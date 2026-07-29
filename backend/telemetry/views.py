from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from fleet.models import Vehicle
from telemetry.models import TelemetryEvent
from telemetry.presentation import event_data, semantic_values
from telemetry.serializers import TelemetryEventInputSerializer


def accepted_response(event, *, response_status, duplicate, http_status):
    return Response(
        {
            "status": response_status,
            "duplicate": duplicate,
            "event": event_data(event),
        },
        status=http_status,
    )


def duplicate_or_conflict(event, serializer):
    incoming = {
        **serializer.validated_data,
        "latitude": float(serializer.validated_data["latitude"]),
        "longitude": float(serializer.validated_data["longitude"]),
        "gnss_speed_kph": float(serializer.validated_data["gnss_speed_kph"]),
        "coolant_c": (
            None
            if serializer.validated_data["coolant_c"] is None
            else float(serializer.validated_data["coolant_c"])
        ),
        "engine_load_pct": (
            None
            if serializer.validated_data["engine_load_pct"] is None
            else float(serializer.validated_data["engine_load_pct"])
        ),
    }
    incoming["recorded_at"] = (
        incoming["recorded_at"].isoformat().replace("+00:00", "Z")
    )
    if semantic_values(event) == incoming:
        return accepted_response(
            event,
            response_status="duplicate",
            duplicate=True,
            http_status=status.HTTP_200_OK,
        )
    return Response(
        {"detail": "event_id already exists with different telemetry data."},
        status=status.HTTP_409_CONFLICT,
    )


class TelemetryEventCreateView(APIView):
    http_method_names = ["post", "options"]

    def post(self, request):
        serializer = TelemetryEventInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        existing = (
            TelemetryEvent.objects.select_related("vehicle")
            .filter(event_id=serializer.validated_data["event_id"])
            .first()
        )
        if existing:
            return duplicate_or_conflict(existing, serializer)

        try:
            with transaction.atomic():
                event = TelemetryEvent.objects.create(**serializer.create_model_values())
        except IntegrityError:
            event = TelemetryEvent.objects.select_related("vehicle").get(
                event_id=serializer.validated_data["event_id"]
            )
            return duplicate_or_conflict(event, serializer)

        event.vehicle = serializer.context["vehicle"]
        return accepted_response(
            event,
            response_status="created",
            duplicate=False,
            http_status=status.HTTP_201_CREATED,
        )


class LatestVehicleStatusView(APIView):
    http_method_names = ["get", "options"]

    def get(self, request, device_id):
        vehicle = get_object_or_404(Vehicle, device_id=device_id)
        event = vehicle.telemetry_events.select_related("vehicle").first()
        return Response(
            {
                "vehicle": {
                    "device_id": vehicle.device_id,
                    "plate_number": vehicle.plate_number,
                    "display_name": vehicle.display_name,
                },
                "latest": None if event is None else event_data(event),
            }
        )
