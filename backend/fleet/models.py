from django.conf import settings
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

    class FuelType(models.TextChoices):
        GASOLINE = "GASOLINE", "Gasoline"
        DIESEL = "DIESEL", "Diesel"
        HYBRID = "HYBRID", "Hybrid"
        ELECTRIC = "ELECTRIC", "Electric"
        OTHER = "OTHER", "Other"

    class TransmissionType(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        AUTOMATIC = "AUTOMATIC", "Automatic"
        CVT = "CVT", "CVT"
        OTHER = "OTHER", "Other"

    class OwnershipType(models.TextChoices):
        COMPANY_OWNED = "COMPANY_OWNED", "Company owned"
        LEASED = "LEASED", "Leased"
        RENTED = "RENTED", "Rented"
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
    payload_capacity_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    gvwr_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    vin = models.CharField(max_length=64, blank=True, default="")
    engine_number = models.CharField(max_length=64, blank=True, default="")
    chassis_number = models.CharField(max_length=64, blank=True, default="")
    color = models.CharField(max_length=64, blank=True, default="")
    fuel_type = models.CharField(max_length=20, choices=FuelType.choices, blank=True, default="")
    transmission_type = models.CharField(
        max_length=20, choices=TransmissionType.choices, blank=True, default=""
    )
    ownership_type = models.CharField(
        max_length=20, choices=OwnershipType.choices, blank=True, default=""
    )
    supplier_name = models.CharField(max_length=160, blank=True, default="")
    purchase_order_number = models.CharField(max_length=80, blank=True, default="")
    acquisition_date = models.DateField(null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    purchase_currency = models.CharField(max_length=3, blank=True, default="")
    warranty_expiry_date = models.DateField(null=True, blank=True)
    registration_expiry_date = models.DateField(null=True, blank=True)
    insurance_expiry_date = models.DateField(null=True, blank=True)
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
            models.CheckConstraint(
                condition=models.Q(purchase_price__isnull=True)
                | models.Q(purchase_price__gte=0),
                name="fleet_vehicle_purchase_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(payload_capacity_kg__isnull=True)
                | models.Q(payload_capacity_kg__gte=0),
                name="fleet_vehicle_payload_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(gvwr_kg__isnull=True) | models.Q(gvwr_kg__gte=0),
                name="fleet_vehicle_gvwr_nonnegative",
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
        for field in (
            "vin", "engine_number", "chassis_number", "color", "supplier_name",
            "purchase_order_number", "purchase_currency",
        ):
            value = getattr(self, field)
            normalized = (
                value.strip().upper()
                if field in {"vin", "purchase_currency"}
                else value.strip()
            )
            setattr(self, field, normalized)
        if self.pk:
            original = type(self).objects.only("device_id").get(pk=self.pk)
            if original.device_id != self.device_id:
                raise ValueError("device_id is immutable.")
        super().save(*args, **kwargs)


class VehicleInspection(models.Model):
    class InspectionType(models.TextChoices):
        PRE_TRIP = "PRE_TRIP", "Pre-trip"
        POST_TRIP = "POST_TRIP", "Post-trip"
        PERIODIC = "PERIODIC", "Periodic"

    class Result(models.TextChoices):
        PASSED = "PASSED", "Passed"
        NEEDS_ATTENTION = "NEEDS_ATTENTION", "Needs attention"
        FAILED = "FAILED", "Failed"

    class Condition(models.TextChoices):
        OK = "OK", "OK"
        NEEDS_ATTENTION = "NEEDS_ATTENTION", "Needs attention"
        NOT_CHECKED = "NOT_CHECKED", "Not checked"

    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.PROTECT, related_name="inspections"
    )
    inspection_date = models.DateField()
    inspection_type = models.CharField(max_length=20, choices=InspectionType.choices)
    result = models.CharField(max_length=20, choices=Result.choices)
    odometer_km = models.PositiveIntegerField(null=True, blank=True)
    fuel_level_percent = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    exterior_condition = models.CharField(max_length=20, choices=Condition.choices)
    interior_condition = models.CharField(max_length=20, choices=Condition.choices)
    tires_condition = models.CharField(max_length=20, choices=Condition.choices)
    lights_condition = models.CharField(max_length=20, choices=Condition.choices)
    brakes_condition = models.CharField(max_length=20, choices=Condition.choices)
    fluids_condition = models.CharField(max_length=20, choices=Condition.choices)
    safety_equipment_condition = models.CharField(max_length=20, choices=Condition.choices)
    notes = models.TextField(blank=True, default="")
    issues_found = models.TextField(blank=True, default="")
    inspected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="vehicle_inspections",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-inspection_date", "-created_at", "-pk")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(odometer_km__isnull=True)
                | models.Q(odometer_km__gte=0),
                name="fleet_inspection_odometer_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(fuel_level_percent__isnull=True)
                | models.Q(fuel_level_percent__range=(0, 100)),
                name="fleet_inspection_fuel_range",
            ),
        ]

    def __str__(self):
        return f"{self.vehicle.device_id} {self.inspection_date} {self.result}"


class VehicleDocument(models.Model):
    class DocumentType(models.TextChoices):
        OFFICIAL_RECEIPT = "OFFICIAL_RECEIPT", "Official receipt"
        CERTIFICATE_OF_REGISTRATION = "CERTIFICATE_OF_REGISTRATION", "Certificate of registration"
        INSURANCE = "INSURANCE", "Insurance"
        PURCHASE_ORDER = "PURCHASE_ORDER", "Purchase order"
        SALES_INVOICE = "SALES_INVOICE", "Sales invoice"
        WARRANTY = "WARRANTY", "Warranty"
        LEASE_AGREEMENT = "LEASE_AGREEMENT", "Lease agreement"
        EMISSION_CERTIFICATE = "EMISSION_CERTIFICATE", "Emission certificate"
        PMVIC_CERTIFICATE = "PMVIC_CERTIFICATE", "PMVIC certificate"
        VEHICLE_PHOTO = "VEHICLE_PHOTO", "Vehicle photo"
        OTHER = "OTHER", "Other"

    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="documents")
    document_type = models.CharField(max_length=40, choices=DocumentType.choices)
    title = models.CharField(max_length=160)
    reference_number = models.CharField(max_length=100, blank=True, default="")
    issuer_name = models.CharField(max_length=160, blank=True, default="")
    effective_date = models.DateField(null=True, blank=True)
    issued_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    file = models.FileField(upload_to="vehicle_documents/%Y/%m/")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="vehicle_documents"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return f"{self.vehicle.device_id} {self.title}"
