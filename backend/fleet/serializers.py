from datetime import UTC, datetime, timedelta

from django.db.models.functions import Lower
from django.utils import timezone
from rest_framework import serializers

from telemetry.models import TelemetryEvent

from .maintenance import ALLOWED_TRANSITIONS
from .models import (
    Driver,
    DriverDocument,
    DriverSafetyDemoProfile,
    NumberCodingRule,
    NumberCodingSuspension,
    Vehicle,
    VehicleCodingExemption,
    VehicleDocument,
    VehicleInspection,
    VehicleMaintenanceRecord,
)
from .safety import DriverSafetyMetrics, safety_metrics_for_drivers
from .schedules import compact_driver_name, evaluate_driver_schedule


class VehicleInspectionSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleInspection
        fields = ["id", "inspection_date", "inspection_type", "result"]


class StrictFieldsMixin:
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected a JSON object.")
        unknown = set(data.keys()) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {field: ["Unknown field."] for field in sorted(unknown)}
            )
        return super().to_internal_value(data)


class NumberCodingRuleSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    weekday_label = serializers.CharField(source="get_weekday_display", read_only=True)

    class Meta:
        model = NumberCodingRule
        fields = [
            "id", "authority", "jurisdiction", "weekday", "weekday_label",
            "restricted_last_digits", "start_time", "end_time", "effective_from",
            "effective_until", "is_active", "source_reference", "notes", "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "weekday_label", "created_at", "updated_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        start = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if (start is None) != (end is None):
            raise serializers.ValidationError(
                {"time_window": "Start and end time must both be provided or both be blank."}
            )
        if start is not None and start >= end:
            raise serializers.ValidationError({"end_time": "End time must be after start time."})
        effective_from = attrs.get(
            "effective_from", getattr(self.instance, "effective_from", None)
        )
        effective_until = attrs.get(
            "effective_until", getattr(self.instance, "effective_until", None)
        )
        if effective_until and effective_from and effective_until < effective_from:
            raise serializers.ValidationError(
                {"effective_until": "Effective until must not precede effective from."}
            )
        return attrs


class NumberCodingSuspensionSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = NumberCodingSuspension
        fields = [
            "id", "authority", "jurisdiction", "starts_at", "ends_at", "reason",
            "source_reference", "is_active", "created_by", "created_by_name", "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "created_by", "created_by_name", "created_at", "updated_at",
        ]

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name().strip() or obj.created_by.username

    def validate(self, attrs):
        attrs = super().validate(attrs)
        starts_at = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        ends_at = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if starts_at and ends_at and starts_at >= ends_at:
            raise serializers.ValidationError({"ends_at": "End must be after start."})
        return attrs


class VehicleCodingExemptionSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    vehicle_display_name = serializers.CharField(source="vehicle.display_name", read_only=True)
    plate_number = serializers.CharField(source="vehicle.plate_number", read_only=True)
    verified_by_name = serializers.SerializerMethodField()

    class Meta:
        model = VehicleCodingExemption
        fields = [
            "id", "vehicle", "vehicle_display_name", "plate_number", "authority",
            "jurisdiction", "starts_at", "ends_at", "reason", "source_reference",
            "is_active", "verified_by", "verified_by_name", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "vehicle_display_name", "plate_number", "verified_by", "verified_by_name",
            "created_at", "updated_at",
        ]

    def get_verified_by_name(self, obj):
        return obj.verified_by.get_full_name().strip() or obj.verified_by.username

    def validate(self, attrs):
        attrs = super().validate(attrs)
        starts_at = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        ends_at = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if starts_at and ends_at and starts_at >= ends_at:
            raise serializers.ValidationError({"ends_at": "End must be after start."})
        return attrs


class VehicleSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    latest_inspection = serializers.SerializerMethodField()
    document_count = serializers.SerializerMethodField()
    document_health = serializers.SerializerMethodField()
    current_telemetry_device = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = [
            "id",
            "device_id",
            "plate_number",
            "display_name",
            "vehicle_type",
            "manufacturer",
            "model",
            "model_year",
            "passenger_capacity",
            "payload_capacity_kg",
            "gvwr_kg",
            "vin",
            "engine_number",
            "chassis_number",
            "color",
            "fuel_type",
            "fuel_grade",
            "transmission_type",
            "ownership_type",
            "supplier_name",
            "purchase_order_number",
            "acquisition_date",
            "purchase_price",
            "purchase_currency",
            "warranty_expiry_date",
            "registration_expiry_date",
            "insurance_expiry_date",
            "photo",
            "photo_url",
            "is_active",
            "created_at",
            "updated_at",
            "latest_inspection",
            "document_count",
            "document_health",
            "current_telemetry_device",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "latest_inspection",
            "document_count",
            "document_health",
            "current_telemetry_device",
            "photo_url",
        ]
        extra_kwargs = {"photo": {"write_only": True, "required": False}}

    def get_photo_url(self, obj):
        return f"/api/v1/vehicles/{obj.device_id}/photo/" if obj.photo else None

    def validate_photo(self, value):
        allowed_types = {"image/jpeg", "image/png", "image/webp"}
        allowed_extensions = {"jpg", "jpeg", "png", "webp"}
        extension = value.name.rsplit(".", 1)[-1].lower() if "." in value.name else ""
        if value.content_type not in allowed_types or extension not in allowed_extensions:
            raise serializers.ValidationError("Only JPG, JPEG, PNG, and WebP files are allowed.")
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Photo must not exceed 5 MB.")
        return value

    def update(self, instance, validated_data):
        old_photo = instance.photo if "photo" in validated_data else None
        updated = super().update(instance, validated_data)
        if old_photo and old_photo.name != updated.photo.name:
            old_photo.delete(save=False)
        return updated

    def get_current_telemetry_device(self, obj):
        bindings = getattr(obj, "current_telemetry_device_bindings", None)
        binding = (
            next(iter(bindings), None)
            if bindings is not None
            else obj.telemetry_device_bindings.select_related("device")
            .filter(unpaired_at__isnull=True)
            .first()
        )
        if binding is None:
            return None
        return {
            "device_id": binding.device.device_id,
            "registration_status": binding.device.registration_status,
        }

    def get_latest_inspection(self, obj):
        inspection = next(iter(obj.inspections.all()), None)
        return (
            VehicleInspectionSummarySerializer(inspection).data if inspection is not None else None
        )

    def get_document_count(self, obj):
        annotated = getattr(obj, "document_count", None)
        return annotated if annotated is not None else obj.documents.count()

    def get_document_health(self, obj):
        required = {
            VehicleDocument.DocumentType.OFFICIAL_RECEIPT,
            VehicleDocument.DocumentType.CERTIFICATE_OF_REGISTRATION,
            VehicleDocument.DocumentType.INSURANCE,
            VehicleDocument.DocumentType.EMISSION_CERTIFICATE,
            VehicleDocument.DocumentType.PMVIC_CERTIFICATE,
        }
        latest_by_type = {}
        for document in obj.documents.all():
            if document.document_type not in required:
                continue
            relevant_date = (
                document.effective_date
                or document.issued_date
                or timezone.localtime(document.created_at).date()
            )
            candidate = (relevant_date, document.pk, document)
            current = latest_by_type.get(document.document_type)
            if current is None or candidate[:2] > current[:2]:
                latest_by_type[document.document_type] = candidate

        latest_documents = [candidate[2] for candidate in latest_by_type.values()]
        today = timezone.localdate()
        if any(
            document.expiry_date is not None and document.expiry_date < today
            for document in latest_documents
        ):
            return "EXPIRED"
        if set(latest_by_type) != required:
            return "INCOMPLETE"
        if any(
            document.expiry_date is not None and document.expiry_date <= today + timedelta(days=30)
            for document in latest_documents
        ):
            return "EXPIRING_SOON"
        return "CURRENT"

    def validate_device_id(self, value):
        if self.instance is not None:
            raise serializers.ValidationError("This field is immutable.")
        return value

    def validate_plate_number(self, value):
        value = value.strip().upper()
        query = Vehicle.objects.annotate(normalized=Lower("plate_number")).filter(
            normalized=value.lower()
        )
        if self.instance:
            query = query.exclude(pk=self.instance.pk)
        if query.exists():
            raise serializers.ValidationError("A vehicle with this plate number already exists.")
        return value

    def validate_model_year(self, value):
        if value is not None and not 1980 <= value <= datetime.now(UTC).year + 1:
            raise serializers.ValidationError("Must be between 1980 and next year.")
        return value

    def validate(self, attrs):
        for field in (
            "display_name",
            "manufacturer",
            "model",
            "vin",
            "engine_number",
            "chassis_number",
            "color",
            "supplier_name",
            "purchase_order_number",
            "purchase_currency",
        ):
            if field in attrs:
                value = attrs[field].strip()
                attrs[field] = value.upper() if field in {"vin", "purchase_currency"} else value
        errors = {}
        for field in (
            "id",
            "created_at",
            "updated_at",
            "latest_inspection",
            "document_count",
            "document_health",
            "current_telemetry_device",
            "photo_url",
        ):
            if field in self.initial_data:
                errors[field] = "This field is not accepted."
        string_fields = (
            "device_id",
            "plate_number",
            "display_name",
            "vehicle_type",
            "manufacturer",
            "model",
            "vin",
            "engine_number",
            "chassis_number",
            "color",
            "fuel_type",
            "fuel_grade",
            "transmission_type",
            "ownership_type",
            "supplier_name",
            "purchase_order_number",
            "purchase_currency",
        )
        request = self.context.get("request")
        enforce_json_types = request is None or request.content_type == "application/json"
        for field in string_fields:
            if (
                enforce_json_types
                and field in self.initial_data
                and not isinstance(self.initial_data[field], str)
            ):
                errors[field] = "Must be a string."
        for field in ("model_year", "passenger_capacity"):
            value = self.initial_data.get(field)
            if (
                enforce_json_types
                and field in self.initial_data
                and value is not None
                and (not isinstance(value, int) or isinstance(value, bool))
            ):
                errors[field] = "Must be an integer or null."
        for field in ("payload_capacity_kg", "gvwr_kg"):
            value = self.initial_data.get(field)
            if (
                enforce_json_types
                and field in self.initial_data
                and value is not None
                and isinstance(value, bool)
            ):
                errors[field] = "Must be a decimal number or null."
        if self.instance is None and "is_active" in self.initial_data:
            errors["is_active"] = "This field is not accepted."
        if self.instance is not None:
            if "device_id" in self.initial_data:
                errors["device_id"] = "This field is immutable."
            if "is_active" in self.initial_data:
                errors["is_active"] = "Use the status action."
        fuel_type = attrs.get(
            "fuel_type", getattr(self.instance, "fuel_type", "")
        )
        fuel_grade = attrs.get(
            "fuel_grade", getattr(self.instance, "fuel_grade", "")
        )
        allowed_grades = {
            Vehicle.FuelType.GASOLINE: {
                "",
                Vehicle.FuelGrade.UNLEADED_91,
                Vehicle.FuelGrade.PREMIUM_95,
                Vehicle.FuelGrade.PREMIUM_97,
            },
            Vehicle.FuelType.DIESEL: {
                "",
                Vehicle.FuelGrade.REGULAR_DIESEL,
                Vehicle.FuelGrade.PREMIUM_DIESEL,
            },
            "": {""},
        }
        if fuel_grade not in allowed_grades.get(fuel_type, set()):
            errors["fuel_grade"] = (
                "Fuel grade is not compatible with the selected fuel type. "
                "Explicitly clear or replace it."
            )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class VehicleDocumentSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = VehicleDocument
        fields = [
            "id",
            "vehicle",
            "document_type",
            "title",
            "reference_number",
            "issuer_name",
            "issued_date",
            "effective_date",
            "expiry_date",
            "file",
            "file_name",
            "download_url",
            "uploaded_by",
            "uploaded_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "vehicle",
            "file_name",
            "download_url",
            "uploaded_by",
            "uploaded_by_name",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"file": {"write_only": True}}

    def get_uploaded_by_name(self, obj):
        return obj.uploaded_by.get_full_name().strip() or obj.uploaded_by.username

    def get_file_name(self, obj):
        return obj.file.name.rsplit("/", 1)[-1]

    def get_download_url(self, obj):
        return f"/api/v1/vehicles/{obj.vehicle.device_id}/documents/{obj.pk}/file/"

    def validate_file(self, value):
        allowed_types = {"application/pdf", "image/jpeg", "image/png"}
        allowed_extensions = {"pdf", "jpg", "jpeg", "png"}
        extension = value.name.rsplit(".", 1)[-1].lower() if "." in value.name else ""
        if value.content_type not in allowed_types or extension not in allowed_extensions:
            raise serializers.ValidationError("Only PDF, JPG, JPEG, and PNG files are allowed.")
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("File must not exceed 5 MB.")
        return value

    def validate(self, attrs):
        errors = {}
        for field in self.Meta.read_only_fields:
            if field in self.initial_data:
                errors[field] = "This field is not accepted."
        for field in ("title", "reference_number", "issuer_name"):
            if field in attrs:
                attrs[field] = attrs[field].strip()
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class VehicleInspectionSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    inspector_name = serializers.SerializerMethodField()

    class Meta:
        model = VehicleInspection
        fields = [
            "id",
            "vehicle",
            "inspection_date",
            "inspection_type",
            "result",
            "odometer_km",
            "fuel_level_percent",
            "exterior_condition",
            "interior_condition",
            "tires_condition",
            "lights_condition",
            "brakes_condition",
            "fluids_condition",
            "safety_equipment_condition",
            "notes",
            "issues_found",
            "inspected_by",
            "inspector_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "vehicle",
            "inspected_by",
            "inspector_name",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"inspection_date": {"required": False}}

    def get_inspector_name(self, obj):
        return obj.inspected_by.get_full_name().strip() or obj.inspected_by.username

    def validate(self, attrs):
        errors = {}
        for field in self.Meta.read_only_fields:
            if field in self.initial_data:
                errors[field] = "This field is not accepted."
        for field in ("notes", "issues_found"):
            if field in attrs:
                attrs[field] = attrs[field].strip()
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class VehicleMaintenanceRecordSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    vehicle = serializers.SerializerMethodField()
    vehicle_device_id = serializers.CharField(write_only=True, max_length=64)
    inspection = VehicleInspectionSummarySerializer(read_only=True)
    inspection_id = serializers.PrimaryKeyRelatedField(
        source="inspection",
        queryset=VehicleInspection.objects.select_related("vehicle"),
        required=False,
        allow_null=True,
        write_only=True,
    )
    created_by_name = serializers.SerializerMethodField()
    allowed_transitions = serializers.SerializerMethodField()

    class Meta:
        model = VehicleMaintenanceRecord
        fields = [
            "id",
            "vehicle",
            "vehicle_device_id",
            "inspection",
            "inspection_id",
            "source",
            "status",
            "title",
            "notes",
            "scheduled_at",
            "started_at",
            "completed_at",
            "created_by",
            "created_by_name",
            "allowed_transitions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "vehicle",
            "source",
            "status",
            "scheduled_at",
            "started_at",
            "completed_at",
            "created_by",
            "created_by_name",
            "allowed_transitions",
            "created_at",
            "updated_at",
        ]

    def get_vehicle(self, record):
        return {
            "id": record.vehicle_id,
            "device_id": record.vehicle.device_id,
            "display_name": record.vehicle.display_name,
            "plate_number": record.vehicle.plate_number,
        }

    def get_created_by_name(self, record):
        return record.created_by.get_full_name().strip() or record.created_by.username

    def get_allowed_transitions(self, record):
        return sorted(ALLOWED_TRANSITIONS.get(record.status, set()))

    def validate(self, attrs):
        errors = {}
        for field in self.Meta.read_only_fields:
            if field in self.initial_data:
                errors[field] = "This field is not accepted."
        device_id = attrs.pop("vehicle_device_id", "")
        vehicle = Vehicle.objects.filter(device_id=device_id).first()
        if vehicle is None:
            errors["vehicle_device_id"] = "Vehicle was not found."
        inspection = attrs.get("inspection")
        if vehicle is not None and inspection is not None and inspection.vehicle_id != vehicle.pk:
            errors["inspection_id"] = "Inspection must belong to the selected vehicle."
        for field in ("title", "notes"):
            if field in attrs:
                attrs[field] = attrs[field].strip()
        if not attrs.get("title"):
            errors["title"] = "This field may not be blank."
        if errors:
            raise serializers.ValidationError(errors)
        attrs["vehicle"] = vehicle
        attrs["source"] = (
            VehicleMaintenanceRecord.Source.INSPECTION
            if inspection is not None
            else VehicleMaintenanceRecord.Source.MANUAL
        )
        return attrs


class MaintenanceTransitionSerializer(StrictFieldsMixin, serializers.Serializer):
    status = serializers.ChoiceField(choices=VehicleMaintenanceRecord.Status.choices)
    scheduled_at = serializers.DateTimeField(required=False, allow_null=True)


def driver_eligibility(driver):
    today = timezone.localdate()
    reasons = []
    if driver.employment_status != Driver.EmploymentStatus.ACTIVE:
        reasons.append(f"Employment status is {driver.get_employment_status_display()}")
    if driver.license_expiry_date and driver.license_expiry_date < today:
        reasons.append("Driver license has expired")
    if driver.medical_certificate_expiry_date and driver.medical_certificate_expiry_date < today:
        reasons.append("Medical certificate has expired")
    if reasons:
        return "NOT_ELIGIBLE", reasons
    if not driver.license_number:
        reasons.append("Driver license number is missing")
    if not driver.license_expiry_date:
        reasons.append("Driver license expiry is missing")
    if not driver.medical_certificate_expiry_date:
        reasons.append("Medical certificate expiry is missing")
    return ("RESTRICTED", reasons) if reasons else ("ELIGIBLE", [])


class DriverSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    linked_user_display = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()
    eligibility_status = serializers.SerializerMethodField()
    eligibility_reasons = serializers.SerializerMethodField()
    safety_score = serializers.SerializerMethodField()
    safety_score_status = serializers.SerializerMethodField()
    safety_score_eligible = serializers.SerializerMethodField()
    safety_completed_trips = serializers.SerializerMethodField()
    safety_driving_hours = serializers.SerializerMethodField()
    safety_event_count = serializers.SerializerMethodField()
    safety_events_per_hour = serializers.SerializerMethodField()
    safety_event_counts = serializers.SerializerMethodField()
    safety_score_source = serializers.SerializerMethodField()
    safety_history = serializers.SerializerMethodField()
    shift_label = serializers.CharField(source="get_work_shift_display", read_only=True)
    shift_hours = serializers.SerializerMethodField()
    schedule_status = serializers.SerializerMethodField()

    class Meta:
        model = Driver
        fields = [
            "id",
            "driver_code",
            "external_hr_id",
            "first_name",
            "middle_name",
            "last_name",
            "full_name",
            "contact_number",
            "email",
            "photo",
            "photo_url",
            "employment_status",
            "date_hired",
            "linked_user",
            "linked_user_display",
            "license_number",
            "license_category",
            "license_codes",
            "license_issue_date",
            "license_expiry_date",
            "medical_certificate_expiry_date",
            "work_shift",
            "shift_label",
            "shift_hours",
            "weekly_rest_days",
            "schedule_status",
            "eligibility_status",
            "eligibility_reasons",
            "safety_score",
            "safety_score_status",
            "safety_score_eligible",
            "safety_completed_trips",
            "safety_driving_hours",
            "safety_event_count",
            "safety_events_per_hour",
            "safety_event_counts",
            "safety_score_source",
            "safety_history",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "full_name",
            "photo_url",
            "linked_user_display",
            "eligibility_status",
            "eligibility_reasons",
            "safety_score",
            "safety_score_status",
            "safety_score_eligible",
            "safety_completed_trips",
            "safety_driving_hours",
            "safety_event_count",
            "safety_events_per_hour",
            "safety_event_counts",
            "safety_score_source",
            "safety_history",
            "work_shift",
            "shift_label",
            "shift_hours",
            "weekly_rest_days",
            "schedule_status",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"photo": {"write_only": True, "required": False}}

    def get_full_name(self, obj):
        return compact_driver_name(obj)

    def get_shift_hours(self, obj):
        return (
            "06:00 AM – 06:00 PM"
            if obj.work_shift == Driver.WorkShift.DAY
            else "06:00 PM – 06:00 AM"
        )

    def get_schedule_status(self, obj):
        return evaluate_driver_schedule(obj, timezone.now()).status

    def get_linked_user_display(self, obj):
        if obj.linked_user is None:
            return None
        return obj.linked_user.get_full_name().strip() or obj.linked_user.username

    def get_photo_url(self, obj):
        return f"/api/v1/drivers/{obj.pk}/photo/" if obj.photo else None

    def get_eligibility_status(self, obj):
        return driver_eligibility(obj)[0]

    def get_eligibility_reasons(self, obj):
        return driver_eligibility(obj)[1]

    def get_safety_score(self, obj):
        return self._resolved_safety_score(obj)[0]

    def get_safety_score_status(self, obj):
        source = self._resolved_safety_score(obj)[1]
        if source == "REAL":
            return "REAL_SCORED"
        return "DEMO_SCORED" if source == DriverSafetyDemoProfile.Source.DEMO_SEED else "NOT_SCORED"

    def _resolved_safety_score(self, obj):
        real_score = self.context.get("real_safety_scores", {}).get(obj.pk)
        if real_score is not None:
            return real_score, "REAL"
        profile = self._demo_profile(obj)
        if profile:
            return profile.safety_score, profile.source
        return None, None

    def _demo_profile(self, obj):
        try:
            return obj.safety_demo_profile
        except DriverSafetyDemoProfile.DoesNotExist:
            return None

    def get_safety_score_source(self, obj):
        return self._resolved_safety_score(obj)[1]

    def get_safety_history(self, obj):
        profile = self._demo_profile(obj)
        if not profile or self._resolved_safety_score(obj)[1] != DriverSafetyDemoProfile.Source.DEMO_SEED:
            return []
        return [
            {
                "id": event.pk,
                "occurred_at": event.occurred_at,
                "event_type": event.event_type,
                "event_label": event.get_event_type_display(),
                "source": event.source,
            }
            for event in profile.events.all()
        ]

    def _safety_metrics(self, obj):
        supplied = self.context.get("safety_metrics", {})
        if obj.pk in supplied:
            return supplied[obj.pk]
        cache = getattr(self, "_safety_metrics_cache", None)
        if cache is None:
            cache = {}
            self._safety_metrics_cache = cache
        if obj.pk not in cache:
            cache[obj.pk] = safety_metrics_for_drivers([obj.pk]).get(
                obj.pk, DriverSafetyMetrics()
            )
        return cache[obj.pk]

    def get_safety_score_eligible(self, obj):
        return self._safety_metrics(obj).score_eligible

    def get_safety_completed_trips(self, obj):
        profile = self._demo_profile(obj)
        if profile and self._resolved_safety_score(obj)[1] == DriverSafetyDemoProfile.Source.DEMO_SEED:
            return profile.completed_trip_count
        return self._safety_metrics(obj).completed_trip_count

    def get_safety_driving_hours(self, obj):
        profile = self._demo_profile(obj)
        if profile and self._resolved_safety_score(obj)[1] == DriverSafetyDemoProfile.Source.DEMO_SEED:
            return float(profile.driving_hours)
        return round(self._safety_metrics(obj).total_driving_hours, 4)

    def get_safety_event_count(self, obj):
        profile = self._demo_profile(obj)
        if profile and self._resolved_safety_score(obj)[1] == DriverSafetyDemoProfile.Source.DEMO_SEED:
            return profile.safety_event_count
        return self._safety_metrics(obj).attributed_harsh_event_count

    def get_safety_events_per_hour(self, obj):
        profile = self._demo_profile(obj)
        if profile and self._resolved_safety_score(obj)[1] == DriverSafetyDemoProfile.Source.DEMO_SEED:
            hours = float(profile.driving_hours)
            return round(profile.safety_event_count / hours, 4) if hours else None
        value = self._safety_metrics(obj).harsh_events_per_driving_hour
        return round(value, 4) if value is not None else None

    def get_safety_event_counts(self, obj):
        profile = self._demo_profile(obj)
        if profile and self._resolved_safety_score(obj)[1] == DriverSafetyDemoProfile.Source.DEMO_SEED:
            counts = {event_type: 0 for event_type in profile.events.model.EventType.values}
            for event in profile.events.all():
                counts[event.event_type] += 1
            return counts
        metrics = self._safety_metrics(obj)
        return {
            TelemetryEvent.DrivingEvent.HARSH_ACCELERATION: metrics.harsh_acceleration_count,
            TelemetryEvent.DrivingEvent.HARSH_BRAKING: metrics.harsh_braking_count,
            TelemetryEvent.DrivingEvent.SHARP_TURN: metrics.sharp_turn_count,
        }

    def validate_photo(self, value):
        allowed_types = {"image/jpeg", "image/png"}
        allowed_extensions = {"jpg", "jpeg", "png"}
        extension = value.name.rsplit(".", 1)[-1].lower() if "." in value.name else ""
        if value.content_type not in allowed_types or extension not in allowed_extensions:
            raise serializers.ValidationError("Only JPG, JPEG, and PNG files are allowed.")
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Photo must not exceed 5 MB.")
        return value

    def validate(self, attrs):
        for field in (
            "driver_code",
            "external_hr_id",
            "first_name",
            "middle_name",
            "last_name",
            "contact_number",
            "email",
            "license_number",
            "license_category",
            "license_codes",
        ):
            if field in attrs and attrs[field] is not None:
                attrs[field] = attrs[field].strip()
        request = self.context.get("request")
        role = getattr(getattr(request.user, "staff_profile", None), "role", None)
        if request and not request.user.is_superuser and role == "FLEET_MANAGER":
            protected = {"external_hr_id", "employment_status", "linked_user"}
            attempted = protected.intersection(self.initial_data)
            if attempted:
                raise serializers.ValidationError(
                    {field: "Only Fleet Admin may change this field." for field in attempted}
                )
        return attrs


class DriverDocumentSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = DriverDocument
        fields = [
            "id",
            "driver",
            "document_type",
            "title",
            "reference_number",
            "issuer_name",
            "issued_date",
            "effective_date",
            "expiry_date",
            "file",
            "file_name",
            "download_url",
            "uploaded_by",
            "uploaded_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "driver",
            "file_name",
            "download_url",
            "uploaded_by",
            "uploaded_by_name",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"file": {"write_only": True}}

    def get_uploaded_by_name(self, obj):
        return obj.uploaded_by.get_full_name().strip() or obj.uploaded_by.username

    def get_file_name(self, obj):
        return obj.file.name.rsplit("/", 1)[-1]

    def get_download_url(self, obj):
        return f"/api/v1/drivers/{obj.driver_id}/documents/{obj.pk}/file/"

    def validate_file(self, value):
        allowed_types = {"application/pdf", "image/jpeg", "image/png"}
        allowed_extensions = {"pdf", "jpg", "jpeg", "png"}
        extension = value.name.rsplit(".", 1)[-1].lower() if "." in value.name else ""
        if value.content_type not in allowed_types or extension not in allowed_extensions:
            raise serializers.ValidationError("Only PDF, JPG, JPEG, and PNG files are allowed.")
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("File must not exceed 5 MB.")
        return value
