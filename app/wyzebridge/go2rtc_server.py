"""go2rtc configuration and process management."""
import os
import signal
import yaml
from pathlib import Path
from subprocess import Popen
from typing import Optional

from wyzebridge.logging import logger

GO2RTC_CONFIG = "/app/go2rtc.yaml"
GO2RTC_BIN = "/app/go2rtc"


class Go2RtcServer:
    """Manages go2rtc process and configuration."""
    
    __slots__ = "sub_process", "config"
    
    def __init__(self):
        self.sub_process: Optional[Popen] = None
        self.config = {
            "api": {"listen": ":1984"},
            "rtsp": {"listen": ":8554"},
            "webrtc": {"listen": ":8555"},
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
