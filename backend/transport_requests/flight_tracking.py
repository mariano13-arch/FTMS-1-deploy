from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from django.conf import settings
from django.utils import timezone

from .models import TransportRequestFlightContext


@dataclass(frozen=True)
class FlightRefreshResult:
    status: str
    message: str


class FlightTrackingProvider(Protocol):
    def refresh(self, context: TransportRequestFlightContext) -> FlightRefreshResult: ...


class Flightradar24Provider:
    """Provider boundary pending verification of the official HTTP contract."""

    def __init__(self, api_token):
        self.configured = bool(api_token.strip())

    def refresh(self, context):
        if not self.configured:
            return FlightRefreshResult(
                TransportRequestFlightContext.RefreshStatus.NOT_CONFIGURED,
                "Flightradar24 is not configured.",
            )
        return FlightRefreshResult(
            TransportRequestFlightContext.RefreshStatus.UNAVAILABLE,
            "Flightradar24 endpoint and response contract have not been verified; "
            "no request was sent.",
        )


def flight_tracking_provider() -> FlightTrackingProvider:
    return Flightradar24Provider(settings.FLIGHTRADAR24_API_TOKEN)


def refresh_flight_context(context):
    """Record a truthful refresh result without guessing an undocumented provider URL."""
    context.last_refresh_attempt_at = timezone.now()
    result = flight_tracking_provider().refresh(context)
    context.refresh_status = result.status
    context.refresh_message = result.message
    context.save(
        update_fields=[
            "last_refresh_attempt_at",
            "refresh_status",
            "refresh_message",
            "updated_at",
        ]
    )
    return result


def _configured_minutes(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def airport_pickup_timing(context, travel_time_seconds=None):
    """Compute advisory timing only when every operational input is explicit."""
    arrival_at = (
        context.actual_arrival_at
        or context.estimated_arrival_at
        or context.scheduled_arrival_at
    )
    arrival_basis = (
        "ACTUAL"
        if context.actual_arrival_at
        else "ESTIMATED"
        if context.estimated_arrival_at
        else "SCHEDULED"
        if context.scheduled_arrival_at
        else None
    )
    allowance = _configured_minutes(settings.AIRPORT_PASSENGER_READY_ALLOWANCE_MINUTES)
    dispatch_buffer = _configured_minutes(settings.DISPATCH_OPERATIONAL_BUFFER_MINUTES)
    missing = []
    if arrival_at is None:
        missing.append("flight arrival time")
    if allowance is None:
        missing.append("passenger-ready allowance")
    if dispatch_buffer is None:
        missing.append("dispatch operational buffer")
    if travel_time_seconds is None:
        missing.append("TomTom travel time")
    if missing:
        return {
            "status": "BLOCKED",
            "message": f"Timing unavailable: {', '.join(missing)}.",
            "arrival_basis": arrival_basis,
            "passenger_ready_at": None,
            "recommended_departure_at": None,
        }
    passenger_ready_at = arrival_at + timedelta(minutes=allowance)
    recommended_departure_at = passenger_ready_at - timedelta(
        seconds=travel_time_seconds, minutes=dispatch_buffer
    )
    return {
        "status": "AVAILABLE",
        "message": "Advisory only; dispatch confirmation remains a staff decision.",
        "arrival_basis": arrival_basis,
        "passenger_ready_at": passenger_ready_at,
        "recommended_departure_at": recommended_departure_at,
    }
