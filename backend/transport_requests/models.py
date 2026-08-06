import secrets
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from fleet.models import Vehicle


def generate_request_number():
    return f"TR-{timezone.localdate():%Y%m%d}-{secrets.token_hex(3).upper()}"


class TransportRequest(models.Model):
    class SourceSystem(models.TextChoices):
        HOTEL_MANAGEMENT_SYSTEM = "HOTEL_MANAGEMENT_SYSTEM", "Hotel management system"
        RESTAURANT_MANAGEMENT_SYSTEM = (
            "RESTAURANT_MANAGEMENT_SYSTEM", "Restaurant management system"
        )
        MANUAL_STAFF_ENTRY = "MANUAL_STAFF_ENTRY", "Manual staff entry"
        OTHER_SUBSYSTEM = "OTHER_SUBSYSTEM", "Other subsystem"

    class RequestType(models.TextChoices):
        AIRPORT_PICKUP = "AIRPORT_PICKUP", "Airport pickup"
        AIRPORT_DROPOFF = "AIRPORT_DROPOFF", "Airport dropoff"
        GUEST_TRANSFER = "GUEST_TRANSFER", "Guest transfer"
        VIP_TRANSPORT = "VIP_TRANSPORT", "VIP transport"
        STAFF_SHUTTLE = "STAFF_SHUTTLE", "Staff shuttle"
        SUPPLIER_PICKUP = "SUPPLIER_PICKUP", "Supplier pickup"
        FOOD_DELIVERY = "FOOD_DELIVERY", "Food delivery"
        CATERING_DELIVERY = "CATERING_DELIVERY", "Catering delivery"
        BANQUET_LOGISTICS = "BANQUET_LOGISTICS", "Banquet logistics"
        BRANCH_TRANSFER = "BRANCH_TRANSFER", "Branch transfer"
        OTHER = "OTHER", "Other"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        NORMAL = "NORMAL", "Normal"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    class Status(models.TextChoices):
        FOR_APPROVAL = "FOR_APPROVAL", "For approval"
        NEEDS_MORE_DETAILS = "NEEDS_MORE_DETAILS", "Needs more details"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        READY_FOR_DISPATCH = "READY_FOR_DISPATCH", "Ready for dispatch"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_number = models.CharField(
        max_length=24, unique=True, default=generate_request_number, editable=False
    )
    source_system = models.CharField(max_length=40, choices=SourceSystem.choices)
    external_reference = models.CharField(max_length=120, blank=True, default="")
    request_type = models.CharField(max_length=30, choices=RequestType.choices)
    requester_name = models.CharField(max_length=160)
    requester_contact = models.CharField(max_length=160, blank=True, default="")
    pickup_name = models.CharField(max_length=200)
    pickup_address = models.CharField(max_length=300)
    pickup_latitude = models.DecimalField(
        max_digits=9, decimal_places=6,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    pickup_longitude = models.DecimalField(
        max_digits=9, decimal_places=6,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    destination_name = models.CharField(max_length=200)
    destination_address = models.CharField(max_length=300)
    destination_latitude = models.DecimalField(
        max_digits=9, decimal_places=6,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    destination_longitude = models.DecimalField(
        max_digits=9, decimal_places=6,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    scheduled_pickup_at = models.DateTimeField()
    required_vehicle_type = models.CharField(
        max_length=20, choices=Vehicle.VehicleType.choices, blank=True, default=""
    )
    estimated_duration_minutes = models.PositiveSmallIntegerField(
        default=60, validators=[MinValueValidator(15), MaxValueValidator(1440)]
    )
    passenger_count = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    luggage_count = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    notes = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.FOR_APPROVAL
    )
    assigned_vehicle = models.ForeignKey(
        "fleet.Vehicle", null=True, blank=True, on_delete=models.PROTECT,
        related_name="transport_requests",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="created_transport_requests",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="approved_transport_requests",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("scheduled_pickup_at", "created_at")
        indexes = [
            models.Index(fields=["status"], name="tr_status_idx"),
            models.Index(fields=["scheduled_pickup_at"], name="tr_schedule_idx"),
            models.Index(fields=["priority"], name="tr_priority_idx"),
            models.Index(fields=["source_system"], name="tr_source_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source_system", "external_reference"],
                condition=~Q(external_reference=""), name="tr_source_external_unique",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status="READY_FOR_DISPATCH")
                    | Q(assigned_vehicle__isnull=False)
                ),
                name="tr_ready_requires_vehicle",
            ),
        ]

    def __str__(self):
        return self.request_number

    def save(self, *args, **kwargs):
        for field in (
            "external_reference", "requester_name", "requester_contact", "pickup_name",
            "pickup_address", "destination_name", "destination_address", "notes",
        ):
            value = getattr(self, field)
            setattr(self, field, value.strip() if isinstance(value, str) else value)
        super().save(*args, **kwargs)


class TransportRequestEvent(models.Model):
    request = models.ForeignKey(TransportRequest, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=40)
    previous_status = models.CharField(max_length=24, blank=True, default="")
    new_status = models.CharField(max_length=24, blank=True, default="")
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")

    def __str__(self):
        return f"{self.request.request_number}: {self.event_type}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Transport request events are immutable.")
        self.note = self.note.strip()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Transport request events are immutable.")
