from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.db.models import Case, IntegerField, OuterRef, Q, Subquery, Value, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import StaffProfile
from accounts.permissions import StaffAccess
from accounts.roles import SUPER_ADMIN, resolve_role
from fleet.models import Vehicle

from . import matrix, places, routing, services
from .models import TransportRequest, TransportRequestEvent
from .serializers import (
    CalendarTransportRequestSerializer,
    NoteSerializer,
    TransportRequestDetailSerializer,
    TransportRequestListSerializer,
    VehicleAssignmentSerializer,
)


class TransportRequestPagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = "page_size"
    max_page_size = 100


def detail_response(item, request):
    return Response(TransportRequestDetailSerializer(item, context={"request": request}).data)


class TransportRequestListView(APIView):
    permission_classes = [StaffAccess]
    http_method_names = ["get", "post", "options"]

    def get(self, request):
        allowed = {
            "search",
            "status",
            "priority",
            "source_system",
            "request_type",
            "scheduled_date",
            "assignment",
            "ordering",
            "page",
            "page_size",
        }
        unknown = set(request.query_params) - allowed
        if unknown:
            raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
        latest_event = TransportRequestEvent.objects.filter(request_id=OuterRef("pk")).order_by(
            "-created_at", "-pk"
        )
        queryset = TransportRequest.objects.select_related(
            "assigned_vehicle", "created_by", "approved_by"
        ).annotate(
            latest_event_type=Subquery(latest_event.values("event_type")[:1]),
            latest_event_at=Subquery(latest_event.values("created_at")[:1]),
        )
        statuses = request.query_params.get("status", "")
        parsed_statuses = []
        if statuses:
            parsed_statuses = [value.strip() for value in statuses.split(",") if value.strip()]
            invalid = sorted(set(parsed_statuses) - set(TransportRequest.Status.values))
            if not parsed_statuses or invalid:
                raise serializers.ValidationError(
                    {"status": f"Invalid status value(s): {', '.join(invalid) or statuses}."}
                )
            queryset = queryset.filter(status__in=parsed_statuses)
        for field, choices in (
            ("priority", TransportRequest.Priority.values),
            ("source_system", TransportRequest.SourceSystem.values),
            ("request_type", TransportRequest.RequestType.values),
        ):
            value = request.query_params.get(field)
            if value:
                if value not in choices:
                    raise serializers.ValidationError({field: f"Invalid {field}."})
                queryset = queryset.filter(**{field: value})
        assignment = request.query_params.get("assignment", "all")
        if assignment not in {"all", "assigned", "unassigned"}:
            raise serializers.ValidationError(
                {"assignment": "Must be all, assigned, or unassigned."}
            )
        if assignment != "all":
            queryset = queryset.filter(assigned_vehicle__isnull=assignment == "unassigned")
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(request_number__icontains=search)
                | Q(requester_name__icontains=search)
                | Q(pickup_name__icontains=search)
                | Q(pickup_address__icontains=search)
                | Q(destination_name__icontains=search)
                | Q(destination_address__icontains=search)
                | Q(external_reference__icontains=search)
            )
        scheduled_date = request.query_params.get("scheduled_date")
        if scheduled_date:
            try:
                parsed = date.fromisoformat(scheduled_date)
            except ValueError as error:
                raise serializers.ValidationError({"scheduled_date": "Use YYYY-MM-DD."}) from error
            queryset = queryset.filter(scheduled_pickup_at__date=parsed)
        ordering = request.query_params.get("ordering", "scheduled_pickup_at")
        allowed_ordering = {
            "scheduled_pickup_at",
            "-scheduled_pickup_at",
            "created_at",
            "-created_at",
            "priority",
            "-priority",
            "request_number",
            "-request_number",
        }
        if ordering not in allowed_ordering:
            raise serializers.ValidationError({"ordering": "Invalid ordering field."})
        if parsed_statuses == [TransportRequest.Status.APPROVED]:
            queryset = queryset.annotate(
                assignment_order=Case(
                    When(assigned_vehicle__isnull=True, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            ).order_by("assignment_order", ordering, "request_number")
        else:
            queryset = queryset.order_by(ordering, "request_number")
        paginator = TransportRequestPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            TransportRequestListSerializer(page, many=True, context={"request": request}).data
        )

    def post(self, request):
        serializer = TransportRequestDetailSerializer(
            data=request.data, context={"request": request}
        )
        if not serializer.is_valid():
            response_status = (
                status.HTTP_409_CONFLICT
                if "external_reference" in serializer.errors
                and "already been imported" in str(serializer.errors["external_reference"])
                else status.HTTP_400_BAD_REQUEST
            )
            return Response(serializer.errors, status=response_status)
        try:
            saved = serializer.save()
        except serializers.ValidationError as error:
            if "external_reference" in error.detail:
                return Response(error.detail, status=status.HTTP_409_CONFLICT)
            raise
        return Response(
            TransportRequestDetailSerializer(saved, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class TransportRequestDetailView(APIView):
    permission_classes = [StaffAccess]
    http_method_names = ["get", "patch", "options"]

    def get_object(self, request_id):
        return get_object_or_404(
            TransportRequest.objects.select_related(
                "assigned_vehicle", "created_by", "approved_by"
            ).prefetch_related("events__performed_by"),
            pk=request_id,
        )

    def get(self, request, request_id):
        return detail_response(self.get_object(request_id), request)

    def patch(self, request, request_id):
        role = resolve_role(request.user)
        if role not in {
            SUPER_ADMIN,
            StaffProfile.Role.FLEET_MANAGER,
            StaffProfile.Role.DISPATCHER,
        }:
            self.permission_denied(
                request,
                message="Your role cannot edit transport requests.",
            )
        with transaction.atomic():
            item = get_object_or_404(
                TransportRequest.objects.select_for_update(),
                pk=request_id,
            )
            editable_statuses = {
                TransportRequest.Status.FOR_APPROVAL,
                TransportRequest.Status.NEEDS_MORE_DETAILS,
            }
            if item.status not in editable_statuses:
                return Response(
                    {
                        "status": (
                            "This request changed workflow status and can no longer "
                            "be edited. Reload the request before continuing."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            serializer = TransportRequestDetailSerializer(
                item, data=request.data, partial=True, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)


class TransportRequestRouteView(APIView):
    permission_classes = [StaffAccess]
    http_method_names = ["get", "options"]

    def get(self, request, request_id):
        item = get_object_or_404(TransportRequest, pk=request_id)
        try:
            return Response(routing.get_route(item))
        except routing.RouteCoordinateError:
            return Response(
                {"detail": "The transport request has invalid route coordinates."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except routing.RouteConfigurationError:
            return Response(
                {"detail": "Routing service is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except routing.RouteServiceError:
            return Response(
                {"detail": "Route unavailable."},
                status=status.HTTP_502_BAD_GATEWAY,
            )


def _places_error_response(error):
    if isinstance(error, places.PlacesConfigurationError):
        return Response(
            {"detail": "Location search is not configured."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if isinstance(error, places.PlacesUnavailableError):
        return Response(
            {"detail": "Location search temporarily unavailable."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if isinstance(error, places.PlacesNotFoundError):
        return Response({"detail": "Location was not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response({"detail": "Unable to search locations."}, status=status.HTTP_502_BAD_GATEWAY)


class PlaceSuggestView(APIView):
    permission_classes = [StaffAccess]
    http_method_names = ["post", "options"]

    def post(self, request):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["query"] = serializers.CharField(trim_whitespace=True, min_length=3)
        serializer.fields["session_id"] = serializers.UUIDField()
        serializer.is_valid(raise_exception=True)
        try:
            return Response(
                places.suggest(
                    serializer.validated_data["query"], serializer.validated_data["session_id"]
                )
            )
        except (places.PlacesConfigurationError, places.PlacesServiceError) as error:
            return _places_error_response(error)


class PlaceDetailsView(APIView):
    permission_classes = [StaffAccess]
    http_method_names = ["get", "options"]

    def get(self, request, place_type, place_id):
        serializer = serializers.Serializer(data=request.query_params)
        serializer.fields["session_id"] = serializers.UUIDField()
        serializer.is_valid(raise_exception=True)
        if place_type not in places.ALLOWED_TYPES:
            raise serializers.ValidationError({"type": "Unsupported place type."})
        try:
            return Response(
                places.details(place_type, place_id, serializer.validated_data["session_id"])
            )
        except (places.PlacesConfigurationError, places.PlacesServiceError) as error:
            return _places_error_response(error)


class DispatchMatrixView(APIView):
    permission_classes = [StaffAccess]
    http_method_names = ["post", "options"]

    def post(self, request):
        allowed = {"vehicle_ids", "request_ids"}
        unknown = set(request.data) - allowed if isinstance(request.data, dict) else set()
        if unknown:
            raise serializers.ValidationError({field: "Unknown field." for field in unknown})
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["vehicle_ids"] = serializers.ListField(
            child=serializers.RegexField(r"^[A-Z0-9][A-Z0-9._-]{0,63}$"),
            required=False,
            allow_empty=False,
        )
        serializer.fields["request_ids"] = serializers.ListField(
            child=serializers.UUIDField(),
            required=False,
            allow_empty=False,
        )
        serializer.is_valid(raise_exception=True)
        try:
            return Response(
                matrix.build_dispatch_matrix(
                    serializer.validated_data.get("vehicle_ids"),
                    serializer.validated_data.get("request_ids"),
                )
            )
        except matrix.MatrixCandidateError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except matrix.MatrixLimitError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except matrix.MatrixConfigurationError:
            return Response(
                {"detail": "Dispatch matrix service is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except matrix.MatrixUpstreamError:
            return Response(
                {"detail": "Dispatch matrix is temporarily unavailable."},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class SummaryView(APIView):
    permission_classes = [StaffAccess]

    def get(self, request):
        today = timezone.localdate()
        queryset = TransportRequest.objects.all()
        for_approval = queryset.filter(status=TransportRequest.Status.FOR_APPROVAL).count()
        needs_more_details = queryset.filter(
            status=TransportRequest.Status.NEEDS_MORE_DETAILS
        ).count()
        approved = queryset.filter(status=TransportRequest.Status.APPROVED)
        return Response(
            {
                "total": queryset.count(),
                "for_approval": for_approval,
                "needs_more_details": needs_more_details,
                "approval_queue": for_approval + needs_more_details,
                "dispatch_queue": approved.count(),
                "approved_unassigned": approved.filter(assigned_vehicle__isnull=True).count(),
                "approved_assigned": approved.filter(assigned_vehicle__isnull=False).count(),
                "ready_for_dispatch": queryset.filter(
                    status=TransportRequest.Status.READY_FOR_DISPATCH
                ).count(),
                "scheduled_today": queryset.filter(scheduled_pickup_at__date=today).count(),
                "high_priority": queryset.filter(
                    priority__in=[
                        TransportRequest.Priority.HIGH,
                        TransportRequest.Priority.URGENT,
                    ]
                ).count(),
            }
        )


class CalendarView(APIView):
    permission_classes = [StaffAccess]
    max_days = 31

    def get(self, request):
        try:
            start_date = date.fromisoformat(request.query_params.get("start", ""))
            end_date = date.fromisoformat(request.query_params.get("end", ""))
        except ValueError as error:
            raise serializers.ValidationError(
                {"date_range": "Start and end are required in YYYY-MM-DD format."}
            ) from error
        if end_date < start_date:
            raise serializers.ValidationError({"end": "End must not be before start."})
        if (end_date - start_date).days >= self.max_days:
            raise serializers.ValidationError(
                {"date_range": f"Calendar ranges may not exceed {self.max_days} days."}
            )
        current_timezone = timezone.get_current_timezone()
        range_start = timezone.make_aware(datetime.combine(start_date, time.min), current_timezone)
        range_end = timezone.make_aware(
            datetime.combine(end_date + timedelta(days=1), time.min), current_timezone
        )
        visible = list(
            TransportRequest.objects.select_related("assigned_vehicle", "created_by", "approved_by")
            .filter(
                scheduled_pickup_at__gte=range_start,
                scheduled_pickup_at__lt=range_end,
            )
            .exclude(
                status__in=[
                    TransportRequest.Status.REJECTED,
                    TransportRequest.Status.CANCELLED,
                ]
            )
            .order_by("scheduled_pickup_at", "request_number")
        )
        allocations = list(
            TransportRequest.objects.select_related("assigned_vehicle")
            .filter(
                assigned_vehicle__isnull=False,
                status__in=services.ALLOCATING_STATUSES,
                scheduled_pickup_at__gte=range_start - timedelta(days=1),
                scheduled_pickup_at__lt=range_end,
            )
            .order_by("scheduled_pickup_at")
        )
        conflict_sets = {item.pk: set() for item in visible}
        for index, first in enumerate(allocations):
            for second in allocations[index + 1 :]:
                if first.assigned_vehicle_id != second.assigned_vehicle_id:
                    continue
                if (
                    first.scheduled_pickup_at < services.planning_end(second)
                    and services.planning_end(first) > second.scheduled_pickup_at
                ):
                    if first.pk in conflict_sets:
                        conflict_sets[first.pk].add(second.request_number)
                    if second.pk in conflict_sets:
                        conflict_sets[second.pk].add(first.request_number)
        conflicts = {key: sorted(values) for key, values in conflict_sets.items() if values}
        serializer = CalendarTransportRequestSerializer(
            visible, many=True, context={"request": request, "conflicts": conflicts}
        )
        return Response(
            {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "timezone": str(current_timezone),
                "results": serializer.data,
            }
        )


class ActionView(APIView):
    permission_classes = [StaffAccess]
    action = None

    def post(self, request, request_id):
        item = get_object_or_404(
            TransportRequest.objects.select_related("assigned_vehicle"), pk=request_id
        )
        serializer = NoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated = self.action(item, request.user, serializer.validated_data["note"])
        except PermissionError:
            self.permission_denied(request)
        except services.AllocationConflict as error:
            return Response(error.detail, status=status.HTTP_409_CONFLICT)
        return detail_response(updated, request)


class ApproveView(ActionView):
    action = staticmethod(services.approve)


class RejectView(ActionView):
    action = staticmethod(services.reject)


class RequestMoreDetailsView(ActionView):
    action = staticmethod(services.request_more_details)


class ResubmitView(ActionView):
    action = staticmethod(services.resubmit)


class CancelView(ActionView):
    action = staticmethod(services.cancel)


class PrepareDispatchView(ActionView):
    action = staticmethod(services.prepare_dispatch)


class AssignVehicleView(APIView):
    permission_classes = [StaffAccess]

    def post(self, request, request_id):
        item = get_object_or_404(TransportRequest, pk=request_id)
        serializer = VehicleAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vehicle = get_object_or_404(
            Vehicle, device_id=serializer.validated_data["vehicle_device_id"]
        )
        try:
            updated = services.assign_vehicle(
                item, vehicle, request.user, serializer.validated_data["note"]
            )
        except PermissionError:
            self.permission_denied(request)
        except services.AllocationConflict as error:
            return Response(error.detail, status=status.HTTP_409_CONFLICT)
        return detail_response(updated, request)
