from datetime import datetime, timedelta
import time
import traceback

from astral import LocationInfo
from astral.sun import sun
from tzlocal import get_localzone

from wyzebridge.config import LATITUDE, LONGITUDE, SNAPSHOT_CAMERAS, SNAPSHOT_INT

# Cache for sunrise and sunset times
_cached_sun_times = {"sunrise": None, "sunset": None, "expiry": None}

def should_take_snapshot(snapshot_type: str, last_snap: float) -> bool:
    """
    Determine if a snapshot should be taken based on snapshot type, interval, and time of day.
    Args:
        snapshot_type (str): The type of snapshot (e.g., "rtsp").
        last_snap (float): The timestamp of the last snapshot.
    Returns:
        bool: True if a snapshot should be taken, False otherwise.
    """
    try:
        global _cached_sun_times
        now = datetime.now(get_localzone())

        # Check if cache is valid
        if not _cached_sun_times["expiry"] or now >= _cached_sun_times["expiry"]:
            city = LocationInfo("CustomLocation", "CustomRegion", get_localzone().key, LATITUDE, LONGITUDE)
            s = sun(city.observer, date=now)
            _cached_sun_times = {
                "sunrise": s["sunrise"],
                "sunset": s["sunset"],
                "expiry": s["dusk"] + timedelta(hours=6)  # Cache until after today's dusk
            }

        # Retrieve times from cache
        sunrise_start = _cached_sun_times["sunrise"] - timedelta(hours=1)
        sunrise_end = _cached_sun_times["sunrise"] + timedelta(hours=2)
        sunset_start = _cached_sun_times["sunset"] - timedelta(hours=2)
        sunset_end = _cached_sun_times["sunset"] + timedelta(hours=1)

        # Determine if current time is within the windows
        in_sunrise_window = sunrise_start <= now <= sunrise_end
        in_sunset_window = sunset_start <= now <= sunset_end

        # Interval selection
        interval = 30 if in_sunrise_window or in_sunset_window else SNAPSHOT_INT
    except Exception as e:
        # Log error with traceback
        print("Error calculating sunrise/sunset times:")
        print(traceback.format_exc())
        interval = SNAPSHOT_INT

    # Return whether a snapshot should be taken
    return snapshot_type in ["rtsp", "api"] and (time.time() - last_snap >= interval)

def should_skip_snapshot(cam_name: str) -> bool:
    """
    Return if camera in list of permitted snapshot cameras
    Args:
        cam_name (str): Camera name to check
    Returns:
        bool: If camera is in filtered cameras, or no var set
    """
    if not SNAPSHOT_CAMERAS:
        return False
    if cam_name in SNAPSHOT_CAMERAS:
        return False
    return True