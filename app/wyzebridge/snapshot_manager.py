import os
import requests
from datetime import datetime
import time
from threading import Thread, Lock, Event
from wyzebridge.config import IMG_PATH, SNAPSHOT_INT, SNAPSHOT_FORMAT, SNAPSHOT_KEEP
from wyzebridge.logging import logger
from wyzebridge.bridge_utils import env_bool

class SnapshotManager(Thread):
    def __init__(self, cameras: dict):
        super().__init__()
        self.cameras = cameras
        self.interval = SNAPSHOT_INT
        self.running = False
        self._lock = Lock()
        self._stop_event = Event()
        self.go2rtc_api = "http://localhost:1984/api/frame.jpeg"

    def run(self):
        logger.info(f"[SNAPSHOT] Starting snapshot thread (Interval: {self.interval}s)")
        # Wait for go2rtc to be ready, but stay interruptible.
        if self._stop_event.wait(10):
            return
        self.running = True
        while self.running:
            self.take_snapshots()
            self.cleanup()
            if self._stop_event.wait(self.interval):
                break

    def take_snapshots(self):
        """Cycle through cameras and save snapshots."""
        for name, cam in self.cameras.items():
            if not self.running:
                break
            if not cam.webrtc_support:
                continue

            try:
                if self.save_snapshot(name):
                    logger.debug(f"[SNAPSHOT] Saved {name}")
                else:
                    logger.debug(f"[SNAPSHOT] Failed to save {name}")
            except Exception as e:
                logger.error(f"[SNAPSHOT] Error saving {name}: {e}")
            
            time.sleep(1) # stagger requests

    def save_snapshot(self, cam_name: str) -> bool:
        """Fetch frame from go2rtc and save to disk."""
        try:
            resp = requests.get(f"{self.go2rtc_api}?src={cam_name}", timeout=15)
            if resp.status_code == 200:
                img_data = resp.content
                # Save 'latest' for WebUI
                with open(f"{IMG_PATH}{cam_name}.jpg", "wb") as f:
                    f.write(img_data)
                
                # Save formatted if enabled
                if SNAPSHOT_FORMAT:
                    try:
                        filename = datetime.now().strftime(SNAPSHOT_FORMAT.format(cam_name=cam_name))
                        file_path = f"{IMG_PATH}{filename}"
                        os.makedirs(os.path.dirname(file_path), exist_ok=True)
                        with open(file_path, "wb") as f:
                            f.write(img_data)
                    except Exception as e:
                        logger.error(f"[SNAPSHOT] Error saving custom format: {e}")

                return True
            logger.debug(f"[SNAPSHOT] Response {resp.status_code} for {cam_name}")
        except Exception as e:
             logger.debug(f"[SNAPSHOT] Exception for {cam_name}: {e}")
        return False

    def cleanup(self):
        """Delete old snapshots based on SNAPSHOT_KEEP"""
        if not SNAPSHOT_FORMAT or not SNAPSHOT_KEEP:
            return
            
        try:
            # Parse retention (e.g. 7d -> 7 days, 24h -> 24 hours). README
            # documents both 'd' and 'h' suffixes as valid; an unrecognized
            # value used to silently fall back to the hardcoded 7-day
            # default with no warning, so SNAPSHOT_KEEP=24h retained 7x
            # longer than configured.
            value = SNAPSHOT_KEEP.strip().lower()
            seconds = 7 * 86400
            if value.endswith("d") and value[:-1].isdigit():
                seconds = int(value[:-1]) * 86400
            elif value.endswith("h") and value[:-1].isdigit():
                seconds = int(value[:-1]) * 3600
            elif value.isdigit():
                seconds = int(value) * 86400
            else:
                logger.warning(
                    f"[SNAPSHOT] Unrecognized SNAPSHOT_KEEP={SNAPSHOT_KEEP!r}, "
                    "defaulting to 7 days"
                )

            cutoff = time.time() - seconds
            
            # Simple walker - this might be slow if many files, but runs in background thread
            count = 0 
            for root, _, files in os.walk(IMG_PATH):
                for file in files:
                    # Skip 'latest' thumbnails which are direct children of IMG_PATH
                    if root == IMG_PATH:
                        continue
                    
                    file_path = os.path.join(root, file)
                    if os.path.getmtime(file_path) < cutoff:
                        os.remove(file_path)
                        count += 1
                        
            if count > 0:
                logger.info(f"[SNAPSHOT] Cleaned up {count} old snapshots")

        except Exception as e:
            logger.error(f"[SNAPSHOT] Cleanup error: {e}")

    def stop(self):
        """Signal the thread and wait briefly for it to unwind.

        The loop used to sit in a bare ``time.sleep(interval)`` (180s by
        default), so callers — the Flask restart routes and the SIGTERM
        clean-up path — blocked for minutes. The stop event wakes it now, and
        the join is bounded and skipped entirely if the thread never started.
        """
        self.running = False
        self._stop_event.set()
        if self.is_alive():
            self.join(timeout=10)
            if self.is_alive():
                logger.warning("[SNAPSHOT] Thread did not exit within 10s")
