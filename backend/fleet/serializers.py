from datetime import UTC, datetime, timedelta

from django.db.models.functions import Lower
from django.utils import timezone
from rest_framework import serializers

from .models import Vehicle, VehicleDocument, VehicleInspection


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
            raise serializers.ValidationError({
                field: ["Unknown field."] for field in sorted(unknown)
            })
        return super().to_internal_value(data)


class VehicleSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    latest_inspection = serializers.SerializerMethodField()
    document_count = serializers.SerializerMethodField()
    document_health = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = [
            "device_id", "plate_number", "display_name", "vehicle_type",
            "manufacturer", "model", "model_year", "passenger_capacity",
            "payload_capacity_kg", "gvwr_kg",
            "vin", "engine_number", "chassis_number", "color", "fuel_type",
            "transmission_type", "ownership_type", "supplier_name",
            "purchase_order_number", "acquisition_date", "purchase_price",
            "purchase_currency", "warranty_expiry_date",
            "registration_expiry_date", "insurance_expiry_date",
            "is_active", "created_at", "updated_at", "latest_inspection",
            "document_count", "document_health",
        ]
        read_only_fields = [
            "created_at", "updated_at", "latest_inspection", "document_count",
            "document_health",
        ]

    def get_latest_inspection(self, obj):
        inspection = next(iter(obj.inspections.all()), None)
        return (
            VehicleInspectionSummarySerializer(inspection).data
            if inspection is not None
            else None
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
            document.expiry_date is not None
            and document.expiry_date <= today + timedelta(days=30)
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
            "display_name", "manufacturer", "model", "vin", "engine_number",
            "chassis_number", "color", "supplier_name", "purchase_order_number",
            "purchase_currency",
        ):
            if field in attrs:
                value = attrs[field].strip()
                attrs[field] = value.upper() if field in {"vin", "purchase_currency"} else value
        errors = {}
        for field in (
            "created_at", "updated_at", "latest_inspection", "document_count",
            "document_health",
        ):
            if field in self.initial_data:
                errors[field] = "This field is not accepted."
        string_fields = (
            "device_id", "plate_number", "display_name", "vehicle_type",
            "manufacturer", "model",
            "vin", "engine_number", "chassis_number", "color", "fuel_type",
            "transmission_type", "ownership_type", "supplier_name",
            "purchase_order_number", "purchase_currency",
        )
        for field in string_fields:
            if field in self.initial_data and not isinstance(self.initial_data[field], str):
                errors[field] = "Must be a string."
        for field in ("model_year", "passenger_capacity"):
            value = self.initial_data.get(field)
            if field in self.initial_data and value is not None and (
                not isinstance(value, int) or isinstance(value, bool)
            ):
                errors[field] = "Must be an integer or null."
        for field in ("payload_capacity_kg", "gvwr_kg"):
            value = self.initial_data.get(field)
            if field in self.initial_data and value is not None and isinstance(value, bool):
                errors[field] = "Must be a decimal number or null."
        if self.instance is None and "is_active" in self.initial_data:
            errors["is_active"] = "This field is not accepted."
        if self.instance is not None:
            if "device_id" in self.initial_data:
                errors["device_id"] = "This field is immutable."
            if "is_active" in self.initial_data:
                errors["is_active"] = "Use the status action."
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
            "id", "vehicle", "document_type", "title", "reference_number",
            "issuer_name", "issued_date", "effective_date", "expiry_date",
            "file", "file_name", "download_url",
            "uploaded_by", "uploaded_by_name", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "vehicle", "file_name", "download_url", "uploaded_by",
            "uploaded_by_name", "created_at", "updated_at",
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
