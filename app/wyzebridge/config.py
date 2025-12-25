from os import environ, getenv

from wyzebridge.build_config import BUILD_STR
from wyzebridge.bridge_utils import env_bool, split_int_str
from wyzebridge.hass import setup_hass

HASS_TOKEN: str = getenv("SUPERVISOR_TOKEN", "")

setup_hass(HASS_TOKEN)

MQTT: bool = bool(env_bool("MQTT", style="bool"))
MQTT_HOST: str = env_bool("MQTT_HOST", "", style="original")
MQTT_DISCOVERY: str = env_bool("MQTT_DTOPIC")
MQTT_TOPIC: str = env_bool("MQTT_TOPIC", "wyzebridge").strip("/")

MQTT_ENABLED = bool(env_bool("MQTT_HOST"))
MQTT_USER, _, MQTT_PASS = getenv("MQTT_AUTH", ":").partition(":")
MQTT_HOST, _, MQTT_PORT = getenv("MQTT_HOST", ":").partition(":")
MQTT_RETRIES: int = int(getenv("MQTT_RETRIES", "3"))

# TODO: change TOKEN_PATH  to /config for all:
TOKEN_PATH: str = "/config/" if HASS_TOKEN else "/tokens/"
IMG_PATH: str = f'/{env_bool("IMG_DIR", r"/img").strip("/")}/'

LATITUDE: float = float(getenv("LATITUDE", "0"))
LONGITUDE: float = float(getenv("LONGITUDE", "0"))
SNAPSHOT_CAMERAS: list[str] = [cam.strip() for cam in getenv("SNAPSHOT_CAMERAS", "").split(",") if cam.strip()]
SNAPSHOT_TYPE, SNAPSHOT_INT = split_int_str(env_bool("SNAPSHOT"), min=15, default=180)
SNAPSHOT_FORMAT: str = env_bool("SNAPSHOT_FORMAT", style="original").strip("/")
SNAPSHOT_KEEP: str = env_bool("SNAPSHOT_KEEP", "7d", style="original")
IMG_TYPE: str = env_bool("IMG_TYPE", "jpg", style="original")

# MediaMTX Configuration
MTX_HLSVARIANT: str = env_bool("MTX_HLSVARIANT", "lowLatency", style="original")
MTX_READTIMEOUT: str = env_bool("MTX_READTIMEOUT", "20s", style="original")
MTX_WRITEQUEUESIZE: int = env_bool("MTX_WRITEQUEUESIZE", "512", style="int")



# WebRTC settings
CONNECT_TIMEOUT: int = env_bool("CONNECT_TIMEOUT", "30", style="int")
STUN_SERVER: str = env_bool("STUN_SERVER", "stun:stun.l.google.com:19302", style="original")
SUBJECT_ALT_NAME: str = env_bool("WB_IP", style="original")


MOTION: bool = env_bool("MOTION_API", style="bool")
MOTION_INT: int = max(env_bool("MOTION_INT", "1.5", style="float"), 1.1)
MOTION_START: bool = env_bool("MOTION_START", style="bool")

WB_AUTH: bool = bool(env_bool("WB_AUTH") if getenv("WB_AUTH") else True)

URI_MAC: bool = bool(env_bool("URI_SEPARATOR", style="bool"))
URI_SEPARATOR: str = env_bool("URI_SEPARATOR", "-", style="original")

FRESH_DATA: bool = env_bool("FRESH_DATA", style="bool")

DEPRECATED = {"DEBUG_FFMPEG", "OFFLINE_IFTTT", "TOTP_KEY", "MFA_TYPE"}

for env in DEPRECATED:
    if getenv(env):
        print(f"\n\n[!] WARNING: {env} is deprecated\n\n")

for key in environ:
    if not MOTION and key.startswith("MOTION_WEBHOOKS"):
        print(f"[!] WARNING: {key} will not trigger because MOTION_API is not set")

for key, value in environ.items():
    if key.startswith("WEB_"):
        new_key = key.replace("WEB", "WB")
        print(f"\n[!] WARNING: In {BUILD_STR}, {key} is deprecated! Please use {new_key} instead\n")
        environ.pop(key, None)
        environ[new_key] = value
