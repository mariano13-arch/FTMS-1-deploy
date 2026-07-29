from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models.functions import Lower


class Vehicle(models.Model):
    class VehicleType(models.TextChoices):
        SEDAN = "SEDAN", "Sedan"
        SUV = "SUV", "SUV"
        VAN = "VAN", "Van"
        SHUTTLE_BUS = "SHUTTLE_BUS", "Shuttle bus"
        SERVICE_TRUCK = "SERVICE_TRUCK", "Service truck"
        MOTORCYCLE = "MOTORCYCLE", "Motorcycle"
        OTHER = "OTHER", "Other"

    device_id = models.CharField(max_length=64, unique=True, validators=[
        RegexValidator(r"^[A-Z0-9][A-Z0-9._-]{0,63}$")
    ])
    plate_number = models.CharField(max_length=32)
    display_name = models.CharField(max_length=120)
    vehicle_type = models.CharField(
        max_length=20, choices=VehicleType.choices, default=VehicleType.OTHER
    )
    manufacturer = models.CharField(max_length=120, blank=True, default="")
    model = models.CharField(max_length=120, blank=True, default="")
    model_year = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1980)],
    )
    passenger_capacity = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("device_id",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(device_id__regex=r"^[A-Z0-9][A-Z0-9._-]{0,63}$"),
                name="fleet_vehicle_device_id_format",
            ),
            models.UniqueConstraint(Lower("plate_number"), name="fleet_vehicle_plate_ci_unique"),
            models.CheckConstraint(
                condition=models.Q(model_year__isnull=True) | models.Q(model_year__gte=1980),
                name="fleet_vehicle_model_year_min",
            ),
            models.CheckConstraint(
                condition=models.Q(passenger_capacity__isnull=True)
                | models.Q(passenger_capacity__range=(1, 100)),
                name="fleet_vehicle_capacity_range",
            ),
        ]

    def __str__(self):
        return f"{self.device_id} ({self.plate_number})"

    def save(self, *args, **kwargs):
        self.device_id = self.device_id.strip()
        self.plate_number = self.plate_number.strip().upper()
        self.display_name = self.display_name.strip()
        self.manufacturer = self.manufacturer.strip()
        self.model = self.model.strip()
        if self.pk:
            original = type(self).objects.only("device_id").get(pk=self.pk)
            if original.device_id != self.device_id:
                raise ValueError("device_id is immutable.")
        super().save(*args, **kwargs)
