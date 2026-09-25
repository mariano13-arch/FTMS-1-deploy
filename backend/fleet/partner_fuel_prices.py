from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from fleet.fuel_prices import PREFERRED_FUEL_PROVIDER
from fleet.models import FuelPriceRecord, Vehicle

GRADE_FUEL_TYPES = {
    Vehicle.FuelGrade.UNLEADED_91: Vehicle.FuelType.GASOLINE,
    Vehicle.FuelGrade.PREMIUM_95: Vehicle.FuelType.GASOLINE,
    Vehicle.FuelGrade.PREMIUM_97: Vehicle.FuelType.GASOLINE,
    Vehicle.FuelGrade.REGULAR_DIESEL: Vehicle.FuelType.DIESEL,
    Vehicle.FuelGrade.PREMIUM_DIESEL: Vehicle.FuelType.DIESEL,
}


def record_preferred_partner_price(
    *, fuel_grade: str, price_per_liter: Decimal, effective_at: datetime
) -> FuelPriceRecord:
    """Record an authorized factual Shell reference price supplied by an operator."""
    fuel_type = GRADE_FUEL_TYPES.get(fuel_grade)
    if fuel_type is None:
        raise ValidationError({"fuel_grade": "Select an exact supported fuel grade."})
    if timezone.is_naive(effective_at):
        effective_at = timezone.make_aware(effective_at)
    if effective_at > timezone.now():
        raise ValidationError({"effective_at": "Effective date/time cannot be in the future."})

    record = FuelPriceRecord(
        fuel_type=fuel_type,
        fuel_grade=fuel_grade,
        price_per_liter=price_per_liter,
        currency=FuelPriceRecord.Currency.PHP,
        effective_at=effective_at,
        provider=PREFERRED_FUEL_PROVIDER,
        source_mode=FuelPriceRecord.SourceMode.MANUAL,
        is_active=True,
    )
    record.full_clean()
    with transaction.atomic():
        record.save()
    return record
