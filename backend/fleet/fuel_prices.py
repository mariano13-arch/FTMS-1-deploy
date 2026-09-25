from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from django.utils import timezone

from fleet.models import FuelPriceRecord, Vehicle

FuelPriceBasis = Literal["EXTERNAL_CACHED", "MANUAL", "UNAVAILABLE"]
SUPPORTED_FUEL_TYPES = frozenset(
    (Vehicle.FuelType.DIESEL, Vehicle.FuelType.GASOLINE)
)
PREFERRED_FUEL_PROVIDER = "ShellPH"


@dataclass(frozen=True)
class FuelPriceResolution:
    basis: FuelPriceBasis
    fuel_type: str
    fuel_grade: str
    price_per_liter: Decimal | None
    currency: str | None
    provider: str | None
    effective_at: datetime | None
    retrieved_at: datetime | None
    reason: str


def _valid_price(record):
    price = record.price_per_liter
    return price is not None and price.is_finite() and price > 0


def _resolution(record):
    return FuelPriceResolution(
        basis=record.source_mode,
        fuel_type=record.fuel_type,
        fuel_grade=record.fuel_grade,
        price_per_liter=record.price_per_liter,
        currency=record.currency,
        provider=record.provider,
        effective_at=record.effective_at,
        retrieved_at=record.retrieved_at,
        reason=(
            "LATEST_VALID_EXTERNAL_CACHED_PRICE"
            if record.source_mode == FuelPriceRecord.SourceMode.EXTERNAL_CACHED
            else "LATEST_VALID_MANUAL_FALLBACK_PRICE"
        ),
    )


def resolve_vehicle_fuel_price(vehicle: Vehicle) -> FuelPriceResolution:
    """Resolve the latest factual PHP/L price without fetching or mutating data."""
    fuel_type = vehicle.fuel_type
    if fuel_type not in SUPPORTED_FUEL_TYPES:
        return FuelPriceResolution(
            basis="UNAVAILABLE",
            fuel_type=fuel_type,
            fuel_grade=getattr(vehicle, "fuel_grade", ""),
            price_per_liter=None,
            currency=None,
            provider=None,
            effective_at=None,
            retrieved_at=None,
            reason="UNSUPPORTED_OR_UNRECORDED_VEHICLE_FUEL_TYPE",
        )

    fuel_grade = vehicle.fuel_grade
    if not fuel_grade:
        return FuelPriceResolution(
            basis="UNAVAILABLE",
            fuel_type=fuel_type,
            fuel_grade="",
            price_per_liter=None,
            currency=None,
            provider=None,
            effective_at=None,
            retrieved_at=None,
            reason="FUEL_GRADE_NOT_RECORDED",
        )

    records = FuelPriceRecord.objects.filter(
        fuel_type=fuel_type,
        fuel_grade=fuel_grade,
        currency=FuelPriceRecord.Currency.PHP,
        provider=PREFERRED_FUEL_PROVIDER,
        is_active=True,
        effective_at__lte=timezone.now(),
    )
    for source_mode in (
        FuelPriceRecord.SourceMode.EXTERNAL_CACHED,
        FuelPriceRecord.SourceMode.MANUAL,
    ):
        source_records = records.filter(source_mode=source_mode)
        source_records = source_records.order_by(
            "-effective_at", "-retrieved_at", "-pk"
        )
        for record in source_records:
            if _valid_price(record):
                return _resolution(record)

    return FuelPriceResolution(
        basis="UNAVAILABLE",
        fuel_type=fuel_type,
        fuel_grade=fuel_grade,
        price_per_liter=None,
        currency=None,
        provider=None,
        effective_at=None,
        retrieved_at=None,
        reason="NO_VALID_PREFERRED_PARTNER_PRICE",
    )
