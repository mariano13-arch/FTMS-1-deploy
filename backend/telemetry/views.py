from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import UserNotification
from accounts.notifications import notify_capability_users
from accounts.permissions import ModuleActionAccess, StaffAccess
from accounts.roles import has_module_permission
from fleet.models import Vehicle, VehicleInspection, VehicleMaintenanceRecord
from telemetry import demo
from telemetry.geofences import (
    GeofenceWriteSerializer,
    event_payload,
    geofence_payload,
    rebuild_geofence_activity,
)
from telemetry.models import (
    Geofence,
    GeofenceEvent,
    TelemetryDevice,
    TelemetryDeviceBinding,
    TelemetryEvent,
    VehicleEmergencySOS,
)
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
    VehicleEmergencySOSActionSerializer,
)
from telemetry.services import IngestionStatus, TelemetryValidationError, ingest_telemetry
from transport_requests import routing
from transport_requests.active_routes import active_assignment_route
from transport_requests.driver_serializers import DriverActiveRouteSerializer
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


def telemetry_device_data(device, *, include_history=False):
    binding = device.bindings.select_related("vehicle").filter(unpaired_at__isnull=True).first()
    vehicle = None
    if binding is not None:
        vehicle = {
            "vehicle_id": binding.vehicle_id,
            "plate_number": binding.vehicle.plate_number,
            "display_name": binding.vehicle.display_name,
            "compatibility_device_id": binding.vehicle.device_id,
        }
    latest = device.telemetry_events.order_by("-recorded_at", "-pk").first()
    result = {
        "device_id": device.device_id,
        "registration_status": device.registration_status,
        "created_at": device.created_at,
        "is_paired": binding is not None,
        "current_vehicle": vehicle,
        "current_binding": (
            {
                "id": binding.pk,
                "paired_at": binding.paired_at,
                "paired_by": binding.paired_by.get_full_name() or binding.paired_by.username
                if binding.paired_by
                else None,
            }
            if binding
            else None
        ),
        "latest_telemetry": (
            {
                "recorded_at": latest.recorded_at,
                "position_source": latest.position_source,
                "obd_source": latest.obd_source,
                "latitude": latest.location.y,
                "longitude": latest.location.x,
            }
            if latest
            else None
        ),
    }
    if include_history:
        result["binding_history"] = [
            {
                "id": item.pk,
                "vehicle_id": item.vehicle_id,
                "vehicle_name": item.vehicle.display_name,
                "plate_number": item.vehicle.plate_number,
                "paired_at": item.paired_at,
                "unpaired_at": item.unpaired_at,
                "paired_by": item.paired_by.get_full_name() or item.paired_by.username
                if item.paired_by
                else None,
                "unpaired_by": item.unpaired_by.get_full_name() or item.unpaired_by.username
                if item.unpaired_by
                else None,
            }
            for item in device.bindings.select_related("vehicle", "paired_by", "unpaired_by").all()
        ]
    return result


class DevicePagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = "page_size"
    max_page_size = 100


class TelemetryDeviceCreateView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DEVICES"
    permission_actions = {"GET": "VIEW", "POST": "REGISTER"}
    http_method_names = ["get", "post", "options"]

    def get(self, request):
        active_bindings = TelemetryDeviceBinding.objects.filter(
            device_id=OuterRef("pk"),
            unpaired_at__isnull=True,
        )
        devices = TelemetryDevice.objects.annotate(has_active_binding=Exists(active_bindings))
        search = request.query_params.get("search", "").strip()
        if search:
            devices = devices.filter(
                Q(device_id__icontains=search)
                | Q(
                    bindings__unpaired_at__isnull=True,
                    bindings__vehicle__display_name__icontains=search,
                )
                | Q(
                    bindings__unpaired_at__isnull=True,
                    bindings__vehicle__plate_number__icontains=search,
                )
                | Q(
                    bindings__unpaired_at__isnull=True,
                    bindings__vehicle__device_id__icontains=search,
                )
            ).distinct()
        binding = request.query_params.get("binding")
        if binding == "paired":
            devices = devices.filter(has_active_binding=True)
        elif binding == "unpaired":
            devices = devices.filter(has_active_binding=False)
        registry = request.query_params.get("registry")
        if registry in TelemetryDevice.RegistrationStatus.values:
            devices = devices.filter(registration_status=registry)
        paginator = DevicePagination()
        page = paginator.paginate_queryset(devices, request, view=self)
        response = paginator.get_paginated_response(
            [telemetry_device_data(device) for device in page]
        )
        response.data["summary"] = {
            "total_registered": TelemetryDevice.objects.filter(
                registration_status=TelemetryDevice.RegistrationStatus.REGISTERED
            ).count(),
            "paired": TelemetryDevice.objects.annotate(has_active_binding=Exists(active_bindings))
            .filter(has_active_binding=True)
            .count(),
            "unpaired": TelemetryDevice.objects.annotate(has_active_binding=Exists(active_bindings))
            .filter(has_active_binding=False)
            .count(),
            "recently_seen": TelemetryDevice.objects.filter(
                telemetry_events__recorded_at__gte=current_telemetry_cutoff()
            )
            .distinct()
            .count(),
        }
        response.data["can_manage"] = any(
            has_module_permission(request.user, "DEVICES", action)
            for action in ("REGISTER", "PAIR", "REPLACE", "UNPAIR")
        )
        return response

    def post(self, request):
        serializer = TelemetryDeviceRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                device, created = TelemetryDevice.objects.get_or_create(
                    device_id=serializer.validated_data["device_id"]
                )
        except IntegrityError:
            device = TelemetryDevice.objects.get(device_id=serializer.validated_data["device_id"])
            created = False
        return Response(
            telemetry_device_data(device),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class TelemetryDeviceDetailView(APIView):
    http_method_names = ["get", "options"]
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DEVICES"
    permission_action = "VIEW"

    def get(self, request, device_id):
        device = get_object_or_404(TelemetryDevice, device_id=device_id)
        data = telemetry_device_data(device, include_history=True)
        data["can_manage"] = any(
            has_module_permission(request.user, "DEVICES", action)
            for action in ("PAIR", "REPLACE", "UNPAIR")
        )
        return Response(data)


class TelemetryDevicePairView(APIView):
    http_method_names = ["post", "options"]
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DEVICES"
    permission_action = "PAIR"

    def post(self, request, device_id):
        device = get_object_or_404(TelemetryDevice, device_id=device_id)
        serializer = TelemetryDevicePairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["replace_current"] and not has_module_permission(
            request.user, "DEVICES", "REPLACE"
        ):
            self.permission_denied(request)
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
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DEVICES"
    permission_action = "UNPAIR"

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


def emergency_sos_data(item):
    return {
        "id": item.pk,
        "device_id": item.device.device_id,
        "vehicle_id": item.vehicle_id,
        "driver_id": item.driver_id,
        "status": item.status,
        "source": item.source,
        "activated_at": item.activated_at,
        "cleared_at": item.cleared_at,
    }


class VehicleEmergencySOSView(APIView):
    http_method_names = ["get", "post", "options"]

    def get_permissions(self):
        if self.request.method == "POST":
            return [AllowAny()]
        permission = ModuleActionAccess()
        self.permission_module = "ALERTS_SOS"
        self.permission_action = "VIEW"
        return [StaffAccess(), permission]

    def post(self, request):
        serializer = VehicleEmergencySOSActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = serializer.context["device"]
        action = serializer.validated_data["action"]
        now = timezone.now()
        with transaction.atomic():
            active = (
                VehicleEmergencySOS.objects.select_for_update()
                .filter(device=device, status=VehicleEmergencySOS.Status.ACTIVE)
                .first()
            )
            if action == "CLEAR":
                if active is not None:
                    active.status = VehicleEmergencySOS.Status.CLEARED
                    active.cleared_at = now
                    active.save(update_fields=("status", "cleared_at"))
                return Response(
                    {
                        "status": "CLEARED",
                        "duplicate": active is None,
                        "sos": emergency_sos_data(active) if active else None,
                    }
                )
            if active is not None:
                return Response(
                    {"status": "ACTIVE", "duplicate": True, "sos": emergency_sos_data(active)}
                )
            binding = (
                device.bindings.select_related("vehicle").filter(unpaired_at__isnull=True).first()
            )
            vehicle = binding.vehicle if binding else None
            assignment = None
            if vehicle is not None:
                assignment = (
                    DispatchAssignment.objects.filter(
                        vehicle=vehicle,
                        transport_request__status=TransportRequest.Status.READY_FOR_DISPATCH,
                        accepted_at__isnull=False,
                        execution_status__in=ACTIVE_EXECUTION_STATUSES,
                    )
                    .order_by("transport_request__scheduled_pickup_at", "pk")
                    .first()
                )
            try:
                with transaction.atomic():
                    active = VehicleEmergencySOS.objects.create(
                        device=device,
                        vehicle=vehicle,
                        driver=assignment.driver if assignment else None,
                        status=VehicleEmergencySOS.Status.ACTIVE,
                        source=VehicleEmergencySOS.Source.PHYSICAL_BUTTON,
                        activated_at=now,
                    )
                    identity = vehicle.display_name if vehicle else device.device_id
                    transaction.on_commit(
                        lambda: notify_capability_users(
                            module="ALERTS_SOS",
                            action="VIEW",
                            notification_type=UserNotification.Type.SOS_ACTIVE,
                            title="Emergency SOS Active",
                            message=f"An emergency SOS was activated for {identity}.",
                            target_url="/alerts",
                            source_key=f"vehicle-emergency-sos:{active.pk}:active",
                        ),
                        robust=True,
                    )
            except IntegrityError:
                active = VehicleEmergencySOS.objects.get(
                    device=device, status=VehicleEmergencySOS.Status.ACTIVE
                )
                return Response(
                    {"status": "ACTIVE", "duplicate": True, "sos": emergency_sos_data(active)}
                )
        return Response(
            {"status": "ACTIVE", "duplicate": False, "sos": emergency_sos_data(active)},
            status=status.HTTP_201_CREATED,
        )

    def get(self, request):
        events = VehicleEmergencySOS.objects.select_related("device", "vehicle", "driver")
        device_id = request.query_params.get("device_id")
        if device_id:
            events = events.filter(device__device_id=device_id)
        return Response({"results": [emergency_sos_data(item) for item in events[:100]]})


class LatestVehicleStatusView(APIView):
    http_method_names = ["get", "options"]
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "LIVE_MAP"
    permission_action = "VIEW"

    def get(self, request, device_id):
        vehicle = get_object_or_404(Vehicle, device_id=device_id)
        return Response(latest_status_data(vehicle))


class FleetLiveVehicleListView(APIView):
    http_method_names = ["get", "options"]
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "LIVE_MAP"
    permission_action = "VIEW"

    def get(self, request):
        vehicles = list(Vehicle.objects.order_by("device_id"))
        vehicle_ids = [vehicle.pk for vehicle in vehicles]
        now = timezone.now()
        latest_events = (
            TelemetryEvent.objects.filter(
                vehicle_id__in=vehicle_ids,
                recorded_at__lte=current_telemetry_cutoff(now),
            )
            .order_by("vehicle_id", "-recorded_at", "-sequence_number", "-received_at", "-pk")
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
        active_sos_by_vehicle = {
            item.vehicle_id: item
            for item in VehicleEmergencySOS.objects.filter(
                vehicle_id__in=vehicle_ids,
                status=VehicleEmergencySOS.Status.ACTIVE,
            ).select_related("device")
        }

        demo_config = demo.configuration()
        simulated_vehicle_count = 0
        stale_cutoff = now - timedelta(seconds=settings.DISPATCH_TELEMETRY_MAX_AGE_SECONDS)
        results = []
        for vehicle in vehicles:
            event = event_by_vehicle.get(vehicle.pk)
            assignment = assignment_by_vehicle.get(vehicle.pk)
            active_sos = active_sos_by_vehicle.get(vehicle.pk)
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
                simulated_position = (
                    event.position_source == TelemetryEvent.PositionSource.SIMULATED_TEST
                )
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
                    "telemetry_source": "demo" if simulated_position else "real",
                    "is_demo_telemetry": simulated_position,
                }
                if simulated_position:
                    simulated_vehicle_count += 1
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
                        f"/api/v1/vehicles/{vehicle.device_id}/photo/" if vehicle.photo else None
                    ),
                    "is_active": vehicle.is_active,
                    "telemetry_state": telemetry_state,
                    "telemetry": telemetry,
                    "active_assignment": active_assignment,
                    "emergency_sos": emergency_sos_data(active_sos) if active_sos else None,
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


class FleetLiveAssignmentRouteView(APIView):
    http_method_names = ["get", "options"]
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "LIVE_MAP"
    permission_action = "VIEW"

    def get(self, request, assignment_id):
        assignment = get_object_or_404(
            DispatchAssignment.objects.select_related("transport_request", "vehicle"),
            pk=assignment_id,
        )
        try:
            active_route = active_assignment_route(assignment)
        except routing.RouteCoordinateError:
            return Response(
                {"detail": "This assignment has invalid route coordinates."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"route": DriverActiveRouteSerializer(active_route).data})


class FleetLiveVehicleTrailView(APIView):
    http_method_names = ["get", "options"]
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "LIVE_MAP"
    permission_action = "VIEW"

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
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DRIVER_SAFETY"
    permission_action = "VIEW"

    def get(self, request):
        allowed = {"event_type", "vehicle", "search", "date_from", "date_to", "page", "page_size"}
        unknown = set(request.query_params) - allowed
        if unknown:
            raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
        filters = SafetyEventFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        values = filters.validated_data
        events = (
            TelemetryEvent.objects.filter(
                driving_event__in=(
                    TelemetryEvent.DrivingEvent.HARSH_BRAKING,
                    TelemetryEvent.DrivingEvent.HARSH_ACCELERATION,
                    TelemetryEvent.DrivingEvent.SHARP_TURN,
                )
            )
            .select_related("vehicle", "device")
            .order_by("-recorded_at", "-sequence_number", "-received_at", "-pk")
        )
        if "event_type" in values:
            events = events.filter(driving_event=values["event_type"])
        if "vehicle" in values:
            events = events.filter(vehicle_id=values["vehicle"])
        search = values.get("search", "").strip()
        if search:
            events = events.filter(
                Q(vehicle__display_name__icontains=search)
                | Q(vehicle__plate_number__icontains=search)
                | Q(vehicle__device_id__icontains=search)
                | Q(device__device_id__icontains=search)
            )
        events = filter_datetime_range(events, values, "recorded_at")
        paginator = AlertPageNumberPagination()
        page = paginator.paginate_queryset(events, request, view=self)
        payload = [safety_event_payload(event) for event in page]
        response = paginator.get_paginated_response(payload)
        # Preserve the established Live Fleet response key while exposing standard pagination.
        response.data["events"] = payload
        return response


class SafetyEventFilterSerializer(serializers.Serializer):
    event_type = serializers.ChoiceField(
        choices=(
            TelemetryEvent.DrivingEvent.HARSH_BRAKING,
            TelemetryEvent.DrivingEvent.HARSH_ACCELERATION,
            TelemetryEvent.DrivingEvent.SHARP_TURN,
        ),
        required=False,
    )
    vehicle = serializers.IntegerField(required=False, min_value=1)
    search = serializers.CharField(required=False, allow_blank=True, max_length=120)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)

    def validate(self, attrs):
        if attrs.get("date_from") and attrs.get("date_to"):
            if attrs["date_from"] > attrs["date_to"]:
                raise serializers.ValidationError({"date_to": "Must be on or after date_from."})
        return attrs


class AlertPageNumberPagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = "page_size"
    max_page_size = 100


def filter_datetime_range(queryset, values, field_name):
    current_timezone = timezone.get_current_timezone()
    if "date_from" in values:
        start = timezone.make_aware(
            datetime.combine(values["date_from"], time.min), current_timezone
        )
        queryset = queryset.filter(**{f"{field_name}__gte": start})
    if "date_to" in values:
        end = timezone.make_aware(
            datetime.combine(values["date_to"] + timedelta(days=1), time.min),
            current_timezone,
        )
        queryset = queryset.filter(**{f"{field_name}__lt": end})
    return queryset


def safety_event_payload(event):
    return {
        "event_id": event.event_id,
        "event_type": event.driving_event,
        "recorded_at": event.recorded_at,
        "received_at": event.received_at,
        "latitude": event.location.y,
        "longitude": event.location.x,
        "position_source": event.position_source,
        "position_accuracy_m": numeric(event.position_accuracy_m),
        "speed_kph": numeric(event.gnss_speed_kph),
        "rpm": event.rpm,
        "coolant_c": numeric(event.coolant_c),
        "engine_load_pct": numeric(event.engine_load_pct),
        "obd_source": event.obd_source,
        "vehicle_id": event.vehicle_id,
        "device_id": event.device.device_id if event.device_id else event.vehicle.device_id,
        "vehicle_device_id": event.vehicle.device_id,
        "vehicle_name": event.vehicle.display_name,
        "plate_number": event.vehicle.plate_number,
    }


class GeofenceEventFilterSerializer(serializers.Serializer):
    geofence = serializers.UUIDField(required=False)
    vehicle = serializers.IntegerField(required=False, min_value=1)
    event_type = serializers.ChoiceField(
        choices=GeofenceEvent.EventType.values,
        required=False,
    )
    category = serializers.ChoiceField(choices=Geofence.Category.values, required=False)
    restricted_entry = serializers.BooleanField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)

    def validate(self, attrs):
        if attrs.get("date_from") and attrs.get("date_to"):
            if attrs["date_from"] > attrs["date_to"]:
                raise serializers.ValidationError({"date_to": "Must be on or after date_from."})
        return attrs


class GeofenceEventPagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = "page_size"
    max_page_size = 100


class GeofenceEventListView(APIView):
    http_method_names = ["get", "options"]
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "ALERTS_SOS"
    permission_action = "VIEW"

    def get(self, request):
        allowed = {
            "geofence",
            "vehicle",
            "event_type",
            "category",
            "restricted_entry",
            "date_from",
            "date_to",
            "page",
            "page_size",
        }
        unknown = set(request.query_params) - allowed
        if unknown:
            raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
        filters = GeofenceEventFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        values = filters.validated_data
        queryset = GeofenceEvent.objects.select_related(
            "geofence", "vehicle", "telemetry_event"
        ).order_by("-occurred_at", "-pk")
        if "geofence" in values:
            queryset = queryset.filter(geofence_id=values["geofence"])
        if "vehicle" in values:
            queryset = queryset.filter(vehicle_id=values["vehicle"])
        if "event_type" in values:
            queryset = queryset.filter(event_type=values["event_type"])
        if "category" in values:
            queryset = queryset.filter(geofence__category=values["category"])
        if values.get("restricted_entry"):
            queryset = queryset.filter(
                event_type=GeofenceEvent.EventType.ENTER,
                geofence__category=Geofence.Category.RESTRICTED,
            )
        queryset = filter_datetime_range(queryset, values, "occurred_at")
        paginator = GeofenceEventPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response([event_payload(event) for event in page])


class ActiveAttentionFilterSerializer(serializers.Serializer):
    source = serializers.ChoiceField(
        choices=("TELEMETRY", "INSPECTION", "MAINTENANCE"), required=False
    )
    condition = serializers.ChoiceField(
        choices=(
            "STALE_TELEMETRY",
            "NO_TELEMETRY",
            "FAILED_INSPECTION",
            "INSPECTION_NEEDS_ATTENTION",
            "MAINTENANCE_OPEN",
            "MAINTENANCE_SCHEDULED",
            "MAINTENANCE_IN_PROGRESS",
        ),
        required=False,
    )
    vehicle = serializers.IntegerField(required=False, min_value=1)
    search = serializers.CharField(required=False, allow_blank=True, max_length=120)
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)


def inspection_attention_payload(inspection):
    vehicle = inspection.vehicle
    condition = (
        "FAILED_INSPECTION"
        if inspection.result == VehicleInspection.Result.FAILED
        else "INSPECTION_NEEDS_ATTENTION"
    )
    return {
        "id": f"inspection:{inspection.pk}",
        "condition": condition,
        "source": "INSPECTION",
        "current_state": inspection.result,
        "last_updated_at": inspection.updated_at,
        "vehicle": {
            "id": vehicle.pk,
            "device_id": vehicle.device_id,
            "display_name": vehicle.display_name,
            "plate_number": vehicle.plate_number,
        },
        "details": {
            "inspection_id": inspection.pk,
            "inspection_date": inspection.inspection_date,
            "inspection_type": inspection.inspection_type,
            "result": inspection.result,
            "odometer_km": inspection.odometer_km,
            "fuel_level_percent": inspection.fuel_level_percent,
            "checklist": {
                field: getattr(inspection, field) for field in VehicleInspection.CHECKLIST_FIELDS
            },
            "issues_found": inspection.issues_found,
            "notes": inspection.notes,
            "inspector": (
                inspection.inspected_by.get_full_name().strip() or inspection.inspected_by.username
            ),
        },
    }


def maintenance_attention_payload(record):
    vehicle = record.vehicle
    return {
        "id": f"maintenance:{record.pk}",
        "condition": f"MAINTENANCE_{record.status}",
        "source": "MAINTENANCE",
        "current_state": record.status,
        "last_updated_at": record.updated_at,
        "vehicle": {
            "id": vehicle.pk,
            "device_id": vehicle.device_id,
            "display_name": vehicle.display_name,
            "plate_number": vehicle.plate_number,
        },
        "details": {
            "maintenance_id": record.pk,
            "title": record.title,
            "status": record.status,
            "maintenance_source": record.source,
            "linked_inspection": (
                {
                    "id": record.inspection_id,
                    "inspection_date": record.inspection.inspection_date,
                    "inspection_type": record.inspection.inspection_type,
                    "result": record.inspection.result,
                }
                if record.inspection_id
                else None
            ),
            "scheduled_at": record.scheduled_at,
            "started_at": record.started_at,
            "completed_at": record.completed_at,
            "notes": record.notes,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        },
    }


def active_attention_items(now):
    latest_telemetry = TelemetryEvent.objects.filter(
        vehicle_id=OuterRef("pk"), recorded_at__lte=current_telemetry_cutoff(now)
    ).order_by("-recorded_at", "-sequence_number", "-received_at", "-pk")
    latest_inspection = VehicleInspection.objects.filter(vehicle_id=OuterRef("pk")).order_by(
        *VehicleInspection._meta.ordering
    )
    vehicles = list(
        Vehicle.objects.filter(is_active=True).annotate(
            latest_telemetry_id=Subquery(latest_telemetry.values("pk")[:1]),
            latest_inspection_id=Subquery(latest_inspection.values("pk")[:1]),
        )
    )
    telemetry_by_id = {
        event.pk: event
        for event in TelemetryEvent.objects.filter(
            pk__in=[item.latest_telemetry_id for item in vehicles if item.latest_telemetry_id]
        ).select_related("device")
    }
    inspection_by_id = {
        inspection.pk: inspection
        for inspection in VehicleInspection.objects.filter(
            pk__in=[item.latest_inspection_id for item in vehicles if item.latest_inspection_id]
        ).select_related("vehicle", "inspected_by")
    }
    stale_cutoff = now - timedelta(seconds=settings.DISPATCH_TELEMETRY_MAX_AGE_SECONDS)
    items = []
    for vehicle in vehicles:
        event = telemetry_by_id.get(vehicle.latest_telemetry_id)
        if event is None or event.recorded_at < stale_cutoff:
            state = "NO_TELEMETRY" if event is None else "STALE"
            condition = "NO_TELEMETRY" if event is None else "STALE_TELEMETRY"
            items.append(
                {
                    "id": f"telemetry:{vehicle.pk}:{state.lower()}",
                    "condition": condition,
                    "source": "TELEMETRY",
                    "current_state": state,
                    "last_updated_at": event.recorded_at if event else None,
                    "vehicle": {
                        "id": vehicle.pk,
                        "device_id": vehicle.device_id,
                        "display_name": vehicle.display_name,
                        "plate_number": vehicle.plate_number,
                    },
                    "details": {
                        "latest_telemetry_at": event.recorded_at if event else None,
                        "telemetry_age_seconds": (
                            max(0, int((now - event.recorded_at).total_seconds()))
                            if event
                            else None
                        ),
                        "position_source": event.position_source if event else None,
                        "position_accuracy_m": (
                            numeric(event.position_accuracy_m) if event else None
                        ),
                        "latitude": event.location.y if event else None,
                        "longitude": event.location.x if event else None,
                        "speed_kph": numeric(event.gnss_speed_kph) if event else None,
                        "obd_source": event.obd_source if event else None,
                    },
                }
            )
        inspection = inspection_by_id.get(vehicle.latest_inspection_id)
        if inspection and inspection.result in (
            VehicleInspection.Result.FAILED,
            VehicleInspection.Result.NEEDS_ATTENTION,
        ):
            items.append(inspection_attention_payload(inspection))
    active_statuses = (
        VehicleMaintenanceRecord.Status.OPEN,
        VehicleMaintenanceRecord.Status.SCHEDULED,
        VehicleMaintenanceRecord.Status.IN_PROGRESS,
    )
    records = VehicleMaintenanceRecord.objects.filter(
        vehicle__is_active=True, status__in=active_statuses
    ).select_related("vehicle", "inspection")
    items.extend(maintenance_attention_payload(record) for record in records)
    items.sort(
        key=lambda item: (
            item["last_updated_at"] is not None,
            item["last_updated_at"] or datetime.min.replace(tzinfo=timezone.get_current_timezone()),
            item["id"],
        ),
        reverse=True,
    )
    return items


class ActiveAttentionListView(APIView):
    http_method_names = ["get", "options"]
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "ALERTS_SOS"
    permission_action = "VIEW"

    def get(self, request):
        allowed = {"source", "condition", "vehicle", "search", "page", "page_size"}
        unknown = set(request.query_params) - allowed
        if unknown:
            raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
        filters = ActiveAttentionFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        values = filters.validated_data
        now = timezone.now()
        all_items = active_attention_items(now)
        telemetry_attention_count = sum(item["source"] == "TELEMETRY" for item in all_items)
        items = all_items
        if "source" in values:
            items = [item for item in items if item["source"] == values["source"]]
        if "condition" in values:
            items = [item for item in items if item["condition"] == values["condition"]]
        if "vehicle" in values:
            items = [item for item in items if item["vehicle"]["id"] == values["vehicle"]]
        search = values.get("search", "").strip().lower()
        if search:
            items = [
                item
                for item in items
                if any(
                    search in str(item["vehicle"][field]).lower()
                    for field in ("display_name", "plate_number", "device_id")
                )
            ]
        paginator = AlertPageNumberPagination()
        page = paginator.paginate_queryset(items, request, view=self)
        response = paginator.get_paginated_response(page)
        today = timezone.localdate(now)
        response.data["summary"] = {
            "active_attention": len(all_items),
            "safety_events_today": TelemetryEvent.objects.filter(
                driving_event__in=(
                    TelemetryEvent.DrivingEvent.HARSH_BRAKING,
                    TelemetryEvent.DrivingEvent.HARSH_ACCELERATION,
                    TelemetryEvent.DrivingEvent.SHARP_TURN,
                ),
                recorded_at__date=today,
            ).count(),
            "restricted_entries_today": GeofenceEvent.objects.filter(
                event_type=GeofenceEvent.EventType.ENTER,
                geofence__category=Geofence.Category.RESTRICTED,
                occurred_at__date=today,
            ).count(),
            "vehicle_device_attention": telemetry_attention_count,
        }
        return response


class GeofenceListCreateView(APIView):
    http_method_names = ["get", "post", "options"]
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "LIVE_MAP"
    permission_actions = {"GET": "VIEW", "POST": "MANAGE_GEOFENCES"}

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
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "LIVE_MAP"
    permission_actions = {"GET": "VIEW", "PATCH": "MANAGE_GEOFENCES"}

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
