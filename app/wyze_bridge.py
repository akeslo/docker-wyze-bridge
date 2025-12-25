"""Main Wyze Bridge application - using go2rtc for WebRTC-to-RTSP."""
from os import makedirs
import signal  # Force rebuild
import sys
from threading import Thread

from wyzebridge.build_config import BUILD_STR, VERSION
from wyzebridge.config import HASS_TOKEN, IMG_PATH, TOKEN_PATH
from wyzebridge.auth import WbAuth
from wyzebridge.bridge_utils import migrate_path
from wyzebridge.hass import setup_hass
from wyzebridge.logging import logger
from wyzebridge.wyze_api import WyzeApi
from wyzebridge.snapshot_manager import SnapshotManager
from wyzebridge.go2rtc_server import Go2RtcServer
from wyzecam.api_models import WyzeCamera

setup_hass(HASS_TOKEN)

makedirs(TOKEN_PATH, exist_ok=True)
makedirs(IMG_PATH, exist_ok=True)

if HASS_TOKEN:
    migrate_path("/config/wyze-bridge/", "/config/")


class WyzeBridge(Thread):
    """Main bridge class - handles Wyze auth and go2rtc stream management."""
    
    __slots__ = "api", "cameras", "go2rtc", "snapshots"

    def __init__(self) -> None:
        Thread.__init__(self)

        for sig in ["SIGTERM", "SIGINT"]:
            signal.signal(getattr(signal, sig), self.clean_up)

        print(f"\n🚀 DOCKER-WYZE-BRIDGE {VERSION} {BUILD_STR} (go2rtc WebRTC-to-RTSP Bridge)\n")
        self.api: WyzeApi = WyzeApi()
        self.cameras: dict[str, WyzeCamera] = {}
        self.go2rtc: Go2RtcServer = Go2RtcServer()
        self.snapshots: SnapshotManager = None

    def health(self):
        """Return health status for /health endpoint."""
        return {
            "wyze_authed": self.api.auth is not None and self.api.auth.access_token is not None,
            "camera_count": len(self.cameras),
            "go2rtc_running": self.go2rtc.is_running(),
            "snapshots_running": self.snapshots and self.snapshots.is_alive(),
        }

    def start(self, fresh_data: bool = False) -> None:
        """Initialize the bridge synchronously."""
        self._initialize(fresh_data)

    def run(self, fresh_data: bool = False) -> None:
        """Initialize and run the bridge in thread mode."""
        self._initialize(fresh_data)
        while True:
            signal.pause()

    def _initialize(self, fresh_data: bool = False) -> None:
        """Login, setup cameras, configure and start go2rtc."""
        self.api.login(fresh_data=fresh_data)
        WbAuth.set_email(email=self.api.get_user().email, force=fresh_data)

        # Discover cameras and configure go2rtc
        self.setup_cameras()

        if len(self.cameras) < 1:
            logger.warning("[BRIDGE] No WebRTC-compatible cameras found!")
            return signal.raise_signal(signal.SIGINT)

        # Start go2rtc with configured streams
        if not self.go2rtc.start():
            logger.error("[BRIDGE] Failed to start go2rtc")
            return signal.raise_signal(signal.SIGINT)

        logger.info(f"🎬 {len(self.cameras)} camera(s) ready for streaming")
        logger.info(f"📺 RTSP streams available at rtsp://HOST:8554/<camera-name>")

        # Start snapshot manager
        try:
            self.snapshots = SnapshotManager(self.cameras)
            self.snapshots.start()
        except Exception as e:
            logger.error(f"Failed to start snapshot manager: {e}")

    def restart(self, fresh_data: bool = False) -> None:
        """Restart the bridge and refresh camera list."""
        if self.snapshots:
            self.snapshots.stop()
        self.go2rtc.stop()
        self.cameras.clear()
        self._initialize(fresh_data)

    def refresh_cams(self) -> None:
        """Refresh camera list from Wyze API."""
        if self.snapshots:
            self.snapshots.stop()
        self.go2rtc.stop()
        self.cameras.clear()
        self.api.get_cameras(fresh_data=True)
        self._initialize(False)

    def setup_cameras(self):
        """Discover cameras and configure go2rtc streams."""
        for cam in self.api.filtered_cams():
            if not cam.webrtc_support:
                logger.warning(f"[!] {cam.nickname} [{cam.product_model}] does not support WebRTC - SKIPPING")
                continue

            logger.info(f"[+] Adding {cam.nickname} [{cam.product_model}] at {cam.name_uri}")
            self.cameras[cam.name_uri] = cam

            # go2rtc will use our Flask signaling endpoint
            # Format: webrtc:http://127.0.0.1:5000/signaling/<cam>?kvs#format=wyze
            signaling_url = f"http://127.0.0.1:5000/signaling/{cam.name_uri}?kvs"
            self.go2rtc.add_camera(cam.name_uri, signaling_url)

    def get_kvs_signal(self, cam_name: str) -> dict:
        """Get KVS signaling data for a camera (used by go2rtc)."""
        return self.api.get_kvs_signal(cam_name)

    def clean_up(self, *_):
        """Clean up before shutdown."""
        logger.info("👋 Shutting down...")
        if self.snapshots:
            self.snapshots.stop()
        if hasattr(self, 'go2rtc'):
            self.go2rtc.stop()
        sys.exit(0)



if __name__ == "__main__":
    wb = WyzeBridge()
    wb.run()
    sys.exit(0)
