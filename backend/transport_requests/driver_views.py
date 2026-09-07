from datetime import timedelta

from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import DriverAccess
from telemetry.presentation import valid_position

from . import routing
from .acceptance import InvalidAssignmentAcceptance, accept_driver_assignment
from .driver_serializers import (
    DriverAssignmentAcceptanceSerializer,
    DriverExecutionSerializer,
    DriverExecutionTransitionSerializer,
    DriverRouteSerializer,
    DriverTripSerializer,
    DriverVehiclePositionSerializer,
)
from .execution import IllegalExecutionTransition, transition_driver_execution
from .models import DispatchAssignment, TransportRequest

DRIVER_TRIP_STATUSES = (TransportRequest.Status.READY_FOR_DISPATCH,)


def driver_trip_queryset(driver):
    return (
        DispatchAssignment.objects.filter(
            driver=driver,
            transport_request__status__in=DRIVER_TRIP_STATUSES,
        )
        .select_related("transport_request", "vehicle")
        .order_by("transport_request__scheduled_pickup_at", "transport_request_id")
    )


def driver_assignment_queryset(driver):
    return DispatchAssignment.objects.filter(driver=driver).select_related(
        "transport_request", "vehicle"
    )


class DriverTripListView(APIView):
    permission_classes = [DriverAccess]
    http_method_names = ["get", "options"]

    def get(self, request):
        assignments = driver_trip_queryset(request.driver)
        return Response({"trips": DriverTripSerializer(assignments, many=True).data})


class DriverTripDetailView(APIView):
    permission_classes = [DriverAccess]
    http_method_names = ["get", "options"]

    def get(self, request, trip_id):
        assignment = get_object_or_404(
            driver_trip_queryset(request.driver), transport_request_id=trip_id
        )
        return Response({"trip": DriverTripSerializer(assignment).data})


class DriverTripAcceptView(APIView):
    permission_classes = [DriverAccess]
    http_method_names = ["post", "options"]

    def post(self, request, trip_id):
        assignment = get_object_or_404(
            driver_assignment_queryset(request.driver), transport_request_id=trip_id
        )
        serializer = DriverAssignmentAcceptanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated, _ = accept_driver_assignment(
                assignment_id=assignment.pk,
                driver=request.driver,
                user=request.user,
                expected_confirmed_at=serializer.validated_data["confirmed_at"],
            )
        except DispatchAssignment.DoesNotExist as error:
            raise Http404 from error
        except InvalidAssignmentAcceptance as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        return Response({"trip": DriverTripSerializer(updated).data})


class DriverTripRouteView(APIView):
    permission_classes = [DriverAccess]
    http_method_names = ["get", "options"]

    def get(self, request, trip_id):
        assignment = get_object_or_404(
            driver_trip_queryset(request.driver), transport_request_id=trip_id
        )
        try:
            route = routing.get_route(assignment.transport_request)
        except routing.RouteCoordinateError:
            return Response(
                {"detail": "This trip has invalid route coordinates."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except routing.RouteConfigurationError:
            return Response(
                {"detail": "Route currently unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except routing.RouteServiceError:
            return Response(
                {"detail": "Route currently unavailable."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"route": DriverRouteSerializer(route).data})


class DriverTripVehiclePositionView(APIView):
    permission_classes = [DriverAccess]
    http_method_names = ["get", "options"]

    def get(self, request, trip_id):
        assignment = get_object_or_404(
            driver_trip_queryset(request.driver), transport_request_id=trip_id
        )
        event = assignment.vehicle.telemetry_events.first()
        coordinates = valid_position(event)
        if event is None or coordinates is None:
            return Response({"vehicle_position": None})
        cutoff = timezone.now() - timedelta(
            seconds=settings.DISPATCH_TELEMETRY_MAX_AGE_SECONDS
        )
        position = {
            **coordinates,
            "recorded_at": event.recorded_at,
            "is_stale": event.recorded_at < cutoff,
        }
        return Response(
            {"vehicle_position": DriverVehiclePositionSerializer(position).data}
        )


class DriverTripTransitionView(APIView):
    permission_classes = [DriverAccess]
    http_method_names = ["post", "options"]

    def post(self, request, trip_id):
        assignment = get_object_or_404(
            driver_assignment_queryset(request.driver), transport_request_id=trip_id
        )
        serializer = DriverExecutionTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated, _ = transition_driver_execution(
                assignment_id=assignment.pk,
                driver=request.driver,
                user=request.user,
                action=serializer.validated_data["action"],
            )
        except DispatchAssignment.DoesNotExist as error:
            raise Http404 from error
        except IllegalExecutionTransition as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        return Response({"execution": DriverExecutionSerializer(updated).data})
