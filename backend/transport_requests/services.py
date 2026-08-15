from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.models import StaffProfile
from accounts.roles import SUPER_ADMIN, resolve_role
from fleet.models import Vehicle

from .models import TransportRequest, TransportRequestEvent

MANAGERS = {SUPER_ADMIN, StaffProfile.Role.FLEET_MANAGER}
OPERATORS = MANAGERS | {StaffProfile.Role.DISPATCHER}
ALLOCATING_STATUSES = {
    TransportRequest.Status.APPROVED,
    TransportRequest.Status.READY_FOR_DISPATCH,
}
TRANSITIONS = {
    TransportRequest.Status.FOR_APPROVAL: {
        TransportRequest.Status.APPROVED,
        TransportRequest.Status.REJECTED,
        TransportRequest.Status.NEEDS_MORE_DETAILS,
        TransportRequest.Status.CANCELLED,
    },
    TransportRequest.Status.NEEDS_MORE_DETAILS: {
        TransportRequest.Status.FOR_APPROVAL,
        TransportRequest.Status.CANCELLED,
    },
    TransportRequest.Status.APPROVED: {
        TransportRequest.Status.READY_FOR_DISPATCH,
        TransportRequest.Status.CANCELLED,
    },
    TransportRequest.Status.READY_FOR_DISPATCH: {TransportRequest.Status.CANCELLED},
}


class AllocationConflict(Exception):
    def __init__(self, vehicle, conflicts):
        self.vehicle = vehicle
        self.conflicts = conflicts
        super().__init__("Vehicle schedule allocation conflict.")

    @property
    def detail(self):
        numbers = ", ".join(item.request_number for item in self.conflicts)
        return {
            "vehicle": (
                f"Vehicle {self.vehicle.device_id} is already allocated during the "
                f"requested planning window ({numbers})."
            ),
            "conflicting_request_ids": [str(item.pk) for item in self.conflicts],
        }


def require_role(user, allowed):
    if resolve_role(user) not in allowed:
        raise PermissionError


def require_note(note):
    normalized = note.strip()
    if not normalized:
        raise serializers.ValidationError({"note": "A meaningful note is required."})
    return normalized


def record_event(request, event_type, user, previous_status="", note=""):
    return TransportRequestEvent.objects.create(
        request=request,
        event_type=event_type,
        previous_status=previous_status,
        new_status=request.status,
        performed_by=user,
        note=note,
    )


def planning_end(request):
    return request.scheduled_pickup_at + timedelta(minutes=request.estimated_duration_minutes)


def allocation_conflicts(request, vehicle):
    requested_start = request.scheduled_pickup_at
    requested_end = planning_end(request)
    candidates = (
        TransportRequest.objects.filter(
            assigned_vehicle=vehicle,
            status__in=ALLOCATING_STATUSES,
            scheduled_pickup_at__lt=requested_end,
        )
        .exclude(pk=request.pk)
        .order_by("scheduled_pickup_at", "pk")
    )
    plan_id = getattr(getattr(request, "dispatch_assignment", None), "plan_id", None)
    if plan_id:
        candidates = candidates.exclude(dispatch_assignment__plan_id=plan_id)
    return [item for item in candidates if planning_end(item) > requested_start]


def validate_vehicle(request, vehicle):
    if not vehicle.is_active:
        raise serializers.ValidationError({"vehicle": "Vehicle must be active."})
    if (
        vehicle.passenger_capacity is not None
        and vehicle.passenger_capacity < request.passenger_count
    ):
        raise serializers.ValidationError(
            {"vehicle": "Vehicle passenger capacity is lower than the passenger count."}
        )
    if request.required_vehicle_type and vehicle.vehicle_type != request.required_vehicle_type:
        raise serializers.ValidationError(
            {"vehicle": (f"Vehicle type must be {request.get_required_vehicle_type_display()}.")}
        )
    conflicts = allocation_conflicts(request, vehicle)
    if conflicts:
        raise AllocationConflict(vehicle, conflicts)


def lock_relevant_vehicles(*vehicle_ids):
    """Lock only the supplied vehicles, using one stable database ordering."""
    relevant_ids = {vehicle_id for vehicle_id in vehicle_ids if vehicle_id is not None}
    return {
        vehicle.pk: vehicle
        for vehicle in Vehicle.objects.select_for_update()
        .filter(pk__in=relevant_ids)
        .order_by("pk")
    }


def apply_transition(current, new_status, user, event_type, note=""):
    if new_status not in TRANSITIONS.get(current.status, set()):
        raise serializers.ValidationError(
            {"status": f"Cannot transition from {current.status} to {new_status}."}
        )
    previous = current.status
    current.status = new_status
    fields = ["status", "updated_at"]
    if new_status == TransportRequest.Status.APPROVED:
        current.approved_by = user
        current.approved_at = timezone.now()
        fields += ["approved_by", "approved_at"]
    current.save(update_fields=fields)
    record_event(current, event_type, user, previous, note)
    return current


@transaction.atomic
def transition(request, new_status, user, event_type, note=""):
    current = TransportRequest.objects.select_for_update().get(pk=request.pk)
    return apply_transition(current, new_status, user, event_type, note)


def approve(request, user, note=""):
    require_role(user, MANAGERS)
    return transition(request, TransportRequest.Status.APPROVED, user, "APPROVED", note.strip())


def reject(request, user, note=""):
    require_role(user, MANAGERS)
    return transition(
        request, TransportRequest.Status.REJECTED, user, "REJECTED", require_note(note)
    )


def request_more_details(request, user, note=""):
    require_role(user, MANAGERS)
    return transition(
        request,
        TransportRequest.Status.NEEDS_MORE_DETAILS,
        user,
        "REQUESTED_MORE_DETAILS",
        require_note(note),
    )


def resubmit(request, user, note=""):
    require_role(user, OPERATORS)
    return transition(
        request,
        TransportRequest.Status.FOR_APPROVAL,
        user,
        "RESUBMITTED",
        note.strip(),
    )


def cancel(request, user, note=""):
    require_role(user, MANAGERS)
    return transition(
        request, TransportRequest.Status.CANCELLED, user, "CANCELLED", require_note(note)
    )


@transaction.atomic
def assign_vehicle(request, vehicle, user, note=""):
    require_role(user, OPERATORS)
    current = TransportRequest.objects.select_for_update().get(pk=request.pk)
    if hasattr(current, "dispatch_assignment"):
        raise serializers.ValidationError(
            {"vehicle": "Use Dispatch Board to change a confirmed Driver/Vehicle assignment."}
        )
    if current.status != TransportRequest.Status.APPROVED:
        raise serializers.ValidationError(
            {"status": "Only approved requests can be assigned or reassigned."}
        )
    locked_vehicles = lock_relevant_vehicles(
        current.assigned_vehicle_id,
        vehicle.pk,
    )
    selected_vehicle = locked_vehicles[vehicle.pk]
    if current.assigned_vehicle_id == selected_vehicle.pk:
        raise serializers.ValidationError(
            {"vehicle": f"Vehicle {selected_vehicle.device_id} is already assigned."}
        )
    validate_vehicle(current, selected_vehicle)
    previous_vehicle = locked_vehicles.get(current.assigned_vehicle_id)
    old_device_id = previous_vehicle.device_id if previous_vehicle else ""
    current.assigned_vehicle = selected_vehicle
    current.save(update_fields=["assigned_vehicle", "updated_at"])
    if old_device_id:
        event_type = "VEHICLE_REASSIGNED"
        allocation_note = f"{old_device_id} -> {selected_vehicle.device_id}"
    else:
        event_type = "VEHICLE_ASSIGNED"
        allocation_note = f"Unassigned -> {selected_vehicle.device_id}"
    if note.strip():
        allocation_note = f"{allocation_note}. {note.strip()}"
    record_event(current, event_type, user, current.status, allocation_note)
    return current


@transaction.atomic
def prepare_dispatch(request, user, note=""):
    require_role(user, OPERATORS)
    current = TransportRequest.objects.select_for_update().get(pk=request.pk)
    if current.status != TransportRequest.Status.APPROVED:
        raise serializers.ValidationError(
            {"status": "Only approved requests can be prepared for dispatch."}
        )
    if not current.assigned_vehicle_id:
        raise serializers.ValidationError({"assigned_vehicle": "Assign a vehicle first."})
    from .dispatch import driver_conflicts, validate_driver
    from .models import DispatchAssignment

    assignment = (
        DispatchAssignment.objects.select_for_update()
        .select_related("driver", "vehicle")
        .filter(transport_request=current)
        .first()
    )
    if not assignment:
        raise serializers.ValidationError(
            {"dispatch_assignment": "Confirm a Driver and Vehicle in Dispatch Board first."}
        )
    if assignment.vehicle_id != current.assigned_vehicle_id:
        raise serializers.ValidationError(
            {"assigned_vehicle": "Confirmed assignment and request vehicle do not match."}
        )
    validate_driver(current, assignment.driver, exclude_assignment_id=assignment.pk)
    if driver_conflicts(current, assignment.driver, exclude_assignment_id=assignment.pk):
        raise serializers.ValidationError({"driver": "Driver has an overlapping assignment."})
    vehicle = lock_relevant_vehicles(current.assigned_vehicle_id)[current.assigned_vehicle_id]
    validate_vehicle(current, vehicle)
    current.assigned_vehicle = vehicle
    return apply_transition(
        current,
        TransportRequest.Status.READY_FOR_DISPATCH,
        user,
        "PREPARED_FOR_DISPATCH",
        note.strip(),
    )
