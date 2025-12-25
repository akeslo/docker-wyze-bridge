import contextlib
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread
from typing import Optional

from threads import AutoRemoveThread
from wyzebridge.bridge_utils import LIVESTREAM_PLATFORMS, env_bool, env_cam
from wyzebridge.config import IMG_PATH, IMG_TYPE, SNAPSHOT_FORMAT
from wyzebridge.logging import logger

def get_log_level():
    level = env_bool("FFMPEG_LOGLEVEL", "fatal").lower()

    if level in {
        "quiet",
        "panic",
        "fatal",
        "error",
        "warning",
        "info",
        "verbose",
        "debug",
    }:
        return level

    return "warning"

def get_livestream_cmd(uri: str) -> str:
    flv = r"|[f=flv:flvflags=no_duration_filesize:use_fifo=1:fifo_options=attempt_recovery=1\\\:drop_pkts_on_overflow=1:onfail=abort]"

    for platform, api in LIVESTREAM_PLATFORMS.items():
        key = env_bool(f"{platform}_{uri}", style="original")
        if len(key) > 5:
            logger.info(f"📺 Livestream to {platform if api else key} enabled")
            return f"{flv}{api}{key}"

    return ""

purges_running = dict[str, Thread]()

def purge_old(base_path: str, extension: str, keep_time: timedelta):
    if purges_running.get(base_path):   # extension will always be the same, so we can just use base_path
        logger.debug(f"[FFMPEG] Purge already running for {base_path}")
        return

    def wrapped():
        try:
            threshold = datetime.now() - keep_time
            parents = set()

            try:
                for file_path in Path(base_path).rglob(f"*{extension}"):
                    modify_time = file_modified(file_path)

                    if modify_time > threshold.timestamp():
                        continue

                    if file_unlink(file_path):
                        parents.add(file_path.parent)

                while len(parents) > 0:
                    parent = parents.pop()
                    directory_remove_if_empty(parent)

            except FileNotFoundError:
                pass
            except OSError as e:
                logger.error(f"[FFMPEG] Error accessing {base_path}/*{extension}: {e}")
            except RecursionError as e:
                logger.error(f"[FFMPEG] Recursion error while accessing {base_path}/*{extension}: {e}")
        except Exception as e:
            logger.error(f"[FFMPEG] Unexpected error in purge_old: {e}")

    thread = AutoRemoveThread(purges_running, base_path, target=wrapped, name=f"{base_path}_purge")
    thread.daemon = True  # Set thread as daemon
    thread.start()

def wait_for_purges():
    logger.debug("[FFMPEG] Waiting for all purge threads to complete.")
    for thread in purges_running.values():
        with contextlib.suppress(ValueError, AttributeError, RuntimeError):
            thread.join(timeout=30)

    purges_running.clear()  # Clear the dictionary after waiting
    logger.debug("[FFMPEG] All purge threads have completed.")

def file_modified(file_path: Path) -> float:
    try:
        file_stat = os.stat(file_path)
        return file_stat.st_mtime
    except FileNotFoundError:
        pass # ignore these, someone deleted the file out from under us
    except OSError as e:
        logger.error(f"[FFMPEG] Error stat {file_path}: {e}")

    # if an Exception occurs, we return the current time, which will never qualify for deletion
    return datetime.now().timestamp()

def file_unlink(file_path: Path) -> bool:
    try:
        file_path.unlink(missing_ok=True)
        logger.debug(f"[FFMPEG] Deleted: {file_path}")
        return True
    except FileNotFoundError:
        pass # ignore these, someone deleted the file out from under us
    except OSError as e:
        logger.error(f"[FFMPEG] Error unlink {file_path}: {e}")

    return False

def directory_remove_if_empty(directory: Path) -> bool:
    try:
        if not any(directory.iterdir()):
            shutil.rmtree(directory, ignore_errors=True)
            logger.debug(f"[FFMPEG] Deleted empty directory: {directory}")
            return True
    except FileNotFoundError:
        pass # ignore these, someone deleted the directory out from under us
    except OSError as e:
        logger.error(f"[FFMPEG] Error rmtree {directory}: {e}")
    return False

def parse_timedelta(env_key: str) -> Optional[timedelta]:
    value = env_bool(env_key)
    if not value:
        return

    time_map = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
    if value.isdigit():
        value += "s"

    try:
        amount, unit = int(value[:-1]), value[-1]
        if unit not in time_map or amount < 1:
            return
        return timedelta(**{time_map[unit]: amount})
    except (ValueError, TypeError):
        return

def rtsp_snap_cmd(cam_name: str, interval: bool = False):
    ext = IMG_TYPE
    img = f"{IMG_PATH}{cam_name}.{ext}"

    if interval and SNAPSHOT_FORMAT:
        file = datetime.now().strftime(f"{IMG_PATH}{SNAPSHOT_FORMAT}")
        base, _ext = os.path.splitext(file)
        ext = _ext.lstrip(".") or ext
        img = f"{base}.{ext}".format(cam_name=cam_name, CAM_NAME=cam_name.upper())
        os.makedirs(os.path.dirname(img), exist_ok=True)

    keep_time = parse_timedelta("SNAPSHOT_KEEP")
    if keep_time and SNAPSHOT_FORMAT:
        purge_old(IMG_PATH + cam_name, ext, keep_time)

    rotation = []
    if rotate_img := env_bool(f"ROTATE_IMG_{cam_name}"):
        transpose = rotate_img if rotate_img in {"0", "1", "2", "3"} else "clock"
        rotation = ["-filter:v", f"{transpose=}"]

    rtsp_transport = "udp" if "udp" in env_bool("MTX_RTSPTRANSPORTS") else "tcp"

    cmd = (
        ["ffmpeg", "-loglevel", "error", "-analyzeduration", "0", "-probesize", "32"]
        + ["-f", "rtsp", "-rtsp_transport", rtsp_transport, "-thread_queue_size", "500"]
        + ["-i", f"rtsp://0.0.0.0:8554/{cam_name}", "-map", "0:v:0"]
        + rotation
        + ["-f", "image2", "-frames:v", "1", "-y", img]
    )

    if get_log_level() in {"info", "verbose", "debug"}:
        logger.info(f"[FFMPEG] Snapshot command: {' '.join(cmd)}")

    return cmd


def get_webrtc_ffmpeg_cmd(uri: str, has_audio: bool = False) -> list[str]:
    """
    Generate FFmpeg command for WebRTC streams using named pipes.

    This reads H264 video and optionally AAC audio from named pipes
    and outputs to MediaMTX via RTSP.

    Parameters:
    - uri (str): Camera URI for identifying the stream
    - has_audio (bool): Whether to include audio track

    Returns:
    - list[str]: FFmpeg command ready to run as subprocess
    """
    rtsp_transport = "udp" if "udp" in env_bool("MTX_RTSPTRANSPORTS") else "tcp"
    level = get_log_level()

    # Video input from named pipe
    video_input = [
        "-thread_queue_size", "8",
        "-f", "h264",
        "-i", f"/tmp/{uri}_video.pipe"
    ]

    # Audio input from named pipe if enabled
    audio_input = []
    audio_map = []
    if has_audio:
        audio_input = [
            "-thread_queue_size", "8",
            "-f", "aac",
            "-i", f"/tmp/{uri}_audio.pipe"
        ]
        audio_map = ["-map", "1:a", "-c:a", "copy"]

    cmd = (
        ["ffmpeg", "-hide_banner", "-loglevel", level]
        + video_input
        + audio_input
        + ["-map", "0:v", "-c:v", "copy"]
        + audio_map
        + ["-f", "rtsp", f"-rtsp_transport", rtsp_transport]
        + [f"rtsp://127.0.0.1:8554/{uri}"]
    )

    if get_log_level() in {"info", "verbose", "debug"}:
        logger.info(f"[FFMPEG] WebRTC command: {' '.join(cmd)}")

    return cmd
