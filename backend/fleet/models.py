from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models.functions import Lower


def validate_restricted_plate_digits(value):
    if not isinstance(value, list) or not value or any(
        not isinstance(digit, int) or isinstance(digit, bool) or digit < 0 or digit > 9
        for digit in value
    ):
        raise ValidationError("Restricted plate digits must be a non-empty list of integers 0-9.")
    if len(value) != len(set(value)):
        raise ValidationError("Restricted plate digits must not contain duplicates.")


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

    class FuelGrade(models.TextChoices):
        UNLEADED_91 = "UNLEADED_91", "Unleaded 91"
        PREMIUM_95 = "PREMIUM_95", "Premium 95"
        PREMIUM_97 = "PREMIUM_97", "Premium 97"
        REGULAR_DIESEL = "REGULAR_DIESEL", "Regular diesel"
        PREMIUM_DIESEL = "PREMIUM_DIESEL", "Premium diesel"

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

    device_id = models.CharField(
        max_length=64, unique=True, validators=[RegexValidator(r"^[A-Z0-9][A-Z0-9._-]{0,63}$")]
    )
    plate_number = models.CharField(max_length=32)
    display_name = models.CharField(max_length=120)
    vehicle_type = models.CharField(
        max_length=20, choices=VehicleType.choices, default=VehicleType.OTHER
    )
    manufacturer = models.CharField(max_length=120, blank=True, default="")
    model = models.CharField(max_length=120, blank=True, default="")
    model_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
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
    fuel_grade = models.CharField(
        max_length=20, choices=FuelGrade.choices, blank=True, default=""
    )
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
    photo = models.FileField(upload_to="vehicle_photos/%Y/%m/", null=True, blank=True)
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
                condition=models.Q(purchase_price__isnull=True) | models.Q(purchase_price__gte=0),
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
            "vin",
            "engine_number",
            "chassis_number",
            "color",
            "supplier_name",
            "purchase_order_number",
            "purchase_currency",
        ):
            value = getattr(self, field)
            normalized = (
                value.strip().upper() if field in {"vin", "purchase_currency"} else value.strip()
            )
            setattr(self, field, normalized)
        if self.pk:
            original = type(self).objects.only("device_id").get(pk=self.pk)
            if original.device_id != self.device_id:
                raise ValueError("device_id is immutable.")
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        allowed_grades = {
            self.FuelType.GASOLINE: {
                "",
                self.FuelGrade.UNLEADED_91,
                self.FuelGrade.PREMIUM_95,
                self.FuelGrade.PREMIUM_97,
            },
            self.FuelType.DIESEL: {
                "",
                self.FuelGrade.REGULAR_DIESEL,
                self.FuelGrade.PREMIUM_DIESEL,
            },
            "": {""},
        }
        if self.fuel_grade not in allowed_grades.get(self.fuel_type, set()):
            raise ValidationError(
                {"fuel_grade": "Fuel grade is not compatible with the selected fuel type."}
            )


class FuelPriceRecord(models.Model):
    class FuelType(models.TextChoices):
        DIESEL = Vehicle.FuelType.DIESEL, "Diesel"
        GASOLINE = Vehicle.FuelType.GASOLINE, "Gasoline"

    class Currency(models.TextChoices):
        PHP = "PHP", "Philippine peso"

    class SourceMode(models.TextChoices):
        EXTERNAL_CACHED = "EXTERNAL_CACHED", "External cached"
        MANUAL = "MANUAL", "Manual"

    fuel_type = models.CharField(max_length=20, choices=FuelType.choices)
    fuel_grade = models.CharField(
        max_length=20, choices=Vehicle.FuelGrade.choices, blank=True, default=""
    )
    price_per_liter = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    currency = models.CharField(
        max_length=3, choices=Currency.choices, default=Currency.PHP
    )
    effective_at = models.DateTimeField()
    retrieved_at = models.DateTimeField(auto_now_add=True)
    provider = models.CharField(max_length=160)
    source_mode = models.CharField(max_length=20, choices=SourceMode.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-effective_at", "-retrieved_at", "-pk")
        indexes = [
            models.Index(
                fields=(
                    "fuel_type",
                    "source_mode",
                    "-effective_at",
                    "-retrieved_at",
                    "-id",
                ),
                condition=models.Q(is_active=True),
                name="fuel_price_active_lookup_idx",
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(fuel_type__in=("DIESEL", "GASOLINE")),
                name="fuel_price_supported_type",
            ),
            models.CheckConstraint(
                condition=models.Q(currency="PHP"),
                name="fuel_price_php_currency",
            ),
            models.CheckConstraint(
                condition=models.Q(source_mode__in=("EXTERNAL_CACHED", "MANUAL")),
                name="fuel_price_source_mode",
            ),
            models.CheckConstraint(
                condition=models.Q(price_per_liter__gt=0),
                name="fuel_price_positive",
            ),
            models.CheckConstraint(
                condition=~models.Q(provider=""),
                name="fuel_price_provider_present",
            ),
        ]

    def __str__(self):
        return (
            f"{self.fuel_type}/{self.fuel_grade or 'GENERIC'} "
            f"{self.currency} {self.price_per_liter}/L "
            f"({self.source_mode})"
        )

    def clean_fields(self, exclude=None):
        if isinstance(self.price_per_liter, bool):
            raise ValidationError({"price_per_liter": "Enter a positive finite price."})
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        try:
            price = Decimal(str(self.price_per_liter))
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError(
                {"price_per_liter": "Enter a positive finite price."}
            ) from None
        if not price.is_finite() or price <= 0:
            raise ValidationError({"price_per_liter": "Enter a positive finite price."})
        allowed_grades = {
            self.FuelType.GASOLINE: {
                "",
                Vehicle.FuelGrade.UNLEADED_91,
                Vehicle.FuelGrade.PREMIUM_95,
                Vehicle.FuelGrade.PREMIUM_97,
            },
            self.FuelType.DIESEL: {
                "",
                Vehicle.FuelGrade.REGULAR_DIESEL,
                Vehicle.FuelGrade.PREMIUM_DIESEL,
            },
        }
        if self.fuel_grade not in allowed_grades.get(self.fuel_type, set()):
            raise ValidationError(
                {"fuel_grade": "Fuel grade is not compatible with the selected fuel type."}
            )


class VehicleFuelReferenceBaseline(models.Model):
    class Provenance(models.TextChoices):
        CAPSTONE_REFERENCE = "CAPSTONE_REFERENCE", "Capstone reference"

    vehicle = models.OneToOneField(
        Vehicle, on_delete=models.CASCADE, related_name="fuel_reference_baseline"
    )
    reference_fuel_rate_lph = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    provenance = models.CharField(
        max_length=32,
        choices=Provenance.choices,
        default=Provenance.CAPSTONE_REFERENCE,
    )
    basis_version = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("vehicle__device_id",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(reference_fuel_rate_lph__gt=0),
                name="fuel_reference_rate_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(provenance="CAPSTONE_REFERENCE"),
                name="fuel_reference_capstone_provenance",
            ),
        ]

    def __str__(self):
        return (
            f"{self.vehicle.device_id} {self.reference_fuel_rate_lph} L/h "
            f"({self.provenance})"
        )

class NumberCodingRule(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    authority = models.CharField(max_length=120)
    jurisdiction = models.CharField(max_length=120)
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    restricted_last_digits = models.JSONField(validators=[validate_restricted_plate_digits])
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    effective_from = models.DateField()
    effective_until = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    source_reference = models.CharField(max_length=300, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("weekday", "start_time", "pk")
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(start_time__isnull=True, end_time__isnull=True)
                           | models.Q(start_time__isnull=False, end_time__isnull=False)),
                name="fleet_coding_rule_time_pair",
            ),
            models.CheckConstraint(
                condition=(models.Q(effective_until__isnull=True)
                           | models.Q(effective_until__gte=models.F("effective_from"))),
                name="fleet_coding_rule_dates_valid",
            ),
        ]

    def __str__(self):
        return f"{self.authority} {self.jurisdiction} {self.get_weekday_display()}"


class NumberCodingSuspension(models.Model):
    authority = models.CharField(max_length=120)
    jurisdiction = models.CharField(max_length=120)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    reason = models.TextField()
    source_reference = models.CharField(max_length=300)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="number_coding_suspensions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-starts_at", "-pk")
        constraints = [models.CheckConstraint(
            condition=models.Q(ends_at__gt=models.F("starts_at")),
            name="fleet_coding_suspension_period_valid",
        )]

    def __str__(self):
        return f"{self.authority} suspension from {self.starts_at}"


class VehicleCodingExemption(models.Model):
    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.PROTECT, related_name="number_coding_exemptions"
    )
    authority = models.CharField(max_length=120)
    jurisdiction = models.CharField(max_length=120)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    reason = models.TextField()
    source_reference = models.CharField(max_length=300)
    is_active = models.BooleanField(default=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="verified_number_coding_exemptions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-starts_at", "-pk")
        constraints = [models.CheckConstraint(
            condition=models.Q(ends_at__gt=models.F("starts_at")),
            name="fleet_coding_exemption_period_valid",
        )]

    def __str__(self):
        return f"{self.vehicle} exemption from {self.starts_at}"


class VehicleInspection(models.Model):
    CHECKLIST_FIELDS = (
        "exterior_condition",
        "interior_condition",
        "tires_condition",
        "lights_condition",
        "brakes_condition",
        "fluids_condition",
        "safety_equipment_condition",
    )

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

    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="inspections")
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
                condition=models.Q(odometer_km__isnull=True) | models.Q(odometer_km__gte=0),
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


class VehicleMaintenanceRecord(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        SCHEDULED = "SCHEDULED", "Scheduled"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        INSPECTION = "INSPECTION", "Inspection"

    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.PROTECT, related_name="maintenance_records"
    )
    inspection = models.ForeignKey(
        VehicleInspection,
        on_delete=models.PROTECT,
        related_name="maintenance_records",
        null=True,
        blank=True,
    )
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    title = models.CharField(max_length=160)
    notes = models.TextField(blank=True, default="")
    scheduled_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="vehicle_maintenance_records",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = [
            models.Index(fields=["vehicle", "status"], name="fleet_maint_vehicle_status_idx")
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(status="SCHEDULED") | models.Q(scheduled_at__isnull=False),
                name="fleet_maint_scheduled_at_required",
            ),
            models.CheckConstraint(
                condition=models.Q(inspection__isnull=True, source="MANUAL")
                | models.Q(inspection__isnull=False, source="INSPECTION"),
                name="fleet_maint_source_matches_inspection",
            ),
        ]

    def __str__(self):
        return f"{self.vehicle.device_id} {self.title} ({self.status})"


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


class Driver(models.Model):
    class EmploymentStatus(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        ON_LEAVE = "ON_LEAVE", "On leave"
        SUSPENDED = "SUSPENDED", "Suspended"
        TERMINATED = "TERMINATED", "Terminated"

    class WorkShift(models.TextChoices):
        DAY = "DAY", "Day Shift"
        NIGHT = "NIGHT", "Night Shift"

    driver_code = models.CharField(max_length=64, unique=True)
    external_hr_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, default="")
    last_name = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=40, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    photo = models.FileField(upload_to="driver_photos/%Y/%m/", null=True, blank=True)
    employment_status = models.CharField(
        max_length=20,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.ACTIVE,
    )
    date_hired = models.DateField(null=True, blank=True)
    linked_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="driver_record",
        null=True,
        blank=True,
    )
    license_number = models.CharField(max_length=80, blank=True, default="")
    license_category = models.CharField(max_length=80, blank=True, default="")
    license_codes = models.CharField(max_length=160, blank=True, default="")
    license_issue_date = models.DateField(null=True, blank=True)
    license_expiry_date = models.DateField(null=True, blank=True)
    medical_certificate_expiry_date = models.DateField(null=True, blank=True)
    work_shift = models.CharField(
        max_length=10, choices=WorkShift.choices, default=WorkShift.DAY
    )
    weekly_rest_days = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("last_name", "first_name", "driver_code")

    def __str__(self):
        return f"{self.driver_code} ({self.first_name} {self.last_name})"

    def save(self, *args, **kwargs):
        self.driver_code = self.driver_code.strip().upper()
        self.external_hr_id = self.external_hr_id.strip() if self.external_hr_id else None
        for field in (
            "first_name",
            "middle_name",
            "last_name",
            "contact_number",
            "email",
            "license_number",
            "license_category",
            "license_codes",
        ):
            setattr(self, field, getattr(self, field).strip())
        super().save(*args, **kwargs)


class DriverDocument(models.Model):
    class DocumentType(models.TextChoices):
        DRIVER_LICENSE = "DRIVER_LICENSE", "Driver license"
        MEDICAL_CERTIFICATE = "MEDICAL_CERTIFICATE", "Medical certificate"
        TRAINING_CERTIFICATE = "TRAINING_CERTIFICATE", "Training certificate"
        OTHER = "OTHER", "Other"

    driver = models.ForeignKey(Driver, on_delete=models.PROTECT, related_name="documents")
    document_type = models.CharField(max_length=30, choices=DocumentType.choices)
    title = models.CharField(max_length=160)
    reference_number = models.CharField(max_length=100, blank=True, default="")
    issuer_name = models.CharField(max_length=160, blank=True, default="")
    issued_date = models.DateField(null=True, blank=True)
    effective_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    file = models.FileField(upload_to="driver_documents/%Y/%m/")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="driver_documents",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return f"{self.driver.driver_code} {self.title}"


class DriverSafetyDemoProfile(models.Model):
    class Source(models.TextChoices):
        DEMO_SEED = "DEMO_SEED", "Demo seed"

    driver = models.OneToOneField(
        Driver, on_delete=models.CASCADE, related_name="safety_demo_profile"
    )
    safety_score = models.PositiveSmallIntegerField()
    completed_trip_count = models.PositiveSmallIntegerField()
    driving_hours = models.DecimalField(max_digits=5, decimal_places=1)
    safety_event_count = models.PositiveSmallIntegerField()
    source = models.CharField(max_length=20, choices=Source.choices)
    generated_at = models.DateTimeField()

    class Meta:
        ordering = ("driver__driver_code",)


class DriverSafetyDemoEvent(models.Model):
    class EventType(models.TextChoices):
        HARSH_ACCELERATION = "HARSH_ACCELERATION", "Harsh Acceleration"
        HARSH_BRAKING = "HARSH_BRAKING", "Harsh Braking"
        SHARP_TURN = "SHARP_TURN", "Sharp Turn"

    profile = models.ForeignKey(
        DriverSafetyDemoProfile, on_delete=models.CASCADE, related_name="events"
    )
    sequence = models.PositiveSmallIntegerField()
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    occurred_at = models.DateTimeField()
    source = models.CharField(
        max_length=20,
        choices=DriverSafetyDemoProfile.Source.choices,
        default=DriverSafetyDemoProfile.Source.DEMO_SEED,
    )

    class Meta:
        ordering = ("-occurred_at", "-pk")
        constraints = [
            models.UniqueConstraint(
                fields=("profile", "sequence"), name="unique_demo_safety_event_sequence"
            )
        ]
