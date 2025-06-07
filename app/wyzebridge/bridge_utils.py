import os
import re
import shutil
from typing import Any

LIVESTREAM_PLATFORMS = {
    "YouTube": "rtmp://a.rtmp.youtube.com/live2/",
    "Facebook": "rtmps://live-api-s.facebook.com:443/rtmp/",
    "RestreamIO": "rtmp://live.restream.io/live/",
    "Livestream": "",
}

def env_cam(env: str, uri: str, default="", style="") -> str:
    return env_bool(
        f"{env}_{uri}",
        env_bool(env, env_bool(f"{env}_all", default, style=style), style=style),
        style=style,
    )

def env_bool(env: str, false="", true="", style="") -> Any:
    """Return env variable or empty string if the variable contains 'false' or is empty."""
    value = os.getenv(env.upper().replace("-", "_"), "").strip("'\" \n\t\r")
    if value.lower() in {"no", "none", "false"}:
        value = ""
    if style.lower() == "bool":
        return bool(value or false)
    if style.lower() == "int":
        return int("".join(filter(str.isdigit, value or str(false))) or 0)
    if style.lower() == "float":
        try:
            return float(value) if value.replace(".", "").isdigit() else float(false)
        except ValueError:
            return 0
    if style.lower() == "upper" and value:
        return value.upper()
    if style.lower() == "original" and value:
        return value
    return true if true and value else value.lower() or false

def env_list(env: str) -> list:
    """Return env values as a list."""
    return [
        x.strip("'\"\n ").upper().replace(":", "")
        for x in os.getenv(env.upper(), "").split(",")
    ]

def clean_cam_name(name: str, uri_sep: str = "_") -> str:
    """Return a URI friendly name by removing special characters and spaces."""
    return (
        re.sub(r"[^\-\w+]", "", name.strip().replace(" ", uri_sep))
        .encode("ascii", "ignore")
        .decode()
    ).upper()

def split_int_str(env_value: str, min: int = 0, default: int = 0) -> tuple[str, int]:
    string_value = "".join(filter(str.isalpha, env_value))
    int_value = int("".join(filter(str.isnumeric, env_value)) or default)
    return string_value, max(int_value, min)

def is_livestream(uri: str) -> bool:
    return any(env_bool(f"{service}_{uri}") for service in LIVESTREAM_PLATFORMS)

def migrate_path(old: str, new: str):
    if not os.path.exists(old):
        return

    print(f"CLEANUP: MIGRATING {old=} to {new=}")

    if not os.path.exists(new):
        os.makedirs(new, exist_ok = True)
    for item in os.listdir(old):
        new_file = os.path.join(new, os.path.relpath(os.path.join(old, item), old))
        if os.path.exists(new_file):
            new_file += ".old"
        shutil.move(os.path.join(old, item), new_file)

    os.rmdir(old)
