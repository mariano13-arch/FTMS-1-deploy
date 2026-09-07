from django.db import transaction
from django.utils import timezone

from .models import DispatchAssignment, DispatchAssignmentEvent, TransportRequest


class InvalidAssignmentAcceptance(Exception):
    pass


@transaction.atomic
def accept_driver_assignment(*, assignment_id, driver, user, expected_confirmed_at):
    assignment = (
        DispatchAssignment.objects.select_for_update()
        .select_related("transport_request", "driver", "vehicle")
        .get(pk=assignment_id, driver=driver)
    )
    if assignment.transport_request.status != TransportRequest.Status.READY_FOR_DISPATCH:
        raise InvalidAssignmentAcceptance("Only released assignments can be accepted.")
    if assignment.confirmed_at != expected_confirmed_at:
        raise InvalidAssignmentAcceptance(
            "This assignment changed after it was loaded. Refresh before accepting."
        )
    if assignment.accepted_at is not None:
        return assignment, False

    assignment.accepted_at = timezone.now()
    assignment.accepted_by = user
    assignment.save(update_fields=["accepted_at", "accepted_by", "updated_at"])
    DispatchAssignmentEvent.objects.create(
        assignment=assignment,
        event_type=DispatchAssignmentEvent.EventType.DRIVER_ACCEPTED,
        previous_driver=assignment.driver,
        previous_vehicle=assignment.vehicle,
        new_driver=assignment.driver,
        new_vehicle=assignment.vehicle,
        performed_by=user,
        selection_mode=assignment.selection_mode,
        reason="",
    )
    return assignment, True
