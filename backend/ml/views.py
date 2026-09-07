from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import StaffAccess
from fleet.models import Vehicle
from ml.dashboard import RANGES, dashboard_data
from ml.fuel import (
    VALIDATED_TELEMETRY_SOURCE_MODE,
    model_info,
    operational_readiness,
    operational_telemetry_inputs,
    predict_fuel,
)
from ml.models import FuelPrediction
from telemetry.models import TelemetryEvent
from telemetry.serializers import AwareDateTimeField


class FuelPredictionTimestampSerializer(serializers.Serializer):
    input_timestamp = AwareDateTimeField(required=False, allow_null=True)
    vehicle_id = serializers.PrimaryKeyRelatedField(
        source="vehicle",
        queryset=Vehicle.objects.all(),
        required=False,
    )

    def validate(self, attrs):
        has_vehicle = "vehicle" in attrs
        has_timestamp = attrs.get("input_timestamp") is not None
        if has_vehicle != has_timestamp:
            raise serializers.ValidationError(
                "vehicle_id and input_timestamp must be provided together for persistence."
            )
        if has_vehicle:
            event = (
                TelemetryEvent.objects.select_related("device", "vehicle")
                .filter(vehicle=attrs["vehicle"], recorded_at=attrs["input_timestamp"])
                .order_by("-sequence_number", "-received_at", "-pk")
                .first()
            )
            if event is None:
                raise serializers.ValidationError(
                    {"input_timestamp": "No matching telemetry event exists for this vehicle."}
                )
            attrs["telemetry_event"] = event
        return attrs


class FuelDashboardFilterSerializer(serializers.Serializer):
    range = serializers.ChoiceField(choices=tuple(RANGES), default="24h")
    vehicle = serializers.IntegerField(required=False, min_value=1)
    page = serializers.IntegerField(default=1, min_value=1)
    page_size = serializers.IntegerField(default=10, min_value=1, max_value=500)
    search = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=120,
        trim_whitespace=True,
    )

    def validate_vehicle(self, value):
        if not Vehicle.objects.filter(pk=value, is_active=True).exists():
            raise serializers.ValidationError("Active vehicle not found.")
        return value


class FuelModelInfoView(APIView):
    http_method_names = ["get", "options"]
    permission_classes = [StaffAccess]

    def get(self, request):
        return Response(model_info())


class FuelReadinessView(APIView):
    http_method_names = ["get", "options"]
    permission_classes = [StaffAccess]

    def get(self, request):
        return Response(operational_readiness())


class FuelDashboardView(APIView):
    http_method_names = ["get", "options"]
    permission_classes = [StaffAccess]

    def get(self, request):
        unknown = set(request.query_params) - {
            "range",
            "vehicle",
            "page",
            "page_size",
            "search",
        }
        if unknown:
            raise serializers.ValidationError(
                {key: "Unknown filter." for key in unknown}
            )
        filters = FuelDashboardFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        return Response(
            dashboard_data(
                range_key=filters.validated_data["range"],
                vehicle_id=filters.validated_data.get("vehicle"),
                page=filters.validated_data["page"],
                page_size=filters.validated_data["page_size"],
                search=filters.validated_data.get("search", ""),
            )
        )


class FuelPredictionView(APIView):
    http_method_names = ["post", "options"]
    permission_classes = [StaffAccess]

    def post(self, request):
        if not isinstance(request.data, dict):
            return Response(
                {"status": "invalid_input", "detail": "A JSON object is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        timestamp_serializer = FuelPredictionTimestampSerializer(
            data={
                key: request.data[key]
                for key in ("input_timestamp", "vehicle_id")
                if key in request.data
            }
        )
        timestamp_serializer.is_valid(raise_exception=True)
        inputs = {
            key: value
            for key, value in request.data.items()
            if key not in {"input_timestamp", "vehicle_id"}
        }
        telemetry_event = timestamp_serializer.validated_data.get("telemetry_event")
        if telemetry_event is not None:
            if inputs:
                raise serializers.ValidationError(
                    {
                        "inputs": (
                            "Vehicle-linked inference derives model inputs from the matched "
                            "telemetry event; request-supplied model inputs are not accepted."
                        )
                    }
                )
            inputs = operational_telemetry_inputs(telemetry_event)
        result = predict_fuel(
            inputs,
            input_timestamp=(
                telemetry_event.recorded_at if telemetry_event is not None else None
            ),
        )
        result["history_persisted"] = False
        if (
            result["status"] == "prediction_available"
            and "vehicle" in timestamp_serializer.validated_data
        ):
            _, created = FuelPrediction.objects.get_or_create(
                vehicle=timestamp_serializer.validated_data["vehicle"],
                input_timestamp=timestamp_serializer.validated_data["input_timestamp"],
                model_version=result["model_version"],
                defaults={
                    "estimated_fuel_lph": result["estimated_fuel_lph"],
                    "model_name": result["model_name"],
                    "source_mode": VALIDATED_TELEMETRY_SOURCE_MODE,
                    "validated_inputs": result["inputs"],
                },
            )
            result["history_persisted"] = created
        response_status = status.HTTP_200_OK
        if result["status"] == "invalid_input":
            response_status = status.HTTP_400_BAD_REQUEST
        elif result["status"] == "model_unavailable":
            response_status = status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(result, status=response_status)
