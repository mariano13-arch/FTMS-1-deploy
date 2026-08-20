from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from .models import DispatchAssignment, DispatchExecutionEvent, TransportRequest


class IllegalExecutionTransition(Exception):
    pass


@dataclass(frozen=True)
class Transition:
    action: str
    next_status: str
    timestamp_field: str


TRANSITIONS = {
    DispatchAssignment.ExecutionStatus.ASSIGNED: Transition(
        DispatchExecutionEvent.Action.START_TOWARD_PICKUP,
        DispatchAssignment.ExecutionStatus.EN_ROUTE_TO_PICKUP,
        "execution_started_at",
    ),
    DispatchAssignment.ExecutionStatus.EN_ROUTE_TO_PICKUP: Transition(
        DispatchExecutionEvent.Action.ARRIVE_AT_PICKUP,
        DispatchAssignment.ExecutionStatus.AT_PICKUP,
        "pickup_arrived_at",
    ),
    DispatchAssignment.ExecutionStatus.AT_PICKUP: Transition(
        DispatchExecutionEvent.Action.DEPART_PICKUP,
        DispatchAssignment.ExecutionStatus.IN_TRANSIT,
        "pickup_departed_at",
    ),
    DispatchAssignment.ExecutionStatus.IN_TRANSIT: Transition(
        DispatchExecutionEvent.Action.ARRIVE_AT_DESTINATION,
        DispatchAssignment.ExecutionStatus.AT_DESTINATION,
        "destination_arrived_at",
    ),
    DispatchAssignment.ExecutionStatus.AT_DESTINATION: Transition(
        DispatchExecutionEvent.Action.COMPLETE,
        DispatchAssignment.ExecutionStatus.COMPLETED,
        "completed_at",
    ),
}

ACTION_TARGETS = {transition.action: transition.next_status for transition in TRANSITIONS.values()}


def allowed_driver_actions(assignment):
    if assignment.transport_request.status == TransportRequest.Status.CANCELLED:
        return []
    transition = TRANSITIONS.get(assignment.execution_status)
    return [transition.action] if transition else []


@transaction.atomic
def transition_driver_execution(*, assignment_id, driver, user, action):
    assignment = (
        DispatchAssignment.objects.select_for_update()
        .select_related("transport_request")
        .get(pk=assignment_id, driver=driver)
    )
    if assignment.transport_request.status == TransportRequest.Status.CANCELLED:
        raise IllegalExecutionTransition("Cancelled trips cannot be advanced by a driver.")

    target_status = ACTION_TARGETS[action]
    if assignment.execution_status == target_status:
        return assignment, False

    transition = TRANSITIONS.get(assignment.execution_status)
    if transition is None or transition.action != action:
        raise IllegalExecutionTransition(
            "This action is not allowed from the current trip state."
        )

    previous_status = assignment.execution_status
    transition_time = timezone.now()
    assignment.execution_status = transition.next_status
    setattr(assignment, transition.timestamp_field, transition_time)
    assignment.save(
        update_fields=["execution_status", transition.timestamp_field, "updated_at"]
    )
    DispatchExecutionEvent.objects.create(
        assignment=assignment,
        previous_status=previous_status,
        new_status=transition.next_status,
        action=transition.action,
        performed_by=user,
        actor_type=DispatchExecutionEvent.ActorType.DRIVER,
    )
    return assignment, True
