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
