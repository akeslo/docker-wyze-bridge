"""go2rtc configuration and process management."""
import os
import signal
import time
import yaml
import requests
from contextlib import suppress
from pathlib import Path
from subprocess import Popen, TimeoutExpired
from typing import Optional

from wyzebridge.logging import logger

GO2RTC_CONFIG = "/app/go2rtc.yaml"
GO2RTC_BIN = "/app/go2rtc"
GO2RTC_API = "http://127.0.0.1:1984"

# Streams that had no producers for this many consecutive checks get restarted
HEALTH_FAIL_THRESHOLD = 2
# Seconds between health checks
HEALTH_CHECK_INTERVAL = 30
# Consecutive failed go2rtc API calls (process alive but not responding) before
# the whole go2rtc process is force-restarted. A single blip shouldn't restart
# the process, so this tolerates a few checks (~90s) before escalating.
API_FAIL_THRESHOLD = 3


class Go2RtcServer:
    """Manages go2rtc process and configuration."""

    __slots__ = "sub_process", "config", "_stream_fail_counts", "_last_health_check", "_api_fail_count"

    def __init__(self):
        self.sub_process: Optional[Popen] = None
        self._stream_fail_counts: dict[str, int] = {}
        self._last_health_check: float = 0
        self._api_fail_count: int = 0
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
            self._api_fail_count = 0
            return True
        except Exception as ex:
            logger.error(f"[go2rtc] Failed to start: {ex}")
            return False

    def stop(self):
        """Stop go2rtc process."""
        if not (self.sub_process and self.sub_process.poll() is None):
            return

        logger.info("[go2rtc] Stopping...")
        try:
            pgid = os.getpgid(self.sub_process.pid)
        except (ProcessLookupError, OSError):
            # Already reaped between poll() and here.
            return

        try:
            os.killpg(pgid, signal.SIGTERM)
            self.sub_process.wait(timeout=5)
        except TimeoutExpired:
            # A go2rtc that ignores SIGTERM must not take the caller down with
            # it — restart_process() would never reach start(), leaving the
            # monitoring thread dead with go2rtc down.
            logger.warning("[go2rtc] Did not exit on SIGTERM, sending SIGKILL")
            with suppress(ProcessLookupError, OSError, TimeoutExpired):
                os.killpg(pgid, signal.SIGKILL)
                self.sub_process.wait(timeout=5)
        except (ProcessLookupError, OSError) as ex:
            logger.debug(f"[go2rtc] Process already gone: {ex}")

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

    def restart_process(self):
        """Force-restart the go2rtc process itself (not just a stream).

        Used when the process is alive but its API has stopped responding —
        e.g. a panic inside a single goroutine that Go recovers per-request,
        leaving the OS process running but the API listener dead. is_running()
        can't detect this since the process never exits; only a failing API
        health check surfaces it.
        """
        logger.error("[go2rtc] API unresponsive after repeated checks — restarting process")
        self.stop()
        self._stream_fail_counts = {uri: 0 for uri in self._stream_fail_counts}
        self.start()

    def health_check_streams(self):
        """Check go2rtc stream health and restart broken streams.

        Called periodically from the main bridge loop. Detects streams
        that have consumers but no active producer (broken pipe state)
        and force-restarts them. Also detects the process-alive-but-API-dead
        state (e.g. an internal panic) and force-restarts the whole process
        after a few consecutive unresponsive checks.
        """
        now = time.time()
        if now - self._last_health_check < HEALTH_CHECK_INTERVAL:
            return
        self._last_health_check = now

        if not self.is_running():
            return

        streams = self.get_streams_status()
        if streams is None:
            self._api_fail_count += 1
            logger.warning(
                f"[go2rtc] API unresponsive (fail count: {self._api_fail_count}/{API_FAIL_THRESHOLD})"
            )
            if self._api_fail_count >= API_FAIL_THRESHOLD:
                self.restart_process()
            return
        self._api_fail_count = 0

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
