from django.db.models import Q

from telemetry.models import DriverSafetyEvent, TelemetryEvent
from transport_requests.models import (
    DispatchAssignment,
    TransportRequest,
    TransportRequestEvent,
)

HARSH_DRIVING_EVENTS = frozenset(
    {
        TelemetryEvent.DrivingEvent.HARSH_ACCELERATION,
        TelemetryEvent.DrivingEvent.HARSH_BRAKING,
        TelemetryEvent.DrivingEvent.SHARP_TURN,
    }
)

STARTED_EXECUTION_STATUSES = (
    DispatchAssignment.ExecutionStatus.EN_ROUTE_TO_PICKUP,
    DispatchAssignment.ExecutionStatus.AT_PICKUP,
    DispatchAssignment.ExecutionStatus.IN_TRANSIT,
    DispatchAssignment.ExecutionStatus.AT_DESTINATION,
    DispatchAssignment.ExecutionStatus.COMPLETED,
)


def _assignment_covers(assignment, occurred_at):
    if assignment.execution_started_at is None:
        return False
    if assignment.execution_started_at > occurred_at:
        return False
    if assignment.completed_at is not None and assignment.completed_at < occurred_at:
        return False
    if (
        assignment.execution_status == DispatchAssignment.ExecutionStatus.COMPLETED
        and assignment.completed_at is None
    ):
        return False
    if assignment.transport_request.status == TransportRequest.Status.READY_FOR_DISPATCH:
        return True
    if assignment.transport_request.status != TransportRequest.Status.CANCELLED:
        return False

    cancelled_at = (
        TransportRequestEvent.objects.filter(
            request=assignment.transport_request,
            event_type="CANCELLED",
        )
        .order_by("created_at", "pk")
        .values_list("created_at", flat=True)
        .first()
    )
    return cancelled_at is not None and occurred_at <= cancelled_at


def attribute_driver_safety_event(event):
    if event.driving_event not in HARSH_DRIVING_EVENTS:
        return None
    if event.position_source == TelemetryEvent.PositionSource.SIMULATED_TEST:
        return None

    candidates = DispatchAssignment.objects.select_related("transport_request").filter(
        vehicle_id=event.vehicle_id,
        execution_status__in=STARTED_EXECUTION_STATUSES,
        execution_started_at__lte=event.recorded_at,
    ).filter(Q(completed_at__isnull=True) | Q(completed_at__gte=event.recorded_at))
    matches = [
        assignment
        for assignment in candidates
        if _assignment_covers(assignment, event.recorded_at)
    ]
    if len(matches) != 1:
        return None

    assignment = matches[0]
    safety_event, _ = DriverSafetyEvent.objects.get_or_create(
        telemetry_event=event,
        defaults={
            "assignment": assignment,
            "driver": assignment.driver,
            "vehicle": event.vehicle,
            "event_type": event.driving_event,
            "occurred_at": event.recorded_at,
        },
    )
    return safety_event
