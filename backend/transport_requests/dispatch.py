from django.core import signing
from django.db import transaction
from django.utils import timezone
from ortools.sat.python import cp_model
from rest_framework import serializers

from accounts.models import StaffProfile
from accounts.roles import SUPER_ADMIN, resolve_role
from fleet.models import Driver, Vehicle
from fleet.serializers import driver_eligibility

from . import matrix
from .models import DispatchAssignment, DispatchAssignmentEvent, TransportRequest
from .services import allocation_conflicts, lock_relevant_vehicles, planning_end, validate_vehicle

OPERATORS = {SUPER_ADMIN, StaffProfile.Role.FLEET_MANAGER, StaffProfile.Role.DISPATCHER}
RECOMMENDATION_SALT = "dispatch-board-recommendation-v1"
RECOMMENDATION_MAX_AGE_SECONDS = 300
CANDIDATE_COMPARISON_LIMIT = 50


class DispatchConflict(Exception):
    pass


def require_operator(user):
    if resolve_role(user) not in OPERATORS:
        raise PermissionError


def driver_conflicts(request, driver, *, exclude_assignment_id=None):
    start, end = request.scheduled_pickup_at, planning_end(request)
    candidates = DispatchAssignment.objects.filter(
        driver=driver,
        transport_request__status__in=(
            TransportRequest.Status.APPROVED,
            TransportRequest.Status.READY_FOR_DISPATCH,
        ),
        transport_request__scheduled_pickup_at__lt=end,
    ).select_related("transport_request")
    if exclude_assignment_id:
        candidates = candidates.exclude(pk=exclude_assignment_id)
    plan_id = getattr(getattr(request, "dispatch_assignment", None), "plan_id", None)
    if plan_id:
        candidates = candidates.exclude(plan_id=plan_id)
    return [item for item in candidates if planning_end(item.transport_request) > start]


def validate_driver(request, driver, *, exclude_assignment_id=None):
    eligibility, reasons = driver_eligibility(driver)
    if eligibility != "ELIGIBLE":
        raise serializers.ValidationError(
            {"driver": f"Driver is {eligibility.lower().replace('_', ' ')}: " + "; ".join(reasons)}
        )
    if driver_conflicts(request, driver, exclude_assignment_id=exclude_assignment_id):
        raise serializers.ValidationError({"driver": "Driver has an overlapping assignment."})


def recommendation_token(request_id, vehicle_id, driver_id):
    return signing.dumps(
        {"request_id": str(request_id), "vehicle_id": vehicle_id, "driver_id": driver_id},
        salt=RECOMMENDATION_SALT,
        compress=True,
    )


def verify_token(token, request_id, vehicle_id, driver_id):
    try:
        payload = signing.loads(
            token, salt=RECOMMENDATION_SALT, max_age=RECOMMENDATION_MAX_AGE_SECONDS
        )
    except signing.BadSignature as error:
        raise serializers.ValidationError(
            {"recommendation_token": "Recommendation is invalid or expired."}
        ) from error
    expected = {
        "request_id": str(request_id),
        "vehicle_id": vehicle_id,
        "driver_id": driver_id,
    }
    if payload != expected:
        raise serializers.ValidationError(
            {"recommendation_token": "Recommendation does not match the selected pair."}
        )


@transaction.atomic
def confirm_assignment(
    *,
    transport_request_id,
    vehicle_id,
    driver_id,
    selection_mode,
    user,
    override_reason="",
    recommendation_token="",
):
    require_operator(user)
    request = TransportRequest.objects.select_for_update().get(pk=transport_request_id)
    if request.status != TransportRequest.Status.APPROVED:
        raise serializers.ValidationError({"status": "Only approved requests can be assigned."})
    existing = (
        DispatchAssignment.objects.select_for_update().filter(transport_request=request).first()
    )
    if existing and request.status == TransportRequest.Status.READY_FOR_DISPATCH:
        raise serializers.ValidationError({"status": "Ready assignments cannot be modified."})
    normalized_reason = override_reason.strip()
    if existing and not normalized_reason:
        raise serializers.ValidationError({"override_reason": "A change reason is required."})
    if selection_mode == DispatchAssignment.SelectionMode.MANUAL and not normalized_reason:
        raise serializers.ValidationError({"override_reason": "An override reason is required."})
    if selection_mode == DispatchAssignment.SelectionMode.OPTIMIZED:
        verify_token(recommendation_token, request.pk, vehicle_id, driver_id)
    vehicle = lock_relevant_vehicles(vehicle_id).get(vehicle_id)
    if not vehicle:
        raise serializers.ValidationError({"vehicle": "Vehicle was not found."})
    driver = Driver.objects.select_for_update().filter(pk=driver_id).first()
    if not driver:
        raise serializers.ValidationError({"driver": "Driver was not found."})
    validate_vehicle(request, vehicle)
    validate_driver(request, driver, exclude_assignment_id=existing.pk if existing else None)
    previous_driver = existing.driver if existing else None
    previous_vehicle = existing.vehicle if existing else None
    if existing:
        existing.vehicle = vehicle
        existing.driver = driver
        existing.selection_mode = selection_mode
        existing.override_reason = normalized_reason
        existing.updated_by = user
        existing.confirmed_at = timezone.now()
        existing.save()
        assignment = existing
    else:
        assignment = DispatchAssignment.objects.create(
            transport_request=request,
            vehicle=vehicle,
            driver=driver,
            selection_mode=selection_mode,
            override_reason=normalized_reason,
            confirmed_by=user,
        )
    request.assigned_vehicle = vehicle
    request.save(update_fields=["assigned_vehicle", "updated_at"])
    DispatchAssignmentEvent.objects.create(
        assignment=assignment,
        previous_driver=previous_driver,
        previous_vehicle=previous_vehicle,
        new_driver=driver,
        new_vehicle=vehicle,
        performed_by=user,
        selection_mode=selection_mode,
        reason=normalized_reason,
    )
    return assignment


def _request_reason(request, active_vehicles, eligible_drivers):
    if not eligible_drivers:
        return "No eligible driver"
    if not active_vehicles:
        return "No active vehicle satisfying request constraints"
    if request.pickup_latitude is None or request.pickup_longitude is None:
        return "Pickup coordinates unavailable"
    return "No feasible TomTom route and Driver/Vehicle pair"


def _window(item):
    return {
        "request_number": item.transport_request.request_number,
        "start": item.transport_request.scheduled_pickup_at,
        "end": planning_end(item.transport_request),
    }


def schedule_context(request, driver, vehicle):
    driver_windows = driver_conflicts(request, driver)
    vehicle_windows = allocation_conflicts(request, vehicle)
    return {
        "selected": {
            "start": request.scheduled_pickup_at,
            "end": planning_end(request),
        },
        "driver": {
            "status": "CONFLICT" if driver_windows else "AVAILABLE",
            "windows": [_window(item) for item in driver_windows],
        },
        "vehicle": {
            "status": "CONFLICT" if vehicle_windows else "AVAILABLE",
            "windows": [
                {
                    "request_number": item.request_number,
                    "start": item.scheduled_pickup_at,
                    "end": planning_end(item),
                }
                for item in vehicle_windows
            ],
        },
    }


def recommendations(request_ids=None):
    requests = list(
        TransportRequest.objects.filter(status=TransportRequest.Status.APPROVED)
        .exclude(dispatch_assignment__isnull=False)
        .order_by("scheduled_pickup_at", "pk")
    )
    if request_ids is not None:
        requests = [item for item in requests if str(item.pk) in {str(pk) for pk in request_ids}]
    all_drivers = list(Driver.objects.order_by("pk"))
    drivers = [driver for driver in all_drivers if driver_eligibility(driver)[0] == "ELIGIBLE"]
    all_vehicles = list(Vehicle.objects.order_by("device_id"))
    vehicles = [vehicle for vehicle in all_vehicles if vehicle.is_active]
    feasible = {}
    for item in requests:
        feasible[item.pk] = {
            vehicle.pk
            for vehicle in vehicles
            if not allocation_conflicts(item, vehicle)
            and (
                vehicle.passenger_capacity is None
                or vehicle.passenger_capacity >= item.passenger_count
            )
            and (
                not item.required_vehicle_type or vehicle.vehicle_type == item.required_vehicle_type
            )
        }
    if not requests:
        return {
            "generated_at": timezone.now(),
            "considered": 0,
            "recommendations": [],
            "unassigned": [],
        }
    if not drivers:
        return {
            "generated_at": timezone.now(),
            "considered": len(requests),
            "recommendations": [],
            "unassigned": [
                {"transport_request": item, "reason": "No eligible driver"} for item in requests
            ],
        }
    located = matrix.eligible_vehicle_origins([vehicle.device_id for vehicle in vehicles])
    origin_by_vehicle = {item["vehicle_id"]: item for item in located}
    if not located:
        return {
            "generated_at": timezone.now(),
            "considered": len(requests),
            "recommendations": [],
            "unassigned": [
                {"transport_request": item, "reason": "No fresh vehicle telemetry"}
                for item in requests
            ],
        }
    matrix_result = matrix.build_dispatch_matrix(
        [vehicle.device_id for vehicle in vehicles],
        [item.pk for item in requests],
        include_assigned=True,
    )
    vehicle_by_code = {vehicle.device_id: vehicle for vehicle in vehicles}
    request_by_id = {str(item.pk): item for item in requests}
    candidates = []
    comparisons = {str(item.pk): [] for item in requests}
    exclusions = {str(item.pk): [] for item in requests}
    for item in requests:
        for driver in all_drivers:
            eligibility, reasons = driver_eligibility(driver)
            if eligibility != "ELIGIBLE":
                exclusions[str(item.pk)].append(
                    {
                        "kind": "DRIVER",
                        "name": " ".join(
                            filter(None, [driver.first_name, driver.middle_name, driver.last_name])
                        ),
                        "code": driver.driver_code,
                        "reason": eligibility,
                        "details": reasons,
                    }
                )
            elif driver_conflicts(item, driver):
                exclusions[str(item.pk)].append(
                    {
                        "kind": "DRIVER",
                        "name": str(driver),
                        "code": driver.driver_code,
                        "reason": "SCHEDULE_CONFLICT",
                        "details": ["Driver has an overlapping confirmed assignment."],
                    }
                )
        matrix_row = {
            vehicle_code: row for row, vehicle_code in enumerate(matrix_result["vehicle_ids"])
        }
        request_column = matrix_result["request_ids"].index(str(item.pk))
        for vehicle in all_vehicles:
            reason = ""
            details = []
            if not vehicle.is_active:
                reason, details = "INACTIVE", ["Vehicle is inactive."]
            elif (
                vehicle.passenger_capacity is not None
                and vehicle.passenger_capacity < item.passenger_count
            ):
                reason, details = (
                    "INSUFFICIENT_CAPACITY",
                    ["Passenger capacity is below the request requirement."],
                )
            elif item.required_vehicle_type and vehicle.vehicle_type != item.required_vehicle_type:
                reason, details = (
                    "VEHICLE_TYPE_MISMATCH",
                    ["Vehicle type does not match the request requirement."],
                )
            elif allocation_conflicts(item, vehicle):
                reason, details = "SCHEDULE_CONFLICT", ["Vehicle has an overlapping allocation."]
            elif vehicle.device_id not in matrix_row:
                reason, details = (
                    "NO_FRESH_TELEMETRY",
                    ["Optimized GIS metrics are unavailable; manual assignment remains possible."],
                )
                if drivers and len(comparisons[str(item.pk)]) < CANDIDATE_COMPARISON_LIMIT:
                    comparisons[str(item.pk)].append(
                        {
                            "driver": drivers[0],
                            "vehicle": vehicle,
                            "travel_time_seconds": None,
                            "distance_meters": None,
                            "traffic_delay_seconds": None,
                            "result": "MANUAL_ONLY",
                        }
                    )
            elif (
                matrix_result["cell_statuses"][matrix_row[vehicle.device_id]][request_column]
                != "OK"
            ):
                reason, details = (
                    "TOMTOM_ROUTE_UNAVAILABLE",
                    ["TomTom matrix route is unavailable."],
                )
            if reason:
                exclusions[str(item.pk)].append(
                    {
                        "kind": "VEHICLE",
                        "name": vehicle.display_name,
                        "code": vehicle.device_id,
                        "reason": reason,
                        "details": details,
                    }
                )
    for row, vehicle_code in enumerate(matrix_result["vehicle_ids"]):
        vehicle = vehicle_by_code[vehicle_code]
        for column, request_id in enumerate(matrix_result["request_ids"]):
            item = request_by_id[request_id]
            if (
                vehicle.pk not in feasible[item.pk]
                or matrix_result["cell_statuses"][row][column] != "OK"
            ):
                continue
            for driver in drivers:
                if not driver_conflicts(item, driver):
                    candidates.append((item, vehicle, driver, row, column))
                    if len(comparisons[str(item.pk)]) < CANDIDATE_COMPARISON_LIMIT:
                        comparisons[str(item.pk)].append(
                            {
                                "driver": driver,
                                "vehicle": vehicle,
                                "travel_time_seconds": matrix_result["durations_seconds"][row][
                                    column
                                ],
                                "distance_meters": matrix_result["distances_meters"][row][column],
                                "traffic_delay_seconds": matrix_result["traffic_delays_seconds"][
                                    row
                                ][column],
                                "result": "FEASIBLE",
                            }
                        )
    model = cp_model.CpModel()
    variables = [model.new_bool_var(f"pair_{i}") for i in range(len(candidates))]
    for item in requests:
        selected = (
            var
            for var, candidate in zip(variables, candidates, strict=True)
            if candidate[0] == item
        )
        model.add(sum(selected) <= 1)
    for vehicle in vehicles:
        selected = (
            var
            for var, candidate in zip(variables, candidates, strict=True)
            if candidate[1] == vehicle
        )
        model.add(sum(selected) <= 1)
    for driver in drivers:
        selected = (
            var
            for var, candidate in zip(variables, candidates, strict=True)
            if candidate[2] == driver
        )
        model.add(sum(selected) <= 1)
    max_duration = (
        sum(
            matrix_result["durations_seconds"][row][column] or 0
            for _, _, _, row, column in candidates
        )
        + len(candidates)
        + 1
    )
    model.maximize(
        sum(
            var * (max_duration - matrix_result["durations_seconds"][row][column] - index)
            for index, (var, (_, _, _, row, column)) in enumerate(
                zip(variables, candidates, strict=True)
            )
        )
    )
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.solve(model)
    selected = []
    selected_requests = set()
    for variable, (item, vehicle, driver, row, column) in zip(variables, candidates, strict=True):
        if solver.value(variable):
            selected_requests.add(item.pk)
            selected.append(
                {
                    "transport_request": item,
                    "vehicle": vehicle,
                    "driver": driver,
                    "travel_time_seconds": matrix_result["durations_seconds"][row][column],
                    "distance_meters": matrix_result["distances_meters"][row][column],
                    "traffic_delay_seconds": matrix_result["traffic_delays_seconds"][row][column],
                    "recommendation_token": recommendation_token(item.pk, vehicle.pk, driver.pk),
                    "explanation": [
                        "Driver eligibility is ELIGIBLE",
                        "Vehicle is active",
                        "Passenger capacity is satisfied",
                        "Required vehicle type is matched"
                        if item.required_vehicle_type
                        else "No specific vehicle type is required",
                        "Driver schedule conflict: none",
                        "Vehicle schedule conflict: none",
                        "Fresh real vehicle telemetry is available",
                        "TomTom route/matrix cell is valid",
                    ],
                    "schedule_context": schedule_context(item, driver, vehicle),
                    "gis_preview": {
                        "status": "METRICS_AVAILABLE",
                        "vehicle_location": origin_by_vehicle.get(vehicle.device_id),
                        "pickup": {
                            "latitude": item.pickup_latitude,
                            "longitude": item.pickup_longitude,
                            "label": item.pickup_name,
                        },
                        "destination": {
                            "latitude": item.destination_latitude,
                            "longitude": item.destination_longitude,
                            "label": item.destination_name,
                        },
                        "geometry": None,
                    },
                }
            )
            for comparison in comparisons[str(item.pk)]:
                if comparison["driver"].pk == driver.pk and comparison["vehicle"].pk == vehicle.pk:
                    comparison["result"] = "RECOMMENDED"
    return {
        "generated_at": timezone.now(),
        "considered": len(requests),
        "recommendations": selected,
        "candidate_comparison": comparisons,
        "excluded_candidates": exclusions,
        "comparison_limit": CANDIDATE_COMPARISON_LIMIT,
        "unassigned": [
            {"transport_request": item, "reason": _request_reason(item, vehicles, drivers)}
            for item in requests
            if item.pk not in selected_requests
        ],
    }
