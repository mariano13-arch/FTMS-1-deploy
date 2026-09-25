from dataclasses import dataclass

from django.db import transaction
from django.db.models import Exists, OuterRef, QuerySet
from django.utils import timezone
from rest_framework import serializers

from accounts.models import UserNotification
from accounts.notifications import notify_capability_users

from .models import Vehicle, VehicleMaintenanceRecord

ACTIVE_MAINTENANCE_STATUSES = (
    VehicleMaintenanceRecord.Status.OPEN,
    VehicleMaintenanceRecord.Status.SCHEDULED,
    VehicleMaintenanceRecord.Status.IN_PROGRESS,
)

ALLOWED_TRANSITIONS = {
    VehicleMaintenanceRecord.Status.OPEN: {
        VehicleMaintenanceRecord.Status.SCHEDULED,
        VehicleMaintenanceRecord.Status.IN_PROGRESS,
        VehicleMaintenanceRecord.Status.CANCELLED,
    },
    VehicleMaintenanceRecord.Status.SCHEDULED: {
        VehicleMaintenanceRecord.Status.IN_PROGRESS,
        VehicleMaintenanceRecord.Status.CANCELLED,
    },
    VehicleMaintenanceRecord.Status.IN_PROGRESS: {
        VehicleMaintenanceRecord.Status.COMPLETED,
    },
}


@dataclass(frozen=True)
class MaintenanceReadiness:
    eligible: bool
    reason: str


def with_maintenance_readiness(queryset: QuerySet[Vehicle]) -> QuerySet[Vehicle]:
    active = VehicleMaintenanceRecord.objects.filter(
        vehicle_id=OuterRef("pk"), status__in=ACTIVE_MAINTENANCE_STATUSES
    )
    return queryset.annotate(has_active_maintenance=Exists(active))


def maintenance_readiness(vehicle: Vehicle) -> MaintenanceReadiness:
    active = getattr(vehicle, "has_active_maintenance", None)
    if active is None:
        active = VehicleMaintenanceRecord.objects.filter(
            vehicle=vehicle, status__in=ACTIVE_MAINTENANCE_STATUSES
        ).exists()
    return MaintenanceReadiness(not active, "" if not active else "Active maintenance record.")


@transaction.atomic
def transition_maintenance(record_id, new_status, scheduled_at=None):
    record = VehicleMaintenanceRecord.objects.select_for_update().get(pk=record_id)
    if new_status not in ALLOWED_TRANSITIONS.get(record.status, set()):
        raise serializers.ValidationError(
            {"status": f"Cannot transition from {record.status} to {new_status}."}
        )
    if new_status == VehicleMaintenanceRecord.Status.SCHEDULED and scheduled_at is None:
        raise serializers.ValidationError({"scheduled_at": "Scheduled date and time are required."})
    if scheduled_at is not None and new_status != VehicleMaintenanceRecord.Status.SCHEDULED:
        raise serializers.ValidationError(
            {"scheduled_at": "Only the SCHEDULED transition accepts this field."}
        )
    now = timezone.now()
    fields = ["status", "updated_at"]
    record.status = new_status
    if new_status == VehicleMaintenanceRecord.Status.SCHEDULED:
        record.scheduled_at = scheduled_at
        fields.append("scheduled_at")
    if new_status == VehicleMaintenanceRecord.Status.IN_PROGRESS:
        record.started_at = now
        fields.append("started_at")
    if new_status == VehicleMaintenanceRecord.Status.COMPLETED:
        record.completed_at = now
        fields.append("completed_at")
    record.save(update_fields=fields)
    if new_status == VehicleMaintenanceRecord.Status.COMPLETED:
        transaction.on_commit(
            lambda: notify_capability_users(
                module="MAINTENANCE",
                action="VIEW",
                notification_type=UserNotification.Type.MAINTENANCE_COMPLETED,
                title="Maintenance Completed",
                message=(
                    f"Maintenance completed for {record.vehicle.display_name}: {record.title}."
                ),
                target_url="/maintenance",
                source_key=f"vehicle-maintenance:{record.pk}:completed",
            ),
            robust=True,
        )
    return record
