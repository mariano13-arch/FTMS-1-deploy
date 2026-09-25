import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from django.db import models
from django.utils import timezone

from .models import NumberCodingRule, NumberCodingSuspension, VehicleCodingExemption

MANILA_TIMEZONE = ZoneInfo("Asia/Manila")


@dataclass(frozen=True)
class NumberCodingEvaluation:
    status: str
    reason: str
    plate_last_digit: int | None = None
    matched_rule_id: int | None = None
    matched_suspension_id: int | None = None
    matched_exemption_id: int | None = None

    @property
    def eligible(self):
        return self.status in {"CLEAR", "EXEMPT", "SUSPENDED"}

    def as_dict(self):
        return {
            "status": self.status,
            "reason": self.reason,
            "plate_last_digit": self.plate_last_digit,
        }


def _local_pickup(scheduled_pickup_at):
    if scheduled_pickup_at is None:
        return None
    if timezone.is_naive(scheduled_pickup_at):
        scheduled_pickup_at = timezone.make_aware(scheduled_pickup_at, MANILA_TIMEZONE)
    return scheduled_pickup_at.astimezone(MANILA_TIMEZONE)


def _time_matches(rule, local_time):
    if rule.start_time is None:
        return True
    if rule.start_time <= rule.end_time:
        return rule.start_time <= local_time < rule.end_time
    return local_time >= rule.start_time or local_time < rule.end_time


def evaluate_vehicle_number_coding(vehicle, scheduled_pickup_at):
    local_pickup = _local_pickup(scheduled_pickup_at)
    if local_pickup is None:
        return NumberCodingEvaluation("UNKNOWN", "Scheduled pickup time is unavailable.")
    digits = re.findall(r"\d", vehicle.plate_number or "")
    if not digits:
        return NumberCodingEvaluation(
            "UNKNOWN", "Vehicle plate number has no numeric digit that can be evaluated."
        )
    plate_digit = int(digits[-1])
    local_date = local_pickup.date()
    rules = NumberCodingRule.objects.filter(
        is_active=True,
        weekday=local_pickup.weekday(),
        effective_from__lte=local_date,
    ).filter(
        models.Q(effective_until__isnull=True) | models.Q(effective_until__gte=local_date)
    )
    rule = next(
        (
            candidate
            for candidate in rules.order_by("start_time", "pk")
            if plate_digit in candidate.restricted_last_digits
            and _time_matches(candidate, local_pickup.time().replace(tzinfo=None))
        ),
        None,
    )
    if rule is None:
        return NumberCodingEvaluation(
            "CLEAR", "Number coding is clear for the scheduled pickup time.", plate_digit
        )
    scope = {"authority": rule.authority, "jurisdiction": rule.jurisdiction, "is_active": True}
    suspension = NumberCodingSuspension.objects.filter(
        **scope, starts_at__lte=local_pickup, ends_at__gt=local_pickup
    ).order_by("-starts_at", "-pk").first()
    if suspension:
        return NumberCodingEvaluation(
            "SUSPENDED", "A temporary number coding suspension is active.", plate_digit,
            rule.pk, suspension.pk,
        )
    exemption = VehicleCodingExemption.objects.filter(
        vehicle=vehicle, **scope, starts_at__lte=local_pickup, ends_at__gt=local_pickup
    ).order_by("-starts_at", "-pk").first()
    if exemption:
        return NumberCodingEvaluation(
            "EXEMPT", "A verified vehicle number coding exemption is active.", plate_digit,
            rule.pk, None, exemption.pk,
        )
    return NumberCodingEvaluation(
        "RESTRICTED",
        "Number coding restriction applies to this vehicle for the scheduled pickup time.",
        plate_digit,
        rule.pk,
    )
