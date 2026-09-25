import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.text import get_valid_filename
from django.utils import timezone

from fleet.models import Driver, Vehicle


def generate_request_number():
    return f"TR-{timezone.localdate():%Y%m%d}-{secrets.token_hex(3).upper()}"


def receipt_image_upload_to(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    safe_name = get_valid_filename(f"{uuid.uuid4().hex}.{extension}")
    today = timezone.localdate()
    return f"trip_receipts/{today:%Y/%m}/{safe_name}"


class TransportRequest(models.Model):
    class SourceSystem(models.TextChoices):
        HOTEL_MANAGEMENT_SYSTEM = "HOTEL_MANAGEMENT_SYSTEM", "Hotel management system"
        RESTAURANT_MANAGEMENT_SYSTEM = (
            "RESTAURANT_MANAGEMENT_SYSTEM",
            "Restaurant management system",
        )
        SUPPLY_CHAIN_MANAGEMENT_SYSTEM = (
            "SUPPLY_CHAIN_MANAGEMENT_SYSTEM",
            "Supply chain management system",
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

    class RequestCategory(models.TextChoices):
        PASSENGER_TRANSPORT = "PASSENGER_TRANSPORT", "Passenger transport"
        DELIVERY_LOGISTICS = "DELIVERY_LOGISTICS", "Delivery logistics"

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
    request_category = models.CharField(  # noqa: DJ001 - null preserves ambiguous legacy rows
        max_length=24, choices=RequestCategory.choices, null=True, blank=True
    )
    requester_name = models.CharField(max_length=160)
    requester_contact = models.CharField(max_length=160, blank=True, default="")
    pickup_name = models.CharField(max_length=200)
    pickup_address = models.CharField(max_length=300)
    pickup_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    pickup_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    destination_name = models.CharField(max_length=200)
    destination_address = models.CharField(max_length=300)
    destination_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    destination_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    scheduled_pickup_at = models.DateTimeField()
    required_vehicle_type = models.CharField(
        max_length=20, choices=Vehicle.VehicleType.choices, blank=True, default=""
    )
    estimated_duration_minutes = models.PositiveSmallIntegerField(
        default=60, validators=[MinValueValidator(15), MaxValueValidator(1440)]
    )
    passenger_count = models.PositiveSmallIntegerField(validators=[MaxValueValidator(100)])
    luggage_count = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])
    load_description = models.TextField(blank=True, default="")
    load_quantity = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)]
    )
    estimated_weight_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    handling_instructions = models.TextField(blank=True, default="")
    temperature_requirement = models.TextField(blank=True, default="")
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    notes = models.TextField(blank=True, default="")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.FOR_APPROVAL)
    assigned_vehicle = models.ForeignKey(
        "fleet.Vehicle",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="transport_requests",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_transport_requests",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
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
                condition=~Q(external_reference=""),
                name="tr_source_external_unique",
            ),
        ]

    def __str__(self):
        return self.request_number

    def save(self, *args, **kwargs):
        for field in (
            "external_reference",
            "requester_name",
            "requester_contact",
            "pickup_name",
            "pickup_address",
            "destination_name",
            "destination_address",
            "notes",
            "load_description",
            "handling_instructions",
            "temperature_requirement",
        ):
            value = getattr(self, field)
            setattr(self, field, value.strip() if isinstance(value, str) else value)
        super().save(*args, **kwargs)


class TransportRequestFlightContext(models.Model):
    """Advisory flight data kept separate from the transport workflow state."""

    class Provider(models.TextChoices):
        FLIGHTRADAR24 = "FLIGHTRADAR24", "Flightradar24"

    class RefreshStatus(models.TextChoices):
        NOT_CONFIGURED = "NOT_CONFIGURED", "Not configured"
        NOT_REFRESHED = "NOT_REFRESHED", "Not refreshed"
        AVAILABLE = "AVAILABLE", "Available"
        UNAVAILABLE = "UNAVAILABLE", "Unavailable"

    transport_request = models.OneToOneField(
        TransportRequest,
        on_delete=models.CASCADE,
        related_name="flight_context",
    )
    provider = models.CharField(
        max_length=24, choices=Provider.choices, default=Provider.FLIGHTRADAR24
    )
    flight_number = models.CharField(max_length=20)
    flight_date = models.DateField(null=True, blank=True)
    origin_airport = models.CharField(max_length=120, blank=True, default="")
    arrival_airport = models.CharField(max_length=120, blank=True, default="")
    terminal = models.CharField(max_length=40, blank=True, default="")
    scheduled_arrival_at = models.DateTimeField(null=True, blank=True)
    estimated_arrival_at = models.DateTimeField(null=True, blank=True)
    actual_arrival_at = models.DateTimeField(null=True, blank=True)
    provider_flight_status = models.CharField(max_length=80, blank=True, default="")
    refresh_status = models.CharField(
        max_length=24,
        choices=RefreshStatus.choices,
        default=RefreshStatus.NOT_REFRESHED,
    )
    last_refresh_attempt_at = models.DateTimeField(null=True, blank=True)
    last_successful_refresh_at = models.DateTimeField(null=True, blank=True)
    refresh_message = models.CharField(max_length=240, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("transport_request_id",)

    def __str__(self):
        return f"{self.transport_request.request_number}: {self.flight_number}"

    def save(self, *args, **kwargs):
        for field in (
            "flight_number",
            "origin_airport",
            "arrival_airport",
            "terminal",
            "provider_flight_status",
            "refresh_message",
        ):
            value = getattr(self, field)
            setattr(self, field, value.strip() if isinstance(value, str) else value)
        super().save(*args, **kwargs)


class IntegrationClient(models.Model):
    TRUSTED_SOURCE_CHOICES = (
        (
            TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            "Hotel management system",
        ),
        (
            TransportRequest.SourceSystem.RESTAURANT_MANAGEMENT_SYSTEM,
            "Restaurant management system",
        ),
        (
            TransportRequest.SourceSystem.SUPPLY_CHAIN_MANAGEMENT_SYSTEM,
            "Supply chain management system",
        ),
    )

    name = models.CharField(max_length=120, unique=True)
    source_system = models.CharField(max_length=40, choices=TRUSTED_SOURCE_CHOICES)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transport_integration_client",
    )
    key_identifier = models.CharField(max_length=32, unique=True, editable=False)
    credential_hash = models.CharField(max_length=256, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    rotated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("name", "pk")
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    source_system__in=(
                        TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
                        TransportRequest.SourceSystem.RESTAURANT_MANAGEMENT_SYSTEM,
                        TransportRequest.SourceSystem.SUPPLY_CHAIN_MANAGEMENT_SYSTEM,
                    )
                ),
                name="integration_client_trusted_source",
            )
        ]

    def __str__(self):
        return f"{self.name}: {self.source_system}"


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


class DispatchAssignment(models.Model):
    class SelectionMode(models.TextChoices):
        OPTIMIZED = "OPTIMIZED", "Optimized"
        MANUAL = "MANUAL", "Manual"

    class ExecutionStatus(models.TextChoices):
        ASSIGNED = "ASSIGNED", "Assigned"
        EN_ROUTE_TO_PICKUP = "EN_ROUTE_TO_PICKUP", "En route to pickup"
        AT_PICKUP = "AT_PICKUP", "At pickup"
        IN_TRANSIT = "IN_TRANSIT", "In transit"
        AT_DESTINATION = "AT_DESTINATION", "At destination"
        COMPLETED = "COMPLETED", "Completed"

    transport_request = models.OneToOneField(
        TransportRequest,
        on_delete=models.PROTECT,
        related_name="dispatch_assignment",
    )
    plan = models.ForeignKey(
        "DispatchPlan",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.PROTECT, related_name="dispatch_assignments"
    )
    driver = models.ForeignKey(
        Driver, on_delete=models.PROTECT, related_name="dispatch_assignments"
    )
    selection_mode = models.CharField(max_length=12, choices=SelectionMode.choices)
    override_reason = models.TextField(blank=True, default="")
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="confirmed_dispatch_assignments",
    )
    confirmed_at = models.DateTimeField(default=timezone.now)
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="accepted_dispatch_assignments",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="updated_dispatch_assignments",
    )
    execution_status = models.CharField(
        max_length=24,
        choices=ExecutionStatus.choices,
        default=ExecutionStatus.ASSIGNED,
    )
    execution_started_at = models.DateTimeField(null=True, blank=True)
    pickup_arrived_at = models.DateTimeField(null=True, blank=True)
    pickup_departed_at = models.DateTimeField(null=True, blank=True)
    destination_arrived_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("transport_request__scheduled_pickup_at", "pk")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(selection_mode="OPTIMIZED")
                    | ~Q(override_reason="")
                ),
                name="dispatch_manual_reason_required",
            )
        ]

    def __str__(self):
        return f"{self.transport_request.request_number}: {self.driver} / {self.vehicle}"


class DispatchAssignmentEvent(models.Model):
    class EventType(models.TextChoices):
        ASSIGNMENT_CONFIRMED = "ASSIGNMENT_CONFIRMED", "Assignment confirmed"
        ASSIGNMENT_CHANGED = "ASSIGNMENT_CHANGED", "Assignment changed"
        DRIVER_ACCEPTED = "DRIVER_ACCEPTED", "Driver accepted"

    assignment = models.ForeignKey(
        DispatchAssignment, on_delete=models.PROTECT, related_name="events"
    )
    event_type = models.CharField(
        max_length=24,
        choices=EventType.choices,
        default=EventType.ASSIGNMENT_CONFIRMED,
    )
    previous_driver = models.ForeignKey(
        Driver,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="previous_dispatch_events",
    )
    previous_vehicle = models.ForeignKey(
        Vehicle,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="previous_dispatch_events",
    )
    new_driver = models.ForeignKey(
        Driver, on_delete=models.PROTECT, related_name="new_dispatch_events"
    )
    new_vehicle = models.ForeignKey(
        Vehicle, on_delete=models.PROTECT, related_name="new_dispatch_events"
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="dispatch_assignment_events",
    )
    selection_mode = models.CharField(
        max_length=12, choices=DispatchAssignment.SelectionMode.choices
    )
    reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")

    def __str__(self):
        return f"{self.assignment}: {self.selection_mode}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Dispatch assignment events are immutable.")
        self.reason = self.reason.strip()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Dispatch assignment events are immutable.")


class DispatchExecutionEvent(models.Model):
    class Action(models.TextChoices):
        START_TOWARD_PICKUP = "START_TOWARD_PICKUP", "Start toward pickup"
        ARRIVE_AT_PICKUP = "ARRIVE_AT_PICKUP", "Arrive at pickup"
        DEPART_PICKUP = "DEPART_PICKUP", "Depart pickup"
        ARRIVE_AT_DESTINATION = "ARRIVE_AT_DESTINATION", "Arrive at destination"
        COMPLETE = "COMPLETE", "Complete"

    class ActorType(models.TextChoices):
        DRIVER = "DRIVER", "Driver"
        STAFF = "STAFF", "Staff"

    assignment = models.ForeignKey(
        DispatchAssignment,
        on_delete=models.PROTECT,
        related_name="execution_events",
    )
    previous_status = models.CharField(
        max_length=24,
        choices=DispatchAssignment.ExecutionStatus.choices,
    )
    new_status = models.CharField(
        max_length=24,
        choices=DispatchAssignment.ExecutionStatus.choices,
    )
    action = models.CharField(max_length=24, choices=Action.choices)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="dispatch_execution_events",
    )
    actor_type = models.CharField(
        max_length=12,
        choices=ActorType.choices,
        default=ActorType.DRIVER,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")

    def __str__(self):
        return f"{self.assignment}: {self.previous_status} -> {self.new_status}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Dispatch execution events are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Dispatch execution events are immutable.")


class SourceResultOutbox(models.Model):
    """Durable completion result seam for a future source-system callback worker."""

    class DeliveryStatus(models.TextChoices):
        UNCONFIGURED = "UNCONFIGURED", "Callback not configured"
        PENDING = "PENDING", "Pending"
        DELIVERED = "DELIVERED", "Delivered"
        FAILED = "FAILED", "Failed"

    transport_request = models.ForeignKey(
        TransportRequest, on_delete=models.PROTECT, related_name="source_result_outbox"
    )
    event_type = models.CharField(max_length=32, default="TRIP_COMPLETED")
    payload = models.JSONField(default=dict)
    delivery_status = models.CharField(
        max_length=16,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.UNCONFIGURED,
    )
    delivery_attempts = models.PositiveSmallIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=240, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=["transport_request", "event_type"],
                name="source_result_outbox_event_uq",
            )
        ]

    def __str__(self):
        return f"{self.transport_request.request_number}: {self.event_type}"


class DispatchPlan(models.Model):
    class PlanType(models.TextChoices):
        CONSOLIDATED = "CONSOLIDATED", "Consolidated"

    plan_type = models.CharField(
        max_length=16, choices=PlanType.choices, default=PlanType.CONSOLIDATED
    )
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="dispatch_plans")
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT, related_name="dispatch_plans")
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="confirmed_dispatch_plans",
    )
    confirmed_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.plan_type}: {self.driver} / {self.vehicle}"


class DispatchPlanStop(models.Model):
    class StopType(models.TextChoices):
        PICKUP = "PICKUP", "Pickup"
        DELIVERY = "DELIVERY", "Delivery"

    plan = models.ForeignKey(DispatchPlan, on_delete=models.PROTECT, related_name="stops")
    transport_request = models.ForeignKey(
        TransportRequest, on_delete=models.PROTECT, related_name="dispatch_plan_stops"
    )
    stop_type = models.CharField(max_length=10, choices=StopType.choices)
    sequence = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ("sequence", "pk")
        constraints = [
            models.UniqueConstraint(fields=["plan", "sequence"], name="dispatch_plan_sequence_uq"),
            models.UniqueConstraint(
                fields=["plan", "transport_request", "stop_type"],
                name="dispatch_plan_request_stop_uq",
            ),
        ]

    def __str__(self):
        return f"{self.plan_id} #{self.sequence}: {self.stop_type}"


class DispatchPlanEvent(models.Model):
    plan = models.ForeignKey(DispatchPlan, on_delete=models.PROTECT, related_name="events")
    event_type = models.CharField(max_length=32)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="dispatch_plan_events"
    )
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")

    def __str__(self):
        return f"{self.plan_id}: {self.event_type}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Dispatch plan events are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Dispatch plan events are immutable.")


class TripExpenseReceipt(models.Model):
    class ExpenseType(models.TextChoices):
        FUEL = "FUEL", "Fuel"
        TOLL = "TOLL", "Toll"

    dispatch_assignment = models.ForeignKey(
        DispatchAssignment,
        on_delete=models.PROTECT,
        related_name="expense_receipts",
    )
    driver = models.ForeignKey(
        Driver,
        on_delete=models.PROTECT,
        related_name="expense_receipts",
    )
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.PROTECT,
        related_name="expense_receipts",
    )
    expense_type = models.CharField(max_length=8, choices=ExpenseType.choices)
    transaction_at = models.DateTimeField()
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    receipt_number = models.CharField(max_length=80, blank=True, default="")
    merchant_or_operator = models.CharField(max_length=160)
    receipt_image = models.FileField(upload_to=receipt_image_upload_to)
    liters = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    fuel_type = models.CharField(
        max_length=20, choices=Vehicle.FuelType.choices, blank=True, default=""
    )
    fuel_grade = models.CharField(
        max_length=20, choices=Vehicle.FuelGrade.choices, blank=True, default=""
    )
    toll_plaza = models.CharField(max_length=160, blank=True, default="")
    confirmed_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-transaction_at", "-created_at", "-pk")
        indexes = [
            models.Index(
                fields=["dispatch_assignment", "-transaction_at"],
                name="trip_rcpt_assign_time_idx",
            ),
            models.Index(fields=["driver", "-created_at"], name="trip_receipt_driver_time_idx"),
            models.Index(
                fields=["expense_type", "receipt_number"],
                name="trip_receipt_type_number_idx",
            ),
        ]

    def __str__(self):
        return f"{self.dispatch_assignment_id} {self.expense_type} {self.amount}"

    def save(self, *args, **kwargs):
        for field in ("receipt_number", "merchant_or_operator", "toll_plaza"):
            setattr(self, field, getattr(self, field).strip())
        super().save(*args, **kwargs)
