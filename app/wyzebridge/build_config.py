from platform import machine

from dotenv import load_dotenv

from wyzebridge.bridge_utils import env_bool

load_dotenv()
load_dotenv("/.build_date")

VERSION: str = env_bool("VERSION", "DEV", style="original")
ARCH = machine().upper()
BUILD = env_bool("BUILD", "local")
BUILD_DATE = env_bool("BUILD_DATE")
GITHUB_SHA = env_bool("GITHUB_SHA")
IOS_VERSION: str = env_bool("IOS_VERSION", style="original")
APP_VERSION: str = env_bool("APP_VERSION", style="original")
MTX_TAG: str = env_bool("MTX_TAG", style="original")

BUILD_STR = ARCH

if BUILD != VERSION:
    BUILD_STR += f" {BUILD.upper()} BUILD [{BUILD_DATE}] {GITHUB_SHA:.7} USING MTX {MTX_TAG}"

