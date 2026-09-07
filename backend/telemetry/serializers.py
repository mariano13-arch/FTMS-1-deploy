from datetime import UTC, timedelta

from django.conf import settings
from django.contrib.gis.geos import Point
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers

from telemetry.models import TelemetryDevice, TelemetryDeviceBinding, TelemetryEvent


class TelemetryDeviceRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelemetryDevice
        fields = ("device_id",)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("A JSON object is required.")
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {"non_field_errors": [f"Unknown fields: {', '.join(sorted(unknown))}."]}
            )
        return super().to_internal_value(data)


class TelemetryDevicePairSerializer(serializers.Serializer):
    vehicle_id = serializers.IntegerField(min_value=1)
    replace_current = serializers.BooleanField(default=False)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("A JSON object is required.")
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {"non_field_errors": [f"Unknown fields: {', '.join(sorted(unknown))}."]}
            )
        return super().to_internal_value(data)


class AwareDateTimeField(serializers.DateTimeField):
    default_error_messages = {"timezone": "A timezone-aware timestamp is required."}

    def to_internal_value(self, value):
        parsed = parse_datetime(value) if isinstance(value, str) else value
        if parsed is None or timezone.is_naive(parsed):
            self.fail("timezone")
        return super().to_internal_value(value).astimezone(UTC)


class TelemetryEventInputSerializer(serializers.Serializer):
    schema_version = serializers.CharField(max_length=8)
    event_id = serializers.CharField(max_length=128)
    sequence_number = serializers.IntegerField(min_value=0)
    device_id = serializers.CharField(max_length=64)
    recorded_at = AwareDateTimeField()
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=-180,
        max_value=180,
    )
    position_source = serializers.ChoiceField(
        choices=TelemetryEvent.PositionSource.values, required=False
    )
    position_accuracy_m = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=0, allow_null=True, required=False
    )
    gnss_speed_kph = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        min_value=0,
        max_value=300,
        allow_null=True,
    )
    rpm = serializers.IntegerField(min_value=0, max_value=12000, allow_null=True)
    coolant_c = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        allow_null=True,
    )
    engine_load_pct = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=0,
        max_value=100,
        allow_null=True,
    )
    obd_source = serializers.ChoiceField(
        choices=TelemetryEvent.ObdSource.values, allow_null=True, required=False
    )
    driving_event = serializers.ChoiceField(
        choices=TelemetryEvent.DrivingEvent.values, allow_null=True
    )

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("A JSON object is required.")
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {"non_field_errors": [f"Unknown fields: {', '.join(sorted(unknown))}."]}
            )
        return super().to_internal_value(data)

    def validate_schema_version(self, value):
        if value not in ("1.0", "1.1", "1.2"):
            raise serializers.ValidationError(
                "Only schema_version 1.0, 1.1, and 1.2 are supported."
            )
        return value

    def validate(self, data):
        version = data["schema_version"]
        source_supplied = "position_source" in self.initial_data
        accuracy_supplied = "position_accuracy_m" in self.initial_data
        obd_source_supplied = "obd_source" in self.initial_data
        if version == "1.0":
            if source_supplied or accuracy_supplied:
                raise serializers.ValidationError(
                    "Position provenance fields require schema_version 1.1."
                )
            if obd_source_supplied:
                raise serializers.ValidationError(
                    "OBD provenance requires schema_version 1.2."
                )
            if data["gnss_speed_kph"] is None:
                raise serializers.ValidationError(
                    {"gnss_speed_kph": "GNSS speed is required for schema_version 1.0."}
                )
            if data["driving_event"] is None:
                raise serializers.ValidationError(
                    {"driving_event": "This field may not be null for schema_version 1.0."}
                )
            data["position_source"] = TelemetryEvent.PositionSource.GNSS
            data["position_accuracy_m"] = None
            data["obd_source"] = None
            return data

        if version == "1.1" and obd_source_supplied:
            raise serializers.ValidationError("OBD provenance requires schema_version 1.2.")

        if not source_supplied:
            raise serializers.ValidationError({"position_source": "This field is required."})
        source = data["position_source"]
        accuracy = data.get("position_accuracy_m")
        if source == TelemetryEvent.PositionSource.GNSS:
            if data["gnss_speed_kph"] is None:
                raise serializers.ValidationError(
                    {"gnss_speed_kph": "GNSS positions require GNSS speed."}
                )
        else:
            if data["gnss_speed_kph"] is not None:
                raise serializers.ValidationError(
                    {"gnss_speed_kph": "Cellular LBS positions must not include GNSS speed."}
                )
            if accuracy is None or accuracy <= 0:
                raise serializers.ValidationError(
                    {"position_accuracy_m": "Cellular LBS positions require positive accuracy."}
                )
        data.setdefault("position_accuracy_m", None)
        if version == "1.2":
            has_obd_values = any(
                data[field] is not None
                for field in ("rpm", "coolant_c", "engine_load_pct")
            )
            if has_obd_values and data.get("obd_source") is None:
                raise serializers.ValidationError(
                    {"obd_source": "This field is required when OBD values are present."}
                )
        data.setdefault("obd_source", None)
        return data

    def validate_recorded_at(self, value):
        clock_skew_seconds = settings.FTMS_TELEMETRY_CLOCK_SKEW_SECONDS
        if value > timezone.now() + timedelta(seconds=clock_skew_seconds):
            raise serializers.ValidationError(
                f"Timestamp cannot be more than {clock_skew_seconds} seconds in the future."
            )
        return value

    def validate_device_id(self, value):
        try:
            device = TelemetryDevice.objects.get(device_id=value)
        except TelemetryDevice.DoesNotExist as exc:
            raise serializers.ValidationError("Unknown device_id.") from exc
        if device.registration_status != TelemetryDevice.RegistrationStatus.REGISTERED:
            raise serializers.ValidationError("Device is not registered for operation.")
        binding = (
            TelemetryDeviceBinding.objects.select_related("vehicle")
            .filter(device=device, unpaired_at__isnull=True)
            .first()
        )
        if binding is None:
            raise serializers.ValidationError("Device is not paired to a vehicle.")
        vehicle = binding.vehicle
        if not vehicle.is_active:
            raise serializers.ValidationError("Vehicle is inactive.")
        self.context["device"] = device
        self.context["vehicle"] = vehicle
        return value

    def create_model_values(self):
        data = self.validated_data
        return {
            "schema_version": data["schema_version"],
            "event_id": data["event_id"],
            "sequence_number": data["sequence_number"],
            "device": self.context["device"],
            "vehicle": self.context["vehicle"],
            "recorded_at": data["recorded_at"],
            "location": Point(float(data["longitude"]), float(data["latitude"]), srid=4326),
            "position_source": data["position_source"],
            "position_accuracy_m": data["position_accuracy_m"],
            "gnss_speed_kph": data["gnss_speed_kph"],
            "rpm": data["rpm"],
            "coolant_c": data["coolant_c"],
            "engine_load_pct": data["engine_load_pct"],
            "obd_source": data["obd_source"],
            "driving_event": data["driving_event"],
        }
