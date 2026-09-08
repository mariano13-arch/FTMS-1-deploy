from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import CanEditVehicle, StaffAccess
from fleet.models import Vehicle
from telemetry import demo
from telemetry.geofences import (
    GeofenceWriteSerializer,
    event_payload,
    geofence_payload,
    rebuild_geofence_activity,
)
from telemetry.models import Geofence, GeofenceEvent, TelemetryDevice, TelemetryEvent
from telemetry.pairing import DevicePairingConflict, pair_device_to_vehicle, unpair_device
from telemetry.presentation import (
    current_telemetry_cutoff,
    event_data,
    latest_status_data,
    numeric,
    valid_position,
)
from telemetry.serializers import (
    TelemetryDevicePairSerializer,
    TelemetryDeviceRegistrationSerializer,
)
from telemetry.services import IngestionStatus, TelemetryValidationError, ingest_telemetry
from transport_requests.execution import ACTIVE_EXECUTION_STATUSES
from transport_requests.models import DispatchAssignment, TransportRequest


def accepted_response(event, *, response_status, duplicate, http_status):
    return Response(
        {
            "status": response_status,
            "duplicate": duplicate,
            "event": event_data(event),
        },
        status=http_status,
    )


def telemetry_device_data(device):
    binding = (
        device.bindings.select_related("vehicle")
        .filter(unpaired_at__isnull=True)
        .first()
    )
    vehicle = None
    if binding is not None:
        vehicle = {
            "vehicle_id": binding.vehicle_id,
            "plate_number": binding.vehicle.plate_number,
            "display_name": binding.vehicle.display_name,
            "compatibility_device_id": binding.vehicle.device_id,
        }
    return {
        "device_id": device.device_id,
        "registration_status": device.registration_status,
        "is_paired": binding is not None,
        "current_vehicle": vehicle,
    }


class TelemetryDeviceCreateView(APIView):
    http_method_names = ["post", "options"]
    permission_classes = [StaffAccess, CanEditVehicle]

    def post(self, request):
        serializer = TelemetryDeviceRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = serializer.save()
        return Response(telemetry_device_data(device), status=status.HTTP_201_CREATED)


class TelemetryDeviceDetailView(APIView):
    http_method_names = ["get", "options"]
    permission_classes = [StaffAccess]

    def get(self, request, device_id):
        device = get_object_or_404(TelemetryDevice, device_id=device_id)
        return Response(telemetry_device_data(device))


class TelemetryDevicePairView(APIView):
    http_method_names = ["post", "options"]
    permission_classes = [StaffAccess, CanEditVehicle]

    def post(self, request, device_id):
        device = get_object_or_404(TelemetryDevice, device_id=device_id)
        serializer = TelemetryDevicePairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vehicle_id = serializer.validated_data["vehicle_id"]
        get_object_or_404(Vehicle, pk=vehicle_id)
        try:
            binding, created = pair_device_to_vehicle(
                device_id=device.device_id,
                vehicle_id=vehicle_id,
                user=request.user,
                replace_current=serializer.validated_data["replace_current"],
            )
        except DevicePairingConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        device.refresh_from_db()
        return Response(
            telemetry_device_data(device),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class TelemetryDeviceUnpairView(APIView):
    http_method_names = ["post", "options"]
    permission_classes = [StaffAccess, CanEditVehicle]

    def post(self, request, device_id):
        device = get_object_or_404(TelemetryDevice, device_id=device_id)
        try:
            unpair_device(device_id=device.device_id, user=request.user)
        except DevicePairingConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        device.refresh_from_db()
        return Response(telemetry_device_data(device))


class TelemetryEventCreateView(APIView):
    http_method_names = ["post", "options"]
    authentication_classes = []
    permission_classes = [AllowAny]

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
    permission_classes = [StaffAccess]

    def get(self, request, device_id):
        vehicle = get_object_or_404(Vehicle, device_id=device_id)
        return Response(latest_status_data(vehicle))


class FleetLiveVehicleListView(APIView):
    http_method_names = ["get", "options"]
    permission_classes = [StaffAccess]

    def get(self, request):
        vehicles = list(Vehicle.objects.order_by("device_id"))
        vehicle_ids = [vehicle.pk for vehicle in vehicles]
        now = timezone.now()
        latest_events = (
            TelemetryEvent.objects.filter(
                vehicle_id__in=vehicle_ids,
                recorded_at__lte=current_telemetry_cutoff(now),
            )
            .order_by(
                "vehicle_id", "-recorded_at", "-sequence_number", "-received_at", "-pk"
            )
            .distinct("vehicle_id")
        )
        event_by_vehicle = {event.vehicle_id: event for event in latest_events}
        assignments = (
            DispatchAssignment.objects.filter(
                vehicle_id__in=vehicle_ids,
                transport_request__status=TransportRequest.Status.READY_FOR_DISPATCH,
                accepted_at__isnull=False,
                execution_status__in=ACTIVE_EXECUTION_STATUSES,
            )
            .select_related("driver", "transport_request")
            .order_by("vehicle_id", "transport_request__scheduled_pickup_at", "pk")
        )
        assignment_by_vehicle = {}
        for assignment in assignments:
            assignment_by_vehicle.setdefault(assignment.vehicle_id, assignment)

        demo_config = demo.configuration()
        simulated_vehicle_count = 0
        stale_cutoff = now - timedelta(seconds=settings.DISPATCH_TELEMETRY_MAX_AGE_SECONDS)
        results = []
        for vehicle in vehicles:
            event = event_by_vehicle.get(vehicle.pk)
            assignment = assignment_by_vehicle.get(vehicle.pk)
            position = valid_position(event)
            if not vehicle.is_active:
                telemetry_state = "offline"
            elif position is None:
                telemetry_state = "no_telemetry"
            elif event.recorded_at < stale_cutoff:
                telemetry_state = "stale"
            else:
                telemetry_state = "live"
            telemetry = None
            if event is not None and position is not None:
                telemetry = {
                    **position,
                    "speed_kph": numeric(event.gnss_speed_kph),
                    "position_source": event.position_source,
                    "position_accuracy_m": numeric(event.position_accuracy_m),
                    "recorded_at": event.recorded_at,
                    "age_seconds": max(0, int((now - event.recorded_at).total_seconds())),
                    "driving_event": event.driving_event,
                    "rpm": event.rpm,
                    "coolant_c": numeric(event.coolant_c),
                    "engine_load_pct": numeric(event.engine_load_pct),
                    "obd_source": event.obd_source,
                    "telemetry_source": "real",
                    "is_demo_telemetry": False,
                }
            elif event is None and assignment is None and demo_config["active"]:
                telemetry_state = "offline" if not vehicle.is_active else demo.state(vehicle)
                telemetry = demo.point(
                    vehicle,
                    now,
                    demo_config,
                    telemetry_state,
                    settings.DISPATCH_TELEMETRY_MAX_AGE_SECONDS,
                )
                if telemetry is not None:
                    simulated_vehicle_count += 1
            active_assignment = None
            if assignment is not None:
                item = assignment.transport_request
                driver_name = " ".join(
                    filter(
                        None,
                        [
                            assignment.driver.first_name,
                            assignment.driver.middle_name,
                            assignment.driver.last_name,
                        ],
                    )
                )
                active_assignment = {
                    "assignment_id": assignment.pk,
                    "execution_status": assignment.execution_status,
                    "driver_id": assignment.driver_id,
                    "driver_code": assignment.driver.driver_code,
                    "driver_name": driver_name,
                    "request_id": item.pk,
                    "request_number": item.request_number,
                    "request_status": item.status,
                    "source_system": item.source_system,
                    "scheduled_pickup_at": item.scheduled_pickup_at,
                    "pickup_name": item.pickup_name,
                    "pickup_latitude": item.pickup_latitude,
                    "pickup_longitude": item.pickup_longitude,
                    "destination_name": item.destination_name,
                    "destination_latitude": item.destination_latitude,
                    "destination_longitude": item.destination_longitude,
                }
            results.append(
                {
                    "vehicle_id": vehicle.pk,
                    "device_id": vehicle.device_id,
                    "display_name": vehicle.display_name,
                    "plate_number": vehicle.plate_number,
                    "vehicle_type": vehicle.vehicle_type,
                    "photo_url": (
                        f"/api/v1/vehicles/{vehicle.device_id}/photo/"
                        if vehicle.photo
                        else None
                    ),
                    "is_active": vehicle.is_active,
                    "telemetry_state": telemetry_state,
                    "telemetry": telemetry,
                    "active_assignment": active_assignment,
                }
            )
        return Response(
            {
                "generated_at": now,
                "capabilities": {
                    "telemetry_trail": True,
                    "safety_events": True,
                    "geofence": True,
                    "demo_telemetry": True,
                },
                "demo_telemetry": {
                    "enabled": demo_config["enabled"],
                    "active": demo_config["active"],
                    "simulated_vehicle_count": simulated_vehicle_count,
                    **(
                        {"configuration_error": demo_config["configuration_error"]}
                        if "configuration_error" in demo_config
                        else {}
                    ),
                },
                "vehicles": results,
            }
        )


class FleetLiveVehicleTrailView(APIView):
    http_method_names = ["get", "options"]
    permission_classes = [StaffAccess]

    def get(self, request, vehicle_id):
        vehicle = get_object_or_404(Vehicle, pk=vehicle_id)
        recent_events = list(
            TelemetryEvent.objects.filter(
                vehicle=vehicle,
                position_source=TelemetryEvent.PositionSource.GNSS,
                recorded_at__lte=current_telemetry_cutoff(),
            ).order_by("-recorded_at", "-sequence_number", "-received_at", "-pk")[:25]
        )
        points = [
            {
                "event_id": event.event_id,
                "latitude": event.location.y,
                "longitude": event.location.x,
                "speed_kph": numeric(event.gnss_speed_kph),
                "recorded_at": event.recorded_at,
            }
            for event in reversed(recent_events)
        ]
        return Response(
            {
                "vehicle_id": vehicle.pk,
                "device_id": vehicle.device_id,
                "points": points,
            }
        )


class FleetLiveSafetyEventListView(APIView):
    http_method_names = ["get", "options"]
    permission_classes = [StaffAccess]

    def get(self, request):
        events = TelemetryEvent.objects.filter(
            driving_event__in=(
                TelemetryEvent.DrivingEvent.HARSH_BRAKING,
                TelemetryEvent.DrivingEvent.HARSH_ACCELERATION,
            )
        ).select_related("vehicle")[:50]
        return Response(
            {
                "events": [
                    {
                        "event_id": event.event_id,
                        "event_type": event.driving_event,
                        "recorded_at": event.recorded_at,
                        "latitude": event.location.y,
                        "longitude": event.location.x,
                        "speed_kph": numeric(event.gnss_speed_kph),
                        "vehicle_id": event.vehicle_id,
                        "device_id": event.vehicle.device_id,
                        "vehicle_name": event.vehicle.display_name,
                        "plate_number": event.vehicle.plate_number,
                    }
                    for event in events
                ]
            }
        )


class GeofenceEventFilterSerializer(serializers.Serializer):
    geofence = serializers.UUIDField(required=False)
    vehicle = serializers.IntegerField(required=False, min_value=1)
    event_type = serializers.ChoiceField(
        choices=GeofenceEvent.EventType.values,
        required=False,
    )
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)

    def validate(self, attrs):
        if attrs.get("date_from") and attrs.get("date_to"):
            if attrs["date_from"] > attrs["date_to"]:
                raise serializers.ValidationError(
                    {"date_to": "Must be on or after date_from."}
                )
        return attrs


class GeofenceEventPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class GeofenceEventListView(APIView):
    http_method_names = ["get", "options"]
    permission_classes = [StaffAccess]

    def get(self, request):
        allowed = {
            "geofence",
            "vehicle",
            "event_type",
            "date_from",
            "date_to",
            "page",
            "page_size",
        }
        unknown = set(request.query_params) - allowed
        if unknown:
            raise serializers.ValidationError(
                {key: "Unknown filter." for key in unknown}
            )
        filters = GeofenceEventFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        values = filters.validated_data
        queryset = GeofenceEvent.objects.select_related("geofence", "vehicle").order_by(
            "-occurred_at", "-pk"
        )
        if "geofence" in values:
            queryset = queryset.filter(geofence_id=values["geofence"])
        if "vehicle" in values:
            queryset = queryset.filter(vehicle_id=values["vehicle"])
        if "event_type" in values:
            queryset = queryset.filter(event_type=values["event_type"])
        current_timezone = timezone.get_current_timezone()
        if "date_from" in values:
            start = timezone.make_aware(
                datetime.combine(values["date_from"], time.min),
                current_timezone,
            )
            queryset = queryset.filter(occurred_at__gte=start)
        if "date_to" in values:
            end = timezone.make_aware(
                datetime.combine(values["date_to"] + timedelta(days=1), time.min),
                current_timezone,
            )
            queryset = queryset.filter(occurred_at__lt=end)
        paginator = GeofenceEventPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response([event_payload(event) for event in page])


class GeofenceListCreateView(APIView):
    http_method_names = ["get", "post", "options"]
    permission_classes = [StaffAccess]

    def get(self, request):
        return Response({"results": [geofence_payload(item) for item in Geofence.objects.all()]})

    def post(self, request):
        serializer = GeofenceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            geofence = serializer.save(user=request.user)
            rebuild_geofence_activity(geofence)
        return Response(
            geofence_payload(geofence, include_activity=True),
            status=status.HTTP_201_CREATED,
        )


class GeofenceDetailView(APIView):
    http_method_names = ["get", "patch", "options"]
    permission_classes = [StaffAccess]

    def get_object(self, geofence_id):
        return get_object_or_404(Geofence, pk=geofence_id)

    def get(self, request, geofence_id):
        return Response(geofence_payload(self.get_object(geofence_id), include_activity=True))

    def patch(self, request, geofence_id):
        geofence = self.get_object(geofence_id)
        serializer = GeofenceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        boundary_changed = geofence.boundary != serializer.validated_data["boundary"]
        with transaction.atomic():
            geofence = serializer.save(user=request.user, instance=geofence)
            if boundary_changed:
                rebuild_geofence_activity(geofence)
        return Response(geofence_payload(geofence, include_activity=True))
