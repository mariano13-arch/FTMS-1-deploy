import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from statistics import median
from typing import Literal

from django.db.models import Q
from django.utils import timezone

from fleet.models import Vehicle, VehicleFuelReferenceBaseline
from ml.fuel import VALIDATED_TELEMETRY_SOURCE_MODE, contract
from ml.models import FuelPrediction
from telemetry.models import TelemetryEvent

CURRENT_MAX_AGE = timedelta(minutes=5)
HISTORY_MAX_AGE = timedelta(days=30)
HISTORY_LIMIT = 20
HISTORY_MINIMUM_SAMPLES = 5

FuelRateBasis = Literal[
    "CURRENT_AI",
    "HISTORICAL_AI_BASELINE",
    "FLEET_REFERENCE_BASELINE",
    "UNAVAILABLE",
]


@dataclass(frozen=True)
class FuelRateResolution:
    basis: FuelRateBasis
    fuel_rate_lph: Decimal | None
    source_timestamp: datetime | None
    history_sample_count: int
    model_name: str
    model_version: str
    reason: str
    provenance: str | None = None


def _inputs_are_complete_and_finite(inputs, required_features):
    if not isinstance(inputs, dict) or not all(feature in inputs for feature in required_features):
        return False
    for feature in required_features:
        value = inputs[feature]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if not math.isfinite(float(value)):
            return False
    return True


def _rate_is_finite_and_nonnegative(value):
    return value is not None and value.is_finite() and value >= 0


def _genuine_telemetry_timestamps(vehicle, timestamps):
    return set(
        TelemetryEvent.objects.filter(
            vehicle=vehicle,
            recorded_at__in=timestamps,
            obd_source=TelemetryEvent.ObdSource.PHYSICAL_OBD,
        )
        .exclude(
            Q(position_source=TelemetryEvent.PositionSource.SIMULATED_TEST)
            | Q(obd_source=TelemetryEvent.ObdSource.SIMULATED_TEST)
        )
        .values_list("recorded_at", flat=True)
    )


def resolve_vehicle_fuel_rate(vehicle: Vehicle, *, now=None) -> FuelRateResolution:
    """Resolve factual persisted L/h evidence without running fuel inference."""
    reference_time = now or timezone.now()
    metadata = contract()
    model_name = metadata["model_name"]
    model_version = metadata["model_version"]
    required_features = tuple(metadata["features"])
    history_start = reference_time - HISTORY_MAX_AGE

    candidates = list(
        FuelPrediction.objects.filter(
            vehicle=vehicle,
            source_mode=VALIDATED_TELEMETRY_SOURCE_MODE,
            model_name=model_name,
            model_version=model_version,
            input_timestamp__gte=history_start,
            input_timestamp__lte=reference_time,
        ).order_by("-input_timestamp", "-predicted_at", "-pk")
    )
    genuine_timestamps = _genuine_telemetry_timestamps(
        vehicle, {prediction.input_timestamp for prediction in candidates}
    )
    eligible = [
        prediction
        for prediction in candidates
        if prediction.input_timestamp in genuine_timestamps
        and _rate_is_finite_and_nonnegative(prediction.estimated_fuel_lph)
        and _inputs_are_complete_and_finite(
            prediction.validated_inputs, required_features
        )
    ]

    if eligible:
        latest = eligible[0]
        latest_telemetry_timestamp = (
            TelemetryEvent.objects.filter(vehicle=vehicle)
            .order_by("-recorded_at", "-sequence_number", "-received_at", "-pk")
            .values_list("recorded_at", flat=True)
            .first()
        )
        if (
            reference_time - latest.input_timestamp <= CURRENT_MAX_AGE
            and latest.input_timestamp == latest_telemetry_timestamp
        ):
            return FuelRateResolution(
                basis="CURRENT_AI",
                fuel_rate_lph=latest.estimated_fuel_lph,
                source_timestamp=latest.input_timestamp,
                history_sample_count=0,
                model_name=model_name,
                model_version=model_version,
                reason="LATEST_VALID_PREDICTION_WITHIN_FRESHNESS_WINDOW",
            )

    history = eligible[:HISTORY_LIMIT]
    if len(history) >= HISTORY_MINIMUM_SAMPLES:
        return FuelRateResolution(
            basis="HISTORICAL_AI_BASELINE",
            fuel_rate_lph=median(
                prediction.estimated_fuel_lph for prediction in history
            ),
            source_timestamp=None,
            history_sample_count=len(history),
            model_name=model_name,
            model_version=model_version,
            reason="CURRENT_AI_UNAVAILABLE_USING_SAME_VEHICLE_HISTORY",
        )

    reference = VehicleFuelReferenceBaseline.objects.filter(
        vehicle=vehicle,
        provenance=VehicleFuelReferenceBaseline.Provenance.CAPSTONE_REFERENCE,
        is_active=True,
    ).first()
    if reference and _rate_is_finite_and_nonnegative(
        reference.reference_fuel_rate_lph
    ):
        return FuelRateResolution(
            basis="FLEET_REFERENCE_BASELINE",
            fuel_rate_lph=reference.reference_fuel_rate_lph,
            source_timestamp=None,
            history_sample_count=0,
            model_name="Fleet Reference Policy",
            model_version=reference.basis_version,
            reason="OPERATIONAL_FUEL_RATE_UNAVAILABLE_USING_FLEET_REFERENCE",
            provenance=reference.provenance,
        )

    return FuelRateResolution(
        basis="UNAVAILABLE",
        fuel_rate_lph=None,
        source_timestamp=None,
        history_sample_count=0,
        model_name=model_name,
        model_version=model_version,
        reason="INSUFFICIENT_ELIGIBLE_SAME_VEHICLE_HISTORY",
    )
