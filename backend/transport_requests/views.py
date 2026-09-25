from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.db.models import (
    Case,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import ModuleActionAccess, StaffAccess
from accounts.roles import has_module_permission
from fleet.inspection_readiness import inspection_readiness, with_latest_inspection
from fleet.maintenance import maintenance_readiness, with_maintenance_readiness
from fleet.models import Driver, Vehicle
from fleet.number_coding import evaluate_vehicle_number_coding

from . import consolidation, dispatch, flight_tracking, matrix, places, routing, services
from .active_routes import recommendation_route
from .domain import is_supply_request
from .driver_serializers import DriverActiveRouteSerializer
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
    OperationalAssignmentSerializer,
    TransportRequestDetailSerializer,
    TransportRequestListSerializer,
    VehicleAssignmentSerializer,
)


class TransportRequestPagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = "page_size"
    max_page_size = 100


class DispatchAssignmentListView(APIView):
    """Read-only staff view of authoritative active or completed executions."""

    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DISPATCH_BOARD"
    permission_action = "VIEW"
    http_method_names = ["get", "options"]

    def get(self, request):
        allowed = {"scope", "search", "page", "page_size"}
        unknown = set(request.query_params) - allowed
        if unknown:
            raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
        scope = request.query_params.get("scope", "active")
        if scope not in {"active", "completed"}:
            raise serializers.ValidationError({"scope": "Must be active or completed."})
        queryset = DispatchAssignment.objects.select_related(
            "transport_request",
            "transport_request__assigned_vehicle",
            "transport_request__created_by",
            "transport_request__approved_by",
            "vehicle",
            "driver",
            "confirmed_by",
        )
        if scope == "completed":
            queryset = queryset.filter(
                execution_status=DispatchAssignment.ExecutionStatus.COMPLETED
            ).order_by("-completed_at", "-pk")
        else:
            queryset = queryset.exclude(
                execution_status=DispatchAssignment.ExecutionStatus.COMPLETED
            ).order_by("transport_request__scheduled_pickup_at", "pk")
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(transport_request__request_number__icontains=search)
                | Q(transport_request__requester_name__icontains=search)
                | Q(transport_request__pickup_name__icontains=search)
                | Q(transport_request__destination_name__icontains=search)
                | Q(driver__driver_code__icontains=search)
                | Q(driver__first_name__icontains=search)
                | Q(driver__last_name__icontains=search)
                | Q(vehicle__device_id__icontains=search)
                | Q(vehicle__plate_number__icontains=search)
            )
        paginator = TransportRequestPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            OperationalAssignmentSerializer(page, many=True).data
        )


def detail_response(item, request):
    return Response(TransportRequestDetailSerializer(item, context={"request": request}).data)


class TransportRequestListView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "TRANSPORT_REQUESTS"
    permission_action = "VIEW"
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
                "Transport Request creation requires a trusted HMS, RMS, or supply-chain "
                "integration identity."
            ),
        )


class TransportRequestDetailView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "TRANSPORT_REQUESTS"
    permission_actions = {"GET": "VIEW", "PATCH": "EDIT"}
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
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "TRANSPORT_REQUESTS"
    permission_action = "VIEW"
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


class FlightRefreshView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "TRANSPORT_REQUESTS"
    permission_action = "EDIT"
    http_method_names = ["post", "options"]

    def post(self, request, request_id):
        try:
            services.require_role(request.user, services.OPERATORS)
        except PermissionError:
            self.permission_denied(request, message="Your role cannot refresh flight data.")
        item = get_object_or_404(
            TransportRequest.objects.select_related("flight_context"), pk=request_id
        )
        if item.request_type != TransportRequest.RequestType.AIRPORT_PICKUP:
            raise serializers.ValidationError(
                {"request_type": "Flight refresh is only available for airport pickups."}
            )
        if not hasattr(item, "flight_context"):
            raise serializers.ValidationError(
                {"flight_context": "Add a flight number before refreshing flight data."}
            )
        flight_tracking.refresh_flight_context(item.flight_context)
        return Response(
            TransportRequestDetailSerializer(item, context={"request": request}).data,
            status=status.HTTP_200_OK,
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
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "TRANSPORT_REQUESTS"
    permission_action = "VIEW"
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
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "TRANSPORT_REQUESTS"
    permission_action = "VIEW"
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
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DISPATCH_BOARD"
    permission_action = "VIEW"
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
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DISPATCH_BOARD"
    permission_action = "VIEW"

    @staticmethod
    def payload(request):
        requests = list(
            TransportRequest.objects.filter(
                status=TransportRequest.Status.READY_FOR_DISPATCH,
                dispatch_assignment__isnull=True,
            )
            .select_related("assigned_vehicle", "created_by", "approved_by", "flight_context")
            .order_by("scheduled_pickup_at", "pk")
        )
        assignments = list(
            DispatchAssignment.objects.filter(
                transport_request__status=TransportRequest.Status.READY_FOR_DISPATCH
            )
            .select_related("transport_request", "vehicle", "driver", "confirmed_by")
            .order_by("transport_request__scheduled_pickup_at", "pk")
        )
        assigned_requests = [assignment.transport_request for assignment in assignments]
        board_context_requests = [*requests, *assigned_requests]
        drivers = [
            driver
            for driver in Driver.objects.all()
            if dispatch.driver_eligibility(driver)[0] == "ELIGIBLE"
        ]
        vehicles = [
            vehicle
            for vehicle in with_maintenance_readiness(
                with_latest_inspection(
                    Vehicle.objects.filter(is_active=True).order_by("device_id")
                )
            )
            if inspection_readiness(vehicle).eligible
            and maintenance_readiness(vehicle).eligible
        ]
        located_vehicle_ids = {
            item["vehicle_id"]
            for item in matrix.eligible_vehicle_origins(
                [vehicle.device_id for vehicle in vehicles]
            )
        }
        approved_count = TransportRequest.objects.filter(
            status=TransportRequest.Status.APPROVED,
            dispatch_assignment__isnull=True,
        ).count()
        confirmed_count = len(assignments)
        awaiting = requests
        busy_drivers = {}
        for assignment in DispatchAssignment.objects.filter(
            transport_request__status__in=(
                TransportRequest.Status.APPROVED, TransportRequest.Status.READY_FOR_DISPATCH
            )
        ).exclude(
            execution_status=DispatchAssignment.ExecutionStatus.COMPLETED
        ).select_related("transport_request"):
            busy_drivers.setdefault(assignment.driver_id, []).append(assignment.transport_request)
        busy_vehicles = {}
        for occupied in TransportRequest.objects.filter(
            assigned_vehicle__isnull=False, status__in=services.ALLOCATING_STATUSES
        ).exclude(dispatch_assignment__execution_status="COMPLETED"):
            busy_vehicles.setdefault(occupied.assigned_vehicle_id, []).append(occupied)

        def overlaps(item, other):
            return (
                other.scheduled_pickup_at < services.planning_end(item)
                and services.planning_end(other) > item.scheduled_pickup_at
            )

        def available_drivers(item):
            return [
                driver for driver in drivers
                if dispatch.evaluate_driver_schedule(
                    driver, item.scheduled_pickup_at
                ).status == "ON_SHIFT"
                and not any(overlaps(item, other) for other in busy_drivers.get(driver.pk, ()))
            ]

        def available_vehicles(item):
            return [
                vehicle for vehicle in vehicles
                if not any(
                    other.pk != item.pk and overlaps(item, other)
                    for other in busy_vehicles.get(vehicle.pk, ())
                )
                and (
                    vehicle.passenger_capacity is None
                    or vehicle.passenger_capacity >= item.passenger_count
                )
                and (
                    not item.required_vehicle_type
                    or vehicle.vehicle_type == item.required_vehicle_type
                )
            ]

        candidates = {
            item.pk: (available_drivers(item), available_vehicles(item)) for item in awaiting
        }
        coding = {
            item.pk: {
                vehicle.pk: evaluate_vehicle_number_coding(vehicle, item.scheduled_pickup_at)
                for vehicle in candidate_vehicles
            }
            for item, (_, candidate_vehicles) in (
                (item, candidates[item.pk]) for item in awaiting
            )
        }
        optimizer_eligible = sum(
            bool(candidate_drivers) and any(
                vehicle.device_id in located_vehicle_ids
                and coding[item.pk][vehicle.pk].eligible
                for vehicle in candidate_vehicles
            )
            for item in awaiting
            for candidate_drivers, candidate_vehicles in [candidates[item.pk]]
        )
        no_eligible_driver = schedule_conflict = no_gis_vehicle = 0
        for item in awaiting:
            if not drivers:
                no_eligible_driver += 1
                continue
            candidate_drivers, candidate_vehicles = candidates[item.pk]
            if not candidate_drivers:
                schedule_conflict += 1
                continue
            has_gis_vehicle = any(
                vehicle.device_id in located_vehicle_ids
                and coding[item.pk][vehicle.pk].eligible
                for vehicle in candidate_vehicles
            )
            if not has_gis_vehicle:
                no_gis_vehicle += 1
        assignment_events = DispatchAssignmentEvent.objects.filter(
            assignment__in=assignments
        ).select_related(
            "assignment__transport_request", "new_driver", "new_vehicle", "performed_by",
            "previous_driver", "previous_vehicle",
        )
        audit_by_request = {str(item.pk): [] for item in board_context_requests}
        for event in assignment_events:
            audit_by_request[str(event.assignment.transport_request_id)].append(
                {
                    "kind": (
                        event.event_type
                        if event.event_type == DispatchAssignmentEvent.EventType.DRIVER_ACCEPTED
                        else (
                            "ASSIGNMENT_CHANGED"
                            if event.previous_driver_id or event.previous_vehicle_id
                            else "ASSIGNMENT_CONFIRMED"
                        )
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
            request__in=board_context_requests, event_type="PREPARED_FOR_DISPATCH"
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
        for item in awaiting:
            candidate_drivers, candidate_vehicles = candidates[item.pk]
            manual_candidates[str(item.pk)] = {
                "drivers": DispatchDriverSerializer(candidate_drivers, many=True).data,
                "vehicles": [
                    {
                        **AssignedVehicleSerializer(vehicle).data,
                        "current_location_available": (
                            vehicle.device_id in located_vehicle_ids
                        ),
                        "number_coding": coding[item.pk][vehicle.pk].as_dict(),
                    }
                    for vehicle in candidate_vehicles
                    if (
                        not is_supply_request(item)
                        or item.estimated_weight_kg is None
                        or (
                            vehicle.payload_capacity_kg is not None
                            and vehicle.payload_capacity_kg >= item.estimated_weight_kg
                        )
                    )
                ],
            }
        return {
                "summary": {
                    "approved_requests": approved_count,
                    "awaiting_assignment": len(awaiting),
                    "confirmed_assignments": confirmed_count,
                    "ready_for_dispatch": len(awaiting) + sum(
                        assignment.execution_status
                        != DispatchAssignment.ExecutionStatus.COMPLETED
                        for assignment in assignments
                    ),
                    "optimizer_eligible": optimizer_eligible,
                    "needs_attention": len(awaiting) - optimizer_eligible,
                    "no_eligible_driver": no_eligible_driver,
                    "no_gis_vehicle": no_gis_vehicle,
                    "schedule_conflict": schedule_conflict,
                    "number_coding_blocked": sum(
                        evaluation.status in {"RESTRICTED", "UNKNOWN"}
                        for evaluations in coding.values()
                        for evaluation in evaluations.values()
                    ),
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
                "recommendation_fingerprints": dispatch.planning_fingerprints(awaiting),
            }

    def get(self, request):
        return Response(self.payload(request))


def dispatch_board_summary(request):
    """Return dashboard-safe dispatch counts without invoking another view lifecycle."""
    return DispatchBoardView.payload(request)["summary"]


class DispatchRecommendationView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DISPATCH_BOARD"
    permission_action = "GENERATE_RECOMMENDATION"

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
                    "planning_fingerprint": item["planning_fingerprint"],
                    "fuel_estimate": item["fuel_estimate"],
                    "explanation": item["explanation"],
                    "schedule_context": item["schedule_context"],
                    "gis_preview": item["gis_preview"],
                    "airport_pickup_timing": item["airport_pickup_timing"],
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
                    "fuel_estimate": item["fuel_estimate"],
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


class DispatchRecommendationRouteInputSerializer(serializers.Serializer):
    transport_request_id = serializers.UUIDField()
    vehicle_id = serializers.IntegerField(min_value=1)
    driver_id = serializers.IntegerField(min_value=1)
    recommendation_token = serializers.CharField()


class DispatchRecommendationRouteView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DISPATCH_BOARD"
    permission_action = "GENERATE_RECOMMENDATION"

    def post(self, request):
        fields = DispatchRecommendationRouteInputSerializer(data=request.data)
        fields.is_valid(raise_exception=True)
        values = fields.validated_data
        dispatch.verify_token(
            values["recommendation_token"],
            values["transport_request_id"],
            values["vehicle_id"],
            values["driver_id"],
        )
        item = get_object_or_404(TransportRequest, pk=values["transport_request_id"])
        vehicle = get_object_or_404(Vehicle, pk=values["vehicle_id"])
        try:
            result = recommendation_route(item, vehicle)
        except routing.RouteCoordinateError:
            return Response(
                {"detail": "This recommendation has invalid route coordinates."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"route": DriverActiveRouteSerializer(result).data})


class DispatchConfirmationView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DISPATCH_BOARD"
    permission_action = "DISPATCH"

    def post(self, request):
        serializer = DispatchConfirmationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if (
            serializer.validated_data["selection_mode"]
            == DispatchAssignment.SelectionMode.MANUAL
            and not has_module_permission(request.user, "DISPATCH_BOARD", "OVERRIDE")
        ):
            self.permission_denied(request)
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
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DISPATCH_BOARD"
    permission_action = "GENERATE_RECOMMENDATION"

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
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DISPATCH_BOARD"
    permission_action = "DISPATCH"

    def post(self, request):
        token = serializers.CharField().run_validation(request.data.get("recommendation_token"))
        try:
            plan = consolidation.confirm(token, request.user)
        except PermissionError:
            self.permission_denied(request)
        return Response(DispatchPlanSerializer(plan).data, status=status.HTTP_201_CREATED)


class ConsolidationPrepareView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DISPATCH_BOARD"
    permission_action = "DISPATCH"

    def post(self, request, plan_id):
        try:
            plan = consolidation.prepare(plan_id, request.user)
        except PermissionError:
            self.permission_denied(request)
        return Response(DispatchPlanSerializer(plan).data)


class SummaryView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "TRANSPORT_REQUESTS"
    permission_action = "VIEW"

    def get(self, request):
        today = timezone.localdate()
        queryset = TransportRequest.objects.all()
        for_approval = queryset.filter(status=TransportRequest.Status.FOR_APPROVAL).count()
        needs_more_details = queryset.filter(
            status=TransportRequest.Status.NEEDS_MORE_DETAILS
        ).count()
        approved = queryset.filter(status=TransportRequest.Status.APPROVED)
        assignments = DispatchAssignment.objects.all()
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
                "active_trips": assignments.exclude(
                    execution_status=DispatchAssignment.ExecutionStatus.COMPLETED
                ).count(),
                "completed_trips": assignments.filter(
                    execution_status=DispatchAssignment.ExecutionStatus.COMPLETED
                ).count(),
            }
        )


class CalendarView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "TRANSPORT_REQUESTS"
    permission_action = "VIEW"
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
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "TRANSPORT_REQUESTS"
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
    permission_action = "APPROVE"
    action = staticmethod(services.approve)


class RejectView(ActionView):
    permission_action = "REJECT"
    action = staticmethod(services.reject)


class RequestMoreDetailsView(ActionView):
    permission_action = "REQUEST_MORE_DETAILS"
    action = staticmethod(services.request_more_details)


class ResubmitView(ActionView):
    permission_action = "EDIT"
    action = staticmethod(services.resubmit)


class CancelView(ActionView):
    permission_action = "CANCEL"
    action = staticmethod(services.cancel)


class PrepareDispatchView(ActionView):
    permission_action = "PREPARE_DISPATCH"
    action = staticmethod(services.prepare_dispatch)


class AssignVehicleView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DISPATCH_BOARD"
    permission_action = "ASSIGN"

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
