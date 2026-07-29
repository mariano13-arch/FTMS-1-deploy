from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from fleet.models import Vehicle
from telemetry.presentation import event_data, latest_status_data
from telemetry.services import IngestionStatus, TelemetryValidationError, ingest_telemetry


def accepted_response(event, *, response_status, duplicate, http_status):
    return Response(
        {
            "status": response_status,
            "duplicate": duplicate,
            "event": event_data(event),
        },
        status=http_status,
    )


class TelemetryEventCreateView(APIView):
    http_method_names = ["post", "options"]

    def post(self, request):
        try:
            result = ingest_telemetry(request.data)
        except TelemetryValidationError as exc:
            raise serializers.ValidationError(exc.errors) from exc
        if result.status == IngestionStatus.CONFLICT:
            return Response(
                {"detail": "event_id already exists with different telemetry data."},
                status=status.HTTP_409_CONFLICT,
            )
        if result.status == IngestionStatus.DUPLICATE:
            return accepted_response(
                result.event,
                response_status="duplicate",
                duplicate=True,
                http_status=status.HTTP_200_OK,
            )
        return accepted_response(
            result.event,
            response_status="created",
            duplicate=False,
            http_status=status.HTTP_201_CREATED,
        )


class LatestVehicleStatusView(APIView):
    http_method_names = ["get", "options"]

    def get(self, request, device_id):
        vehicle = get_object_or_404(Vehicle, device_id=device_id)
        return Response(latest_status_data(vehicle))
