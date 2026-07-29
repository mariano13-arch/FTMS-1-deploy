from datetime import UTC


def utc_iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def numeric(value):
    return None if value is None else float(value)


def event_data(event):
    return {
        "schema_version": event.schema_version,
        "event_id": event.event_id,
        "sequence_number": event.sequence_number,
        "device_id": event.vehicle.device_id,
        "recorded_at": utc_iso(event.recorded_at),
        "received_at": utc_iso(event.received_at),
        "latitude": event.location.y,
        "longitude": event.location.x,
        "gnss_speed_kph": numeric(event.gnss_speed_kph),
        "rpm": event.rpm,
        "coolant_c": numeric(event.coolant_c),
        "engine_load_pct": numeric(event.engine_load_pct),
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
    event = vehicle.telemetry_events.select_related("vehicle").first()
    return vehicle_status_data(vehicle, event)
