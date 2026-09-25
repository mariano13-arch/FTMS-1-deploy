from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from fleet.fuel_prices import resolve_vehicle_fuel_price
from fleet.models import Vehicle
from ml.fuel_rate_resolver import FuelRateBasis
from transport_requests.fuel_estimation import estimate_trip_fuel

MONEY_PRECISION = Decimal("0.01")


@dataclass(frozen=True)
class TripFuelCostEstimate:
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    fuel_rate_basis: FuelRateBasis
    fuel_rate_lph: Decimal | None
    travel_time_seconds: Decimal | None
    estimated_fuel_liters: Decimal | None
    fuel_type: str
    fuel_grade: str
    price_per_liter: Decimal | None
    currency: str | None
    price_provider: str | None
    price_source_mode: str | None
    price_effective_at: datetime | None
    estimated_fuel_cost_php: Decimal | None
    fuel_source_timestamp: datetime | None
    history_sample_count: int
    reason: str
    fuel_rate_provenance: str | None = None


def estimate_trip_fuel_cost(
    vehicle: Vehicle, travel_time_seconds
) -> TripFuelCostEstimate:
    """Estimate trip cost using trip liters and exact-grade preferred-partner price."""
    fuel = estimate_trip_fuel(vehicle, travel_time_seconds)
    price = resolve_vehicle_fuel_price(vehicle)

    reason = None
    if price.reason == "FUEL_GRADE_NOT_RECORDED":
        reason = price.reason
    elif fuel.basis == "UNAVAILABLE" or fuel.estimated_fuel_liters is None:
        reason = fuel.reason
    elif price.basis == "UNAVAILABLE" or price.price_per_liter is None:
        reason = price.reason

    cost = None
    if reason is None:
        cost = (fuel.estimated_fuel_liters * price.price_per_liter).quantize(
            MONEY_PRECISION, rounding=ROUND_HALF_UP
        )

    return TripFuelCostEstimate(
        status="UNAVAILABLE" if reason else "AVAILABLE",
        fuel_rate_basis=fuel.basis,
        fuel_rate_lph=fuel.fuel_rate_lph,
        travel_time_seconds=fuel.travel_time_seconds,
        estimated_fuel_liters=fuel.estimated_fuel_liters,
        fuel_type=vehicle.fuel_type,
        fuel_grade=vehicle.fuel_grade,
        price_per_liter=price.price_per_liter,
        currency=price.currency,
        price_provider=price.provider,
        price_source_mode=None if price.basis == "UNAVAILABLE" else price.basis,
        price_effective_at=price.effective_at,
        estimated_fuel_cost_php=cost,
        fuel_source_timestamp=fuel.source_timestamp,
        history_sample_count=fuel.history_sample_count,
        reason=reason or "PREFERRED_PARTNER_TRIP_FUEL_COST_ESTIMATED",
        fuel_rate_provenance=fuel.provenance,
    )
