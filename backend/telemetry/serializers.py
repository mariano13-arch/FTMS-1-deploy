from datetime import UTC, timedelta

from django.conf import settings
from django.contrib.gis.geos import Point
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers

from fleet.models import Vehicle
from telemetry.models import TelemetryEvent


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
    gnss_speed_kph = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        min_value=0,
        max_value=300,
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
    driving_event = serializers.ChoiceField(choices=TelemetryEvent.DrivingEvent.values)

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
        if value != "1.0":
            raise serializers.ValidationError("Only schema_version 1.0 is supported.")
        return value

    def validate_recorded_at(self, value):
        clock_skew_seconds = settings.FTMS_TELEMETRY_CLOCK_SKEW_SECONDS
        if value > timezone.now() + timedelta(seconds=clock_skew_seconds):
            raise serializers.ValidationError(
                f"Timestamp cannot be more than {clock_skew_seconds} seconds in the future."
            )
        return value

    def validate_device_id(self, value):
        try:
            vehicle = Vehicle.objects.get(device_id=value)
        except Vehicle.DoesNotExist as exc:
            raise serializers.ValidationError("Unknown device_id.") from exc
        if not vehicle.is_active:
            raise serializers.ValidationError("Vehicle is inactive.")
        self.context["vehicle"] = vehicle
        return value

    def create_model_values(self):
        data = self.validated_data
        return {
            "schema_version": data["schema_version"],
            "event_id": data["event_id"],
            "sequence_number": data["sequence_number"],
            "vehicle": self.context["vehicle"],
            "recorded_at": data["recorded_at"],
            "location": Point(float(data["longitude"]), float(data["latitude"]), srid=4326),
            "gnss_speed_kph": data["gnss_speed_kph"],
            "rpm": data["rpm"],
            "coolant_c": data["coolant_c"],
            "engine_load_pct": data["engine_load_pct"],
            "driving_event": data["driving_event"],
        }
