import logging
from dataclasses import dataclass
from enum import StrEnum

from django.db import IntegrityError, transaction

from telemetry.geofences import evaluate_geofence_transitions
from telemetry.models import TelemetryEvent
from telemetry.presentation import current_event_for_vehicle, semantic_values
from telemetry.realtime import broadcast_vehicle_status
from telemetry.safety import attribute_driver_safety_event
from telemetry.serializers import TelemetryEventInputSerializer

logger = logging.getLogger(__name__)


class IngestionStatus(StrEnum):
    CREATED = "created"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"


class TelemetryValidationError(Exception):
    def __init__(self, errors):
        super().__init__("Telemetry validation failed")
        self.errors = errors


@dataclass(frozen=True)
class IngestionResult:
    status: IngestionStatus
    event: TelemetryEvent


def _incoming_semantic_values(serializer):
    data = serializer.validated_data
    return {
        **data,
        "recorded_at": data["recorded_at"].isoformat().replace("+00:00", "Z"),
        "latitude": float(data["latitude"]),
        "longitude": float(data["longitude"]),
        "gnss_speed_kph": (
            None if data["gnss_speed_kph"] is None else float(data["gnss_speed_kph"])
        ),
        "position_accuracy_m": (
            None if data["position_accuracy_m"] is None else float(data["position_accuracy_m"])
        ),
        "coolant_c": None if data["coolant_c"] is None else float(data["coolant_c"]),
        "engine_load_pct": (
            None if data["engine_load_pct"] is None else float(data["engine_load_pct"])
        ),
        "obd_source": data["obd_source"],
    }


def _existing_result(event, serializer):
    status = (
        IngestionStatus.DUPLICATE
        if semantic_values(event) == _incoming_semantic_values(serializer)
        else IngestionStatus.CONFLICT
    )
    return IngestionResult(status=status, event=event)


def _broadcast_if_latest(event_id):
    try:
        event = TelemetryEvent.objects.select_related("device", "vehicle").get(event_id=event_id)
        latest = current_event_for_vehicle(event.vehicle)
        if latest and latest.pk == event.pk:
            broadcast_vehicle_status(event)
    except Exception:
        logger.exception(
            "Post-commit real-time processing failed for event_id=%s; "
            "REST fallback remains available",
            event_id,
        )


def ingest_telemetry(payload):
    serializer = TelemetryEventInputSerializer(data=payload)
    if not serializer.is_valid():
        raise TelemetryValidationError(serializer.errors)

    event_id = serializer.validated_data["event_id"]
    existing = (
        TelemetryEvent.objects.select_related("device", "vehicle")
        .filter(event_id=event_id)
        .first()
    )
    if existing:
        return _existing_result(existing, serializer)

    try:
        with transaction.atomic():
            event = TelemetryEvent.objects.create(**serializer.create_model_values())
            attribute_driver_safety_event(event)
            evaluate_geofence_transitions(event)
            transaction.on_commit(lambda: _broadcast_if_latest(event.event_id))
    except IntegrityError:
        event = TelemetryEvent.objects.select_related("device", "vehicle").get(event_id=event_id)
        return _existing_result(event, serializer)

    event.device = serializer.context["device"]
    event.vehicle = serializer.context["vehicle"]
    return IngestionResult(status=IngestionStatus.CREATED, event=event)
