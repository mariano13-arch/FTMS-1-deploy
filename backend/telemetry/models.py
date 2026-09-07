import uuid

from django.conf import settings
from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db.models import Q


class TelemetryDevice(models.Model):
    class RegistrationStatus(models.TextChoices):
        REGISTERED = "REGISTERED", "Registered"
        RETIRED = "RETIRED", "Retired"

    device_id = models.CharField(
        max_length=64,
        unique=True,
        validators=[RegexValidator(r"^[A-Z0-9][A-Z0-9._-]{0,63}$")],
    )
    registration_status = models.CharField(
        max_length=16,
        choices=RegistrationStatus.choices,
        default=RegistrationStatus.REGISTERED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("device_id",)
        constraints = [
            models.CheckConstraint(
                condition=Q(device_id__regex=r"^[A-Z0-9][A-Z0-9._-]{0,63}$"),
                name="telemetry_device_id_format",
            )
        ]

    def save(self, *args, **kwargs):
        self.device_id = self.device_id.strip()
        if self.pk:
            original = type(self).objects.only("device_id").get(pk=self.pk)
            if original.device_id != self.device_id:
                raise ValueError("device_id is immutable.")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.device_id


class TelemetryDeviceBinding(models.Model):
    device = models.ForeignKey(
        TelemetryDevice,
        on_delete=models.PROTECT,
        related_name="bindings",
    )
    vehicle = models.ForeignKey(
        "fleet.Vehicle",
        on_delete=models.PROTECT,
        related_name="telemetry_device_bindings",
    )
    paired_at = models.DateTimeField()
    unpaired_at = models.DateTimeField(null=True, blank=True)
    paired_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="telemetry_device_pairings",
    )
    unpaired_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="telemetry_device_unpairings",
    )

    class Meta:
        ordering = ("-paired_at", "-pk")
        constraints = [
            models.UniqueConstraint(
                fields=("device",),
                condition=Q(unpaired_at__isnull=True),
                name="telemetry_one_active_vehicle_per_device",
            ),
            models.UniqueConstraint(
                fields=("vehicle",),
                condition=Q(unpaired_at__isnull=True),
                name="telemetry_one_active_device_per_vehicle",
            ),
            models.CheckConstraint(
                condition=Q(unpaired_at__isnull=True) | Q(unpaired_at__gte=models.F("paired_at")),
                name="telemetry_binding_dates_ordered",
            ),
        ]

    def __str__(self):
        return f"{self.device.device_id} -> {self.vehicle.plate_number}"


class TelemetryEvent(models.Model):
    class ObdSource(models.TextChoices):
        SIMULATED_TEST = "SIMULATED_TEST", "Simulated test"
        PHYSICAL_OBD = "PHYSICAL_OBD", "Physical OBD"

    class PositionSource(models.TextChoices):
        GNSS = "GNSS", "GNSS"
        CELLULAR_LBS = "CELLULAR_LBS", "Cellular LBS"

    class DrivingEvent(models.TextChoices):
        NORMAL = "NORMAL", "Normal"
        HARSH_BRAKING = "HARSH_BRAKING", "Harsh braking"
        HARSH_ACCELERATION = "HARSH_ACCELERATION", "Harsh acceleration"
        SHARP_TURN = "SHARP_TURN", "Sharp turn"

    schema_version = models.CharField(max_length=8)
    event_id = models.CharField(max_length=128, unique=True)
    sequence_number = models.PositiveBigIntegerField()
    device = models.ForeignKey(
        TelemetryDevice,
        on_delete=models.PROTECT,
        related_name="telemetry_events",
    )
    vehicle = models.ForeignKey(
        "fleet.Vehicle",
        on_delete=models.PROTECT,
        related_name="telemetry_events",
    )
    recorded_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    location = models.PointField(srid=4326)
    position_source = models.CharField(
        max_length=16, choices=PositionSource.choices, default=PositionSource.GNSS
    )
    position_accuracy_m = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    gnss_speed_kph = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    rpm = models.PositiveIntegerField(null=True, blank=True)
    coolant_c = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    engine_load_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    obd_source = models.CharField(
        max_length=16, choices=ObdSource.choices, null=True, blank=True
    )
    driving_event = models.CharField(
        max_length=32, choices=DrivingEvent.choices, null=True, blank=True
    )

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
                condition=Q(gnss_speed_kph__isnull=True)
                | Q(gnss_speed_kph__gte=0, gnss_speed_kph__lte=300),
                name="tel_speed_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(position_source="GNSS", gnss_speed_kph__isnull=False)
                    | Q(
                        position_source="CELLULAR_LBS",
                        gnss_speed_kph__isnull=True,
                        position_accuracy_m__gt=0,
                    )
                ),
                name="tel_position_source_valid",
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
            models.CheckConstraint(
                condition=~Q(schema_version="1.2")
                | Q(obd_source__isnull=False)
                | Q(rpm__isnull=True, coolant_c__isnull=True, engine_load_pct__isnull=True),
                name="tel_v12_obd_source_required",
            ),
        ]

    def __str__(self):
        return f"{self.device.device_id}: {self.event_id}"

    def clean(self):
        super().clean()
        errors = {}
        if self.position_source == self.PositionSource.GNSS and self.gnss_speed_kph is None:
            errors["gnss_speed_kph"] = "GNSS positions require GNSS speed."
        if self.position_source == self.PositionSource.CELLULAR_LBS:
            if self.gnss_speed_kph is not None:
                errors["gnss_speed_kph"] = "Cellular LBS positions must not include GNSS speed."
            if self.position_accuracy_m is None or self.position_accuracy_m <= 0:
                errors["position_accuracy_m"] = "Cellular LBS positions require positive accuracy."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.device_id is None and self.vehicle_id is not None:
            binding = TelemetryDeviceBinding.objects.filter(
                vehicle_id=self.vehicle_id,
                unpaired_at__isnull=True,
            ).only("device_id").first()
            if binding is None:
                raise ValueError("Vehicle has no active telemetry device binding.")
            self.device_id = binding.device_id
        super().save(*args, **kwargs)


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
