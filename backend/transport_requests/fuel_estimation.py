import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fleet.models import Vehicle
from ml.fuel_rate_resolver import FuelRateBasis, resolve_vehicle_fuel_rate

SECONDS_PER_HOUR = Decimal("3600")
LITER_PRECISION = Decimal("0.0001")


@dataclass(frozen=True)
class TripFuelEstimate:
    basis: FuelRateBasis
    fuel_rate_lph: Decimal | None
    travel_time_seconds: Decimal | None
    estimated_fuel_liters: Decimal | None
    source_timestamp: datetime | None
    history_sample_count: int
    model_name: str
    model_version: str
    reason: str
    provenance: str | None = None


def _validated_duration(value):
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        duration = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not duration.is_finite() or duration < 0:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return duration


def estimate_trip_fuel(vehicle: Vehicle, travel_time_seconds) -> TripFuelEstimate:
    """Estimate trip liters from factual persisted L/h and TomTom travel duration."""
    resolution = resolve_vehicle_fuel_rate(vehicle)
    duration = _validated_duration(travel_time_seconds)

    if duration is None:
        return TripFuelEstimate(
            basis="UNAVAILABLE",
            fuel_rate_lph=resolution.fuel_rate_lph,
            travel_time_seconds=None,
            estimated_fuel_liters=None,
            source_timestamp=resolution.source_timestamp,
            history_sample_count=resolution.history_sample_count,
            model_name=resolution.model_name,
            model_version=resolution.model_version,
            reason="INVALID_TRAFFIC_AWARE_TRAVEL_TIME",
            provenance=resolution.provenance,
        )

    if resolution.basis == "UNAVAILABLE" or resolution.fuel_rate_lph is None:
        return TripFuelEstimate(
            basis="UNAVAILABLE",
            fuel_rate_lph=None,
            travel_time_seconds=duration,
            estimated_fuel_liters=None,
            source_timestamp=resolution.source_timestamp,
            history_sample_count=resolution.history_sample_count,
            model_name=resolution.model_name,
            model_version=resolution.model_version,
            reason=resolution.reason,
            provenance=resolution.provenance,
        )

    estimated_liters = (
        resolution.fuel_rate_lph * duration / SECONDS_PER_HOUR
    ).quantize(LITER_PRECISION)
    return TripFuelEstimate(
        basis=resolution.basis,
        fuel_rate_lph=resolution.fuel_rate_lph,
        travel_time_seconds=duration,
        estimated_fuel_liters=estimated_liters,
        source_timestamp=resolution.source_timestamp,
        history_sample_count=resolution.history_sample_count,
        model_name=resolution.model_name,
        model_version=resolution.model_version,
        reason=resolution.reason,
        provenance=resolution.provenance,
    )
