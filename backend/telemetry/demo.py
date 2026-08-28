import hashlib
import math
from datetime import timedelta

from django.conf import settings


def configuration():
    if not settings.FTMS_DEMO_TELEMETRY_ENABLED:
        return {"enabled": False, "active": False}
    try:
        latitude = float(settings.FTMS_DEMO_TELEMETRY_CENTER_LATITUDE)
        longitude = float(settings.FTMS_DEMO_TELEMETRY_CENTER_LONGITUDE)
        radius_meters = float(settings.FTMS_DEMO_TELEMETRY_RADIUS_METERS)
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError
        if not (100 <= radius_meters <= 10_000):
            raise ValueError
        if not all(math.isfinite(value) for value in (latitude, longitude, radius_meters)):
            raise ValueError
    except (TypeError, ValueError):
        return {
            "enabled": True,
            "active": False,
            "configuration_error": "Demo telemetry center or radius is not configured correctly.",
        }
    return {
        "enabled": True,
        "active": True,
        "center_latitude": latitude,
        "center_longitude": longitude,
        "radius_meters": radius_meters,
    }


DEMO_STATES = ("live", "stale", "offline", "no_telemetry")


def state(vehicle):
    digest = hashlib.sha256(vehicle.device_id.encode()).digest()
    return DEMO_STATES[digest[6] % len(DEMO_STATES)]


def point(vehicle, now, config, telemetry_state, stale_after_seconds):
    digest = hashlib.sha256(vehicle.device_id.encode()).digest()
    angle = int.from_bytes(digest[:4], "big") / (2**32) * 2 * math.pi
    radius = config["radius_meters"] * (0.25 + digest[4] / 255 * 0.75)
    latitude = config["center_latitude"] + radius * math.cos(angle) / 111_320
    longitude_scale = 111_320 * max(abs(math.cos(math.radians(latitude))), 0.2)
    longitude = config["center_longitude"] + radius * math.sin(angle) / longitude_scale
    if telemetry_state == "live":
        age_seconds = 0
        speed_kph = round(10 + digest[5] / 255 * 35, 2)
    elif telemetry_state == "stale":
        age_seconds = stale_after_seconds + 300
        speed_kph = round(digest[5] / 255 * 5, 2)
    elif telemetry_state == "offline":
        age_seconds = stale_after_seconds + 3600
        speed_kph = 0
    else:
        age_seconds = stale_after_seconds + 7200
        speed_kph = 0
    return {
        "latitude": latitude,
        "longitude": longitude,
        "speed_kph": speed_kph,
        "recorded_at": now - timedelta(seconds=age_seconds),
        "age_seconds": age_seconds,
        "driving_event": "NORMAL",
        "telemetry_source": "demo",
        "is_demo_telemetry": True,
    }
