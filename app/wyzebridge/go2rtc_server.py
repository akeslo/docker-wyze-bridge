"""go2rtc configuration and process management."""
import os
import signal
import time
import yaml
import requests
from pathlib import Path
from subprocess import Popen
from typing import Optional

from wyzebridge.logging import logger

GO2RTC_CONFIG = "/app/go2rtc.yaml"
GO2RTC_BIN = "/app/go2rtc"
GO2RTC_API = "http://127.0.0.1:1984"

# Streams that had no producers for this many consecutive checks get restarted
HEALTH_FAIL_THRESHOLD = 2
# Seconds between health checks
HEALTH_CHECK_INTERVAL = 30


class Go2RtcServer:
    """Manages go2rtc process and configuration."""

    __slots__ = "sub_process", "config", "_stream_fail_counts", "_last_health_check"

    def __init__(self):
        self.sub_process: Optional[Popen] = None
        self._stream_fail_counts: dict[str, int] = {}
        self._last_health_check: float = 0
        self.config = {
            "api": {"listen": ":1984"},
            "rtsp": {"listen": ":8554"},
            "webrtc": {
                "listen": ":8555",
                "ice_servers": [
                    {"urls": ["stun:stun.l.google.com:19302"]},
                ]
            },
            "log": {
                "level": "info",
                "format": "text"
            },
            "streams": {}
        }

    def add_camera(self, uri: str, signaling_url: str):
        """Add a camera stream to go2rtc config.

        Args:
            uri: Camera URI (e.g., 'back-right-flood-light')
            signaling_url: Full signaling URL for Wyze WebRTC
        """
        # go2rtc Wyze WebRTC format
        self.config["streams"][uri] = f"webrtc:{signaling_url}#format=wyze"
        self._stream_fail_counts[uri] = 0
        logger.info(f"[go2rtc] Added stream: {uri}")

    def write_config(self):
        """Write go2rtc.yaml configuration file."""
        with open(GO2RTC_CONFIG, "w") as f:
            yaml.dump(self.config, f, default_flow_style=False)
        logger.info(f"[go2rtc] Configuration written to {GO2RTC_CONFIG}")

    def start(self) -> bool:
        """Start go2rtc process."""
        if not Path(GO2RTC_BIN).exists():
            logger.error(f"[go2rtc] Binary not found at {GO2RTC_BIN}")
            return False

        self.write_config()

        try:
            self.sub_process = Popen(
                [GO2RTC_BIN, "-config", GO2RTC_CONFIG],
                start_new_session=True
            )
            logger.info(f"[go2rtc] Started with PID {self.sub_process.pid}")
            self._last_health_check = time.time()
            return True
        except Exception as ex:
            logger.error(f"[go2rtc] Failed to start: {ex}")
            return False

    def stop(self):
        """Stop go2rtc process."""
        if self.sub_process and self.sub_process.poll() is None:
            logger.info("[go2rtc] Stopping...")
            os.killpg(os.getpgid(self.sub_process.pid), signal.SIGTERM)
            self.sub_process.wait(timeout=5)
            logger.info("[go2rtc] Stopped")

    def is_running(self) -> bool:
        """Check if go2rtc is running."""
        return self.sub_process is not None and self.sub_process.poll() is None

    def get_streams_status(self) -> Optional[dict]:
        """Query go2rtc API for stream status.

        Returns dict of stream_name -> stream_info, or None on error.
        """
        try:
            resp = requests.get(f"{GO2RTC_API}/api/streams", timeout=5)
            if resp.status_code == 200:
                return resp.json()
        except Exception as ex:
            logger.debug(f"[go2rtc] API query failed: {ex}")
        return None

    def restart_stream(self, uri: str) -> bool:
        """Force-restart a stream by deleting and re-adding via go2rtc API.

        This tears down the existing (possibly dead) source and triggers
        a fresh WebRTC connection on next consumer request.
        """
        source = self.config["streams"].get(uri)
        if not source:
            return False

        try:
            # Delete existing stream (clears dead producers)
            requests.delete(
                f"{GO2RTC_API}/api/streams",
                params={"src": uri},
                timeout=5
            )
            # Re-add stream source so go2rtc can reconnect
            requests.put(
                f"{GO2RTC_API}/api/streams",
                params={"src": uri, "name": uri},
                json={"source": source} if isinstance(source, str) else source,
                timeout=5
            )
            logger.info(f"[go2rtc] Restarted stream: {uri}")
            self._stream_fail_counts[uri] = 0
            return True
        except Exception as ex:
            logger.error(f"[go2rtc] Failed to restart stream {uri}: {ex}")
            return False

    def health_check_streams(self):
        """Check go2rtc stream health and restart broken streams.

        Called periodically from the main bridge loop. Detects streams
        that have consumers but no active producer (broken pipe state)
        and force-restarts them.
        """
        now = time.time()
        if now - self._last_health_check < HEALTH_CHECK_INTERVAL:
            return
        self._last_health_check = now

        if not self.is_running():
            return

        streams = self.get_streams_status()
        if streams is None:
            return

        for uri in self._stream_fail_counts:
            stream_info = streams.get(uri)
            if not stream_info:
                continue

            producers = stream_info.get("producers", [])
            consumers = stream_info.get("consumers", [])

            has_consumers = len(consumers) > 0
            has_producers = len(producers) > 0

            if has_consumers and not has_producers:
                # Consumers waiting but no source — stream is stuck
                self._stream_fail_counts[uri] += 1
                count = self._stream_fail_counts[uri]
                logger.warning(
                    f"[go2rtc] Stream {uri} has {len(consumers)} consumers "
                    f"but no producer (fail count: {count}/{HEALTH_FAIL_THRESHOLD})"
                )
                if count >= HEALTH_FAIL_THRESHOLD:
                    logger.error(f"[go2rtc] Stream {uri} stuck — forcing restart")
                    self.restart_stream(uri)
            elif not has_consumers and not has_producers:
                # Idle stream — check if it was recently broken
                # A stream with 0 consumers and 0 producers after a broken pipe
                # means all clients gave up. Reset fail count but don't restart
                # (go2rtc will connect on-demand when a consumer comes back).
                if self._stream_fail_counts[uri] > 0:
                    logger.info(f"[go2rtc] Stream {uri} idle after failures — resetting fail count")
                    self._stream_fail_counts[uri] = 0
            else:
                # Healthy: has producers (source connected)
                if self._stream_fail_counts[uri] > 0:
                    logger.info(f"[go2rtc] Stream {uri} recovered")
                self._stream_fail_counts[uri] = 0
