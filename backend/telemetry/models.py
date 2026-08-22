import uuid

from django.conf import settings
from django.contrib.gis.db import models
from django.db.models import Q


class TelemetryEvent(models.Model):
    class DrivingEvent(models.TextChoices):
        NORMAL = "NORMAL", "Normal"
        HARSH_BRAKING = "HARSH_BRAKING", "Harsh braking"
        HARSH_ACCELERATION = "HARSH_ACCELERATION", "Harsh acceleration"
        SHARP_TURN = "SHARP_TURN", "Sharp turn"

    schema_version = models.CharField(max_length=8)
    event_id = models.CharField(max_length=128, unique=True)
    sequence_number = models.PositiveBigIntegerField()
    vehicle = models.ForeignKey(
        "fleet.Vehicle",
        on_delete=models.PROTECT,
        related_name="telemetry_events",
    )
    recorded_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    location = models.PointField(srid=4326)
    gnss_speed_kph = models.DecimalField(max_digits=6, decimal_places=2)
    rpm = models.PositiveIntegerField(null=True, blank=True)
    coolant_c = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    engine_load_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    driving_event = models.CharField(max_length=32, choices=DrivingEvent.choices)

    class Meta:
        ordering = ("-recorded_at", "-sequence_number", "-received_at", "-pk")
        indexes = [
            models.Index(
                fields=["vehicle", "-recorded_at", "-sequence_number", "-received_at"],
                name="tel_vehicle_latest_idx",
            ),
            models.Index(fields=["recorded_at"], name="tel_recorded_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(gnss_speed_kph__gte=0, gnss_speed_kph__lte=300),
                name="tel_speed_valid",
            ),
            models.CheckConstraint(
                condition=Q(rpm__isnull=True) | Q(rpm__gte=0, rpm__lte=12000),
                name="tel_rpm_valid",
            ),
            models.CheckConstraint(
                condition=Q(engine_load_pct__isnull=True)
                | Q(engine_load_pct__gte=0, engine_load_pct__lte=100),
                name="tel_load_valid",
            ),
        ]

    def __str__(self):
        return f"{self.vehicle.device_id}: {self.event_id}"


class Geofence(models.Model):
    class ShapeType(models.TextChoices):
        CIRCLE = "CIRCLE", "Circle"
        POLYGON = "POLYGON", "Custom polygon"

    class Category(models.TextChoices):
        DEPOT = "DEPOT", "Depot"
        CUSTOMER = "CUSTOMER", "Customer site"
        HOTEL = "HOTEL", "Hotel property"
        RESTRICTED = "RESTRICTED", "Restricted area"
        CUSTOM = "CUSTOM", "Custom"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.CUSTOM)
    shape_type = models.CharField(max_length=12, choices=ShapeType.choices)
    boundary = models.PolygonField(srid=4326)
    center = models.PointField(srid=4326)
    radius_meters = models.PositiveIntegerField(null=True, blank=True)
    color = models.CharField(max_length=7, default="#008F8C")
    show_on_map = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_geofences",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "pk")
        indexes = [models.Index(fields=["is_active", "show_on_map"], name="geofence_visible_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(radius_meters__isnull=True)
                | Q(radius_meters__gte=25, radius_meters__lte=5000),
                name="geofence_radius_valid",
            ),
        ]

    def __str__(self):
        return self.name


class GeofenceEvent(models.Model):
    class EventType(models.TextChoices):
        ENTER = "ENTER", "Entered"
        EXIT = "EXIT", "Exited"

    geofence = models.ForeignKey(Geofence, on_delete=models.CASCADE, related_name="events")
    vehicle = models.ForeignKey(
        "fleet.Vehicle", on_delete=models.PROTECT, related_name="geofence_events"
    )
    telemetry_event = models.ForeignKey(
        TelemetryEvent, on_delete=models.PROTECT, related_name="geofence_events"
    )
    event_type = models.CharField(max_length=8, choices=EventType.choices)
    occurred_at = models.DateTimeField()
    location = models.PointField(srid=4326)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-occurred_at", "-pk")
        indexes = [
            models.Index(fields=["geofence", "-occurred_at"], name="geofence_event_time_idx"),
            models.Index(fields=["vehicle", "-occurred_at"], name="geo_event_vehicle_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["geofence", "vehicle", "telemetry_event", "event_type"],
                name="unique_geofence_transition",
            ),
        ]

    def __str__(self):
        return f"{self.geofence}: {self.vehicle} {self.event_type}"
