from django.db import transaction
from django.utils import timezone

from accounts.models import UserNotification
from accounts.notifications import notify_capability_users

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
    event = DispatchAssignmentEvent.objects.create(
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
    transaction.on_commit(
        lambda: notify_capability_users(
            module="DISPATCH_BOARD",
            action="VIEW",
            notification_type=UserNotification.Type.DRIVER_ACCEPTED,
            title="Driver Accepted Assignment",
            message=(
                f"{assignment.driver} accepted the assignment for "
                f"{assignment.transport_request.request_number}."
            ),
            target_url=f"/transport-requests/{assignment.transport_request_id}",
            source_key=f"dispatch-assignment-event:{event.pk}:driver-accepted",
        ),
        robust=True,
    )
    return assignment, True
