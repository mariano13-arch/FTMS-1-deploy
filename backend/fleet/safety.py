from dataclasses import dataclass
from datetime import timedelta
from statistics import fmean, median

from django.db.models import Count, DurationField, ExpressionWrapper, F, Q, Sum

from telemetry.models import DriverSafetyEvent, TelemetryEvent
from transport_requests.models import DispatchAssignment, TransportRequest

MINIMUM_COMPLETED_TRIPS = 3
MINIMUM_DRIVING_SECONDS = 60 * 60


@dataclass(frozen=True)
class DriverSafetyMetrics:
    completed_trip_count: int = 0
    total_driving_seconds: int = 0
    attributed_harsh_event_count: int = 0
    harsh_acceleration_count: int = 0
    harsh_braking_count: int = 0
    sharp_turn_count: int = 0

    @property
    def total_driving_hours(self):
        return self.total_driving_seconds / 3600

    @property
    def harsh_events_per_driving_hour(self):
        if self.total_driving_seconds <= 0:
            return None
        return self.attributed_harsh_event_count / self.total_driving_hours

    @property
    def score_eligible(self):
        return (
            self.completed_trip_count >= MINIMUM_COMPLETED_TRIPS
            and self.total_driving_seconds >= MINIMUM_DRIVING_SECONDS
        )


def eligible_safety_assignments(
    driver_ids=None,
    *,
    completed_at_gte=None,
    completed_at_lt=None,
):
    queryset = DispatchAssignment.objects.filter(
        execution_status=DispatchAssignment.ExecutionStatus.COMPLETED,
        transport_request__status=TransportRequest.Status.READY_FOR_DISPATCH,
        execution_started_at__isnull=False,
        completed_at__isnull=False,
        completed_at__gte=F("execution_started_at"),
    )
    if driver_ids is not None:
        queryset = queryset.filter(driver_id__in=driver_ids)
    if completed_at_gte is not None:
        queryset = queryset.filter(completed_at__gte=completed_at_gte)
    if completed_at_lt is not None:
        queryset = queryset.filter(completed_at__lt=completed_at_lt)
    return queryset


def safety_metrics_for_drivers(
    driver_ids,
    *,
    completed_at_gte=None,
    completed_at_lt=None,
):
    driver_ids = tuple(dict.fromkeys(driver_ids))
    metrics = {driver_id: DriverSafetyMetrics() for driver_id in driver_ids}
    if not driver_ids:
        return metrics

    eligible = eligible_safety_assignments(
        driver_ids,
        completed_at_gte=completed_at_gte,
        completed_at_lt=completed_at_lt,
    )
    duration = ExpressionWrapper(
        F("completed_at") - F("execution_started_at"), output_field=DurationField()
    )
    exposure_by_driver = {
        row["driver_id"]: row
        for row in eligible.values("driver_id").annotate(
            completed_trip_count=Count("pk"),
            total_driving_duration=Sum(duration),
        )
    }
    events_by_driver = {
        row["driver_id"]: row
        for row in DriverSafetyEvent.objects.filter(
            driver_id__in=driver_ids,
            assignment__in=eligible,
        )
        .values("driver_id")
        .annotate(
            attributed_harsh_event_count=Count("pk"),
            harsh_acceleration_count=Count(
                "pk", filter=Q(event_type=TelemetryEvent.DrivingEvent.HARSH_ACCELERATION)
            ),
            harsh_braking_count=Count(
                "pk", filter=Q(event_type=TelemetryEvent.DrivingEvent.HARSH_BRAKING)
            ),
            sharp_turn_count=Count(
                "pk", filter=Q(event_type=TelemetryEvent.DrivingEvent.SHARP_TURN)
            ),
        )
    }

    for driver_id in driver_ids:
        exposure = exposure_by_driver.get(driver_id, {})
        events = events_by_driver.get(driver_id, {})
        driving_duration = exposure.get("total_driving_duration") or timedelta()
        metrics[driver_id] = DriverSafetyMetrics(
            completed_trip_count=exposure.get("completed_trip_count", 0),
            total_driving_seconds=int(driving_duration.total_seconds()),
            attributed_harsh_event_count=events.get("attributed_harsh_event_count", 0),
            harsh_acceleration_count=events.get("harsh_acceleration_count", 0),
            harsh_braking_count=events.get("harsh_braking_count", 0),
            sharp_turn_count=events.get("sharp_turn_count", 0),
        )
    return metrics


def safety_calibration_summary(
    driver_ids,
    *,
    completed_at_gte=None,
    completed_at_lt=None,
):
    driver_ids = tuple(dict.fromkeys(driver_ids))
    metrics_by_driver = safety_metrics_for_drivers(
        driver_ids,
        completed_at_gte=completed_at_gte,
        completed_at_lt=completed_at_lt,
    )
    eligible = [metrics for metrics in metrics_by_driver.values() if metrics.score_eligible]
    rates = [metrics.harsh_events_per_driving_hour for metrics in eligible]

    return {
        "total_drivers": len(driver_ids),
        "exposure_eligible_drivers": len(eligible),
        "eligible_drivers_with_zero_harsh_events": sum(
            metrics.attributed_harsh_event_count == 0 for metrics in eligible
        ),
        "eligible_drivers_with_harsh_events": sum(
            metrics.attributed_harsh_event_count > 0 for metrics in eligible
        ),
        "total_eligible_completed_trips": sum(
            metrics.completed_trip_count for metrics in eligible
        ),
        "total_eligible_driving_hours": sum(
            metrics.total_driving_seconds for metrics in eligible
        )
        / 3600,
        "total_attributed_eligible_harsh_events": sum(
            metrics.attributed_harsh_event_count for metrics in eligible
        ),
        "event_type_counts": {
            TelemetryEvent.DrivingEvent.HARSH_ACCELERATION: sum(
                metrics.harsh_acceleration_count for metrics in eligible
            ),
            TelemetryEvent.DrivingEvent.HARSH_BRAKING: sum(
                metrics.harsh_braking_count for metrics in eligible
            ),
            TelemetryEvent.DrivingEvent.SHARP_TURN: sum(
                metrics.sharp_turn_count for metrics in eligible
            ),
        },
        "events_per_driving_hour": {
            "minimum": min(rates) if rates else None,
            "median": median(rates) if rates else None,
            "mean": fmean(rates) if rates else None,
            "maximum": max(rates) if rates else None,
        },
    }
