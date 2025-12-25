import os
import requests
from datetime import datetime
import time
from threading import Thread, Lock
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
        self.go2rtc_api = "http://localhost:1984/api/frame.jpeg"

    def run(self):
        logger.info(f"[SNAPSHOT] Starting snapshot thread (Interval: {self.interval}s)")
        time.sleep(10) # Wait for go2rtc to be ready
        self.running = True
        while self.running:
            self.take_snapshots()
            self.cleanup()
            time.sleep(self.interval)

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
            # Parse retention (e.g. 7d -> 7 days)
            # Simple parser: only supports 'd' for now or raw int for days
            days = 7
            if SNAPSHOT_KEEP.lower().endswith("d"):
                days = int(SNAPSHOT_KEEP[:-1])
            elif SNAPSHOT_KEEP.isdigit():
                days = int(SNAPSHOT_KEEP)
            
            cutoff = time.time() - (days * 86400)
            
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
        self.running = False
        self.join()
