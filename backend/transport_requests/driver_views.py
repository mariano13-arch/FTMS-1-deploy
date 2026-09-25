import logging
import mimetypes

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import DriverAccess
from telemetry.presentation import valid_position

from . import matrix, routing
from .acceptance import InvalidAssignmentAcceptance, accept_driver_assignment
from .active_routes import active_assignment_route
from .driver_serializers import (
    DriverActiveRouteSerializer,
    DriverAssignmentAcceptanceSerializer,
    DriverExecutionSerializer,
    DriverExecutionTransitionSerializer,
    DriverReceiptCreateSerializer,
    DriverReceiptOcrPreviewSerializer,
    DriverReceiptSerializer,
    DriverTripSerializer,
    DriverVehiclePositionSerializer,
)
from .execution import (
    ACTIVE_EXECUTION_STATUSES,
    IllegalExecutionTransition,
    transition_driver_execution,
)
from .models import DispatchAssignment, TransportRequest, TripExpenseReceipt
from .receipt_ocr import InvalidReceiptImage, ReceiptOcrError, analyze_receipt

logger = logging.getLogger(__name__)

DRIVER_TRIP_STATUSES = (TransportRequest.Status.READY_FOR_DISPATCH,)
RECEIPT_ELIGIBLE_EXECUTION_STATUSES = (
    *ACTIVE_EXECUTION_STATUSES,
    DispatchAssignment.ExecutionStatus.COMPLETED,
)


def driver_trip_queryset(driver):
    return (
        DispatchAssignment.objects.filter(
            driver=driver,
            transport_request__status__in=DRIVER_TRIP_STATUSES,
        )
        .select_related("transport_request", "transport_request__flight_context", "vehicle")
        .order_by("transport_request__scheduled_pickup_at", "transport_request_id")
    )


def driver_assignment_queryset(driver):
    return DispatchAssignment.objects.filter(driver=driver).select_related(
        "transport_request", "transport_request__flight_context", "vehicle"
    )


def driver_receipt_assignment_queryset(driver):
    return driver_assignment_queryset(driver).filter(
        transport_request__status=TransportRequest.Status.READY_FOR_DISPATCH,
        accepted_at__isnull=False,
        execution_status__in=RECEIPT_ELIGIBLE_EXECUTION_STATUSES,
    )


def receipt_queryset(driver):
    return TripExpenseReceipt.objects.filter(driver=driver).select_related(
        "dispatch_assignment",
        "dispatch_assignment__transport_request",
        "driver",
        "vehicle",
    )


def has_duplicate_warning(assignment, values):
    queryset = TripExpenseReceipt.objects.filter(
        dispatch_assignment=assignment,
        expense_type=values["expense_type"],
    )
    receipt_number = values.get("receipt_number", "").strip()
    if receipt_number and queryset.filter(receipt_number__iexact=receipt_number).exists():
        return True
    return queryset.filter(
        amount=values["amount"],
        transaction_at=values["transaction_at"],
    ).exists()


class DriverReceiptPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


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
        if assignment.accepted_at is None:
            return Response(
                {"detail": "Accept this trip before requesting active routing."},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            route = active_assignment_route(assignment)
        except routing.RouteCoordinateError:
            return Response(
                {"detail": "This trip has invalid route coordinates."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"route": DriverActiveRouteSerializer(route).data})


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
        position = {
            **coordinates,
            "recorded_at": event.recorded_at,
            "is_stale": not matrix.dispatch_position_is_eligible(
                assignment.vehicle, event
            ),
            "source": event.position_source,
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


class DriverTripReceiptListCreateView(APIView):
    permission_classes = [DriverAccess]
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ["get", "post", "options"]

    def get_assignment(self, request, trip_id):
        return get_object_or_404(
            driver_receipt_assignment_queryset(request.driver),
            transport_request_id=trip_id,
        )

    def get(self, request, trip_id):
        assignment = self.get_assignment(request, trip_id)
        queryset = receipt_queryset(request.driver).filter(
            dispatch_assignment=assignment
        ).order_by("-transaction_at", "-created_at", "-pk")
        paginator = DriverReceiptPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(DriverReceiptSerializer(page, many=True).data)

    def post(self, request, trip_id):
        assignment = self.get_assignment(request, trip_id)
        serializer = DriverReceiptCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        duplicate_warning = has_duplicate_warning(assignment, serializer.validated_data)
        receipt = serializer.save(
            dispatch_assignment=assignment,
            driver=request.driver,
            vehicle=assignment.vehicle,
        )
        receipt._duplicate_warning = duplicate_warning
        return Response(DriverReceiptSerializer(receipt).data, status=status.HTTP_201_CREATED)


class DriverTripReceiptOcrPreviewView(APIView):
    permission_classes = [DriverAccess]
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ["post", "options"]

    def post(self, request, trip_id):
        get_object_or_404(
            driver_receipt_assignment_queryset(request.driver),
            transport_request_id=trip_id,
        )
        serializer = DriverReceiptOcrPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        expense_type = serializer.validated_data["expense_type"]
        try:
            result = analyze_receipt(serializer.validated_data["receipt_image"], expense_type)
        except InvalidReceiptImage as error:
            return Response(
                {"receipt_image": [str(error)]}, status=status.HTTP_400_BAD_REQUEST
            )
        except ReceiptOcrError:
            logger.error("Receipt OCR processing failed")
            result = None

        if result is None:
            candidates = {key: None for key in (
                "merchant_or_operator", "transaction_at", "transaction_date", "amount",
                "receipt_number",
            )}
            if expense_type == TripExpenseReceipt.ExpenseType.FUEL:
                candidates.update(
                    liters=None, unit_price=None, fuel_type=None, fuel_grade=None
                )
            else:
                candidates["toll_plaza"] = None
            warnings = ["Receipt analysis is unavailable. Enter the values manually."]
        else:
            candidates = result.candidates
            warnings = result.warnings
        return Response(
            {"expense_type": expense_type, "candidates": candidates, "warnings": warnings}
        )


class DriverReceiptDetailView(APIView):
    permission_classes = [DriverAccess]
    http_method_names = ["get", "options"]

    def get(self, request, receipt_id):
        receipt = get_object_or_404(receipt_queryset(request.driver), pk=receipt_id)
        return Response(DriverReceiptSerializer(receipt).data)


class DriverReceiptImageView(APIView):
    permission_classes = [DriverAccess]
    http_method_names = ["get", "options"]

    def get(self, request, receipt_id):
        receipt = get_object_or_404(receipt_queryset(request.driver), pk=receipt_id)
        content_type = (
            mimetypes.guess_type(receipt.receipt_image.name)[0]
            or "application/octet-stream"
        )
        return FileResponse(
            receipt.receipt_image.open("rb"),
            content_type=content_type,
            as_attachment=False,
            filename=receipt.receipt_image.name.rsplit("/", 1)[-1],
        )
