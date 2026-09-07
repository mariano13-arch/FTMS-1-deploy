import math
from datetime import UTC, timedelta

from django.conf import settings
from django.utils import timezone


def current_telemetry_cutoff(now=None):
    reference_time = now or timezone.now()
    return reference_time + timedelta(
        seconds=settings.FTMS_TELEMETRY_CLOCK_SKEW_SECONDS
    )


def current_event_for_vehicle(vehicle, *, now=None):
    return (
        vehicle.telemetry_events.select_related("device", "vehicle")
        .filter(recorded_at__lte=current_telemetry_cutoff(now))
        .order_by("-recorded_at", "-sequence_number", "-received_at", "-pk")
        .first()
    )


def utc_iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def numeric(value):
    return None if value is None else float(value)


def valid_position(event):
    if event is None or event.location is None:
        return None
    latitude = event.location.y
    longitude = event.location.x
    if not (
        math.isfinite(latitude)
        and math.isfinite(longitude)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    ):
        return None
    return {"latitude": latitude, "longitude": longitude}


def event_data(event):
    return {
        "schema_version": event.schema_version,
        "event_id": event.event_id,
        "sequence_number": event.sequence_number,
        "device_id": event.device.device_id,
        "recorded_at": utc_iso(event.recorded_at),
        "received_at": utc_iso(event.received_at),
        "latitude": event.location.y,
        "longitude": event.location.x,
        "position_source": event.position_source,
        "position_accuracy_m": numeric(event.position_accuracy_m),
        "gnss_speed_kph": numeric(event.gnss_speed_kph),
        "rpm": event.rpm,
        "coolant_c": numeric(event.coolant_c),
        "engine_load_pct": numeric(event.engine_load_pct),
        "obd_source": event.obd_source,
        "driving_event": event.driving_event,
    }


def semantic_values(event):
    data = event_data(event)
    data.pop("received_at")
    return data


def vehicle_status_data(vehicle, event):
    return {
        "vehicle": {
            "device_id": vehicle.device_id,
            "plate_number": vehicle.plate_number,
            "display_name": vehicle.display_name,
        },
        "latest": None if event is None else event_data(event),
    }


def latest_status_data(vehicle):
    event = current_event_for_vehicle(vehicle)
    return vehicle_status_data(vehicle, event)
