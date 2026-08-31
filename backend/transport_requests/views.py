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
from fleet.models import Driver, Vehicle

from . import consolidation, dispatch, matrix, places, routing, services
from .models import (
    DispatchAssignment,
    DispatchAssignmentEvent,
    TransportRequest,
    TransportRequestEvent,
)
from .serializers import (
    AssignedVehicleSerializer,
    CalendarTransportRequestSerializer,
    DispatchAssignmentSerializer,
    DispatchConfirmationSerializer,
    DispatchDriverSerializer,
    DispatchPlanSerializer,
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
        self.permission_denied(
            request,
            message=(
                "Transport Request creation requires a trusted HMS/RMS "
                "integration identity."
            ),
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


class DispatchBoardView(APIView):
    permission_classes = [StaffAccess]

    def get(self, request):
        requests = list(
            TransportRequest.objects.filter(
                status__in=(
                    TransportRequest.Status.APPROVED,
                    TransportRequest.Status.READY_FOR_DISPATCH,
                )
            )
            .select_related("assigned_vehicle", "created_by", "approved_by")
            .order_by("scheduled_pickup_at", "pk")
        )
        assignments = list(DispatchAssignment.objects.filter(
            transport_request__in=requests
        ).select_related("transport_request", "vehicle", "driver", "confirmed_by"))
        assignment_by_request = {
            assignment.transport_request_id: assignment for assignment in assignments
        }
        drivers = [
            driver
            for driver in Driver.objects.all()
            if dispatch.driver_eligibility(driver)[0] == "ELIGIBLE"
        ]
        vehicles = Vehicle.objects.filter(is_active=True).order_by("device_id")
        located_vehicle_ids = {
            item["vehicle_id"] for item in matrix.eligible_vehicle_origins()
        }
        approved = [item for item in requests if item.status == TransportRequest.Status.APPROVED]
        confirmed_count = sum(item.pk in assignment_by_request for item in approved)
        awaiting = [item for item in approved if item.pk not in assignment_by_request]
        optimizer_eligible = sum(
            any(
                vehicle.device_id in located_vehicle_ids
                and not services.allocation_conflicts(item, vehicle)
                and (
                    vehicle.passenger_capacity is None
                    or vehicle.passenger_capacity >= item.passenger_count
                )
                and (
                    not item.required_vehicle_type
                    or vehicle.vehicle_type == item.required_vehicle_type
                )
                for vehicle in vehicles
            )
            and any(not dispatch.driver_conflicts(item, driver) for driver in drivers)
            for item in awaiting
        )
        no_eligible_driver = schedule_conflict = no_gis_vehicle = 0
        for item in awaiting:
            if not drivers:
                no_eligible_driver += 1
                continue
            available_drivers = [
                driver for driver in drivers if not dispatch.driver_conflicts(item, driver)
            ]
            if not available_drivers:
                schedule_conflict += 1
                continue
            has_gis_vehicle = any(
                vehicle.device_id in located_vehicle_ids
                and not services.allocation_conflicts(item, vehicle)
                and (
                    vehicle.passenger_capacity is None
                    or vehicle.passenger_capacity >= item.passenger_count
                )
                and (
                    not item.required_vehicle_type
                    or vehicle.vehicle_type == item.required_vehicle_type
                )
                for vehicle in vehicles
            )
            if not has_gis_vehicle:
                no_gis_vehicle += 1
        assignment_events = DispatchAssignmentEvent.objects.filter(
            assignment__in=assignments
        ).select_related(
            "assignment__transport_request", "new_driver", "new_vehicle", "performed_by",
            "previous_driver", "previous_vehicle",
        )
        audit_by_request = {str(item.pk): [] for item in requests}
        for event in assignment_events:
            audit_by_request[str(event.assignment.transport_request_id)].append(
                {
                    "kind": (
                        "ASSIGNMENT_CHANGED"
                        if event.previous_driver_id or event.previous_vehicle_id
                        else "ASSIGNMENT_CONFIRMED"
                    ),
                    "driver": DispatchDriverSerializer(event.new_driver).data,
                    "vehicle": AssignedVehicleSerializer(event.new_vehicle).data,
                    "selection_mode": event.selection_mode,
                    "reason": event.reason,
                    "operator": (
                        event.performed_by.get_full_name().strip()
                        or event.performed_by.username
                    ),
                    "timestamp": event.created_at,
                }
            )
        prepare_events = TransportRequestEvent.objects.filter(
            request__in=requests, event_type="PREPARED_FOR_DISPATCH"
        ).select_related("performed_by")
        for event in prepare_events:
            audit_by_request[str(event.request_id)].append(
                {
                    "kind": "PREPARED_FOR_DISPATCH",
                    "reason": event.note,
                    "operator": (
                        event.performed_by.get_full_name().strip()
                        or event.performed_by.username
                    ),
                    "timestamp": event.created_at,
                }
            )
        for events in audit_by_request.values():
            events.sort(key=lambda item: item["timestamp"])
        manual_candidates = {}
        for item in approved:
            existing_id = (
                assignment_by_request[item.pk].pk
                if item.pk in assignment_by_request
                else None
            )
            manual_candidates[str(item.pk)] = {
                "drivers": DispatchDriverSerializer(
                    [
                        driver
                        for driver in drivers
                        if not dispatch.driver_conflicts(
                            item, driver, exclude_assignment_id=existing_id
                        )
                    ],
                    many=True,
                ).data,
                "vehicles": [
                    {
                        **AssignedVehicleSerializer(vehicle).data,
                        "current_location_available": (
                            vehicle.device_id in located_vehicle_ids
                        ),
                    }
                    for vehicle in vehicles
                    if not services.allocation_conflicts(item, vehicle)
                    and (
                        vehicle.passenger_capacity is None
                        or vehicle.passenger_capacity >= item.passenger_count
                    )
                    and (
                        not item.required_vehicle_type
                        or vehicle.vehicle_type == item.required_vehicle_type
                    )
                ],
            }
        return Response(
            {
                "summary": {
                    "approved_requests": len(approved),
                    "awaiting_assignment": len(awaiting),
                    "confirmed_assignments": confirmed_count,
                    "ready_for_dispatch": sum(
                        item.status == TransportRequest.Status.READY_FOR_DISPATCH
                        for item in requests
                    ),
                    "optimizer_eligible": optimizer_eligible,
                    "needs_attention": len(awaiting) - optimizer_eligible,
                    "no_eligible_driver": no_eligible_driver,
                    "no_gis_vehicle": no_gis_vehicle,
                    "schedule_conflict": schedule_conflict,
                },
                "requests": TransportRequestListSerializer(
                    requests, many=True, context={"request": request}
                ).data,
                "assignments": DispatchAssignmentSerializer(assignments, many=True).data,
                "eligible_drivers": DispatchDriverSerializer(drivers, many=True).data,
                "active_vehicles": [
                    {
                        **AssignedVehicleSerializer(vehicle).data,
                        "current_location_available": vehicle.device_id in located_vehicle_ids,
                    }
                    for vehicle in vehicles
                ],
                "manual_candidates": manual_candidates,
                "assignment_audit": audit_by_request,
            }
        )


class DispatchRecommendationView(APIView):
    permission_classes = [StaffAccess]

    def post(self, request):
        request_ids = request.data.get("request_ids") if isinstance(request.data, dict) else None
        if request_ids is not None:
            field = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
            request_ids = field.run_validation(request_ids)
        try:
            result = dispatch.recommendations(request_ids)
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
        recommendations = []
        for item in result["recommendations"]:
            recommendations.append(
                {
                    "transport_request_id": item["transport_request"].pk,
                    "request_number": item["transport_request"].request_number,
                    "recommended_vehicle": AssignedVehicleSerializer(item["vehicle"]).data,
                    "recommended_driver": DispatchDriverSerializer(item["driver"]).data,
                    "travel_time_seconds": item["travel_time_seconds"],
                    "distance_meters": item["distance_meters"],
                    "traffic_delay_seconds": item["traffic_delay_seconds"],
                    "recommendation_token": item["recommendation_token"],
                    "explanation": item["explanation"],
                    "schedule_context": item["schedule_context"],
                    "gis_preview": item["gis_preview"],
                }
            )
        comparisons = {}
        for request_id, candidates in result.get("candidate_comparison", {}).items():
            comparisons[request_id] = [
                {
                    "driver": DispatchDriverSerializer(item["driver"]).data,
                    "vehicle": AssignedVehicleSerializer(item["vehicle"]).data,
                    "travel_time_seconds": item["travel_time_seconds"],
                    "distance_meters": item["distance_meters"],
                    "traffic_delay_seconds": item["traffic_delay_seconds"],
                    "result": item["result"],
                }
                for item in candidates
            ]
        return Response(
            {
                "generated_at": result["generated_at"],
                "optimizer": "GOOGLE_OR_TOOLS",
                "routing_source": "TOMTOM",
                "requests_considered": result["considered"],
                "requests_recommended": len(recommendations),
                "recommendations": recommendations,
                "unassigned": [
                    {
                        "transport_request_id": item["transport_request"].pk,
                        "request_number": item["transport_request"].request_number,
                        "reason": item["reason"],
                    }
                    for item in result["unassigned"]
                ],
                "candidate_comparison": comparisons,
                "excluded_candidates": result.get("excluded_candidates", {}),
                "comparison_scope": {
                    "limit": result.get("comparison_limit", dispatch.CANDIDATE_COMPARISON_LIMIT),
                    "limited": any(
                        len(items)
                        >= result.get(
                            "comparison_limit", dispatch.CANDIDATE_COMPARISON_LIMIT
                        )
                        for items in comparisons.values()
                    ),
                },
            }
        )


class DispatchConfirmationView(APIView):
    permission_classes = [StaffAccess]

    def post(self, request):
        serializer = DispatchConfirmationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            assignment = dispatch.confirm_assignment(
                user=request.user, **serializer.validated_data
            )
        except PermissionError:
            self.permission_denied(request)
        except TransportRequest.DoesNotExist:
            return Response({"detail": "Transport request was not found."}, status=404)
        return Response(
            DispatchAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED
        )


class ConsolidationRecommendationView(APIView):
    permission_classes = [StaffAccess]

    def post(self, request):
        field = serializers.UUIDField()
        selected_request_id = field.run_validation(request.data.get("selected_request_id"))
        try:
            result = consolidation.recommendations(selected_request_id)
        except TransportRequest.DoesNotExist:
            return Response({"detail": "Transport request was not found."}, status=404)
        except matrix.MatrixLimitError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except matrix.MatrixConfigurationError:
            return Response({"detail": "Dispatch matrix service is not configured."}, status=503)
        except matrix.MatrixUpstreamError:
            return Response({"detail": "Dispatch matrix is temporarily unavailable."}, status=502)
        recommendation = result["recommendation"]
        if recommendation:
            recommendation = {
                "request_ids": recommendation["request_ids"],
                "requests": TransportRequestListSerializer(
                    recommendation["requests"], many=True, context={"request": request}
                ).data,
                "driver": DispatchDriverSerializer(recommendation["driver"]).data,
                "vehicle": AssignedVehicleSerializer(recommendation["vehicle"]).data,
                "route": recommendation["route"],
                "explanation": recommendation["explanation"],
                "recommendation_token": recommendation["recommendation_token"],
                "geometry": None,
            }
        return Response(
            {
                "generated_at": result["generated_at"],
                "optimizer": "GOOGLE_OR_TOOLS_ROUTING_MODEL",
                "routing_source": "TOMTOM",
                "candidate_limit": result["limit"],
                "recommendation": recommendation,
                "exclusions": result["exclusions"],
            }
        )


class ConsolidationConfirmationView(APIView):
    permission_classes = [StaffAccess]

    def post(self, request):
        token = serializers.CharField().run_validation(request.data.get("recommendation_token"))
        try:
            plan = consolidation.confirm(token, request.user)
        except PermissionError:
            self.permission_denied(request)
        return Response(DispatchPlanSerializer(plan).data, status=status.HTTP_201_CREATED)


class ConsolidationPrepareView(APIView):
    permission_classes = [StaffAccess]

    def post(self, request, plan_id):
        try:
            plan = consolidation.prepare(plan_id, request.user)
        except PermissionError:
            self.permission_denied(request)
        return Response(DispatchPlanSerializer(plan).data)


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
