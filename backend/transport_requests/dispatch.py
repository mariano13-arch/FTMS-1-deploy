import hashlib
import json

from django.core import signing
from django.db import transaction
from django.utils import timezone
from ortools.sat.python import cp_model
from rest_framework import serializers

from accounts.models import StaffProfile, UserNotification
from accounts.notifications import notify_capability_users
from accounts.roles import resolve_role
from fleet.inspection_readiness import inspection_readiness, with_latest_inspection
from fleet.maintenance import maintenance_readiness, with_maintenance_readiness
from fleet.models import (
    Driver,
    NumberCodingRule,
    NumberCodingSuspension,
    Vehicle,
    VehicleCodingExemption,
    VehicleInspection,
    VehicleMaintenanceRecord,
)
from fleet.number_coding import evaluate_vehicle_number_coding
from fleet.schedules import compact_driver_name, evaluate_driver_schedule
from fleet.serializers import driver_eligibility
from telemetry.models import TelemetryEvent

from . import matrix
from .domain import is_supply_request
from .flight_tracking import airport_pickup_timing
from .fuel_cost_estimation import estimate_trip_fuel_cost
from .models import DispatchAssignment, DispatchAssignmentEvent, TransportRequest
from .services import allocation_conflicts, lock_relevant_vehicles, planning_end, validate_vehicle

OPERATORS = {
    StaffProfile.Role.FLEET_ADMIN,
    StaffProfile.Role.FLEET_MANAGER,
    StaffProfile.Role.DISPATCHER,
}
RECOMMENDATION_SALT = "dispatch-board-recommendation-v1"
RECOMMENDATION_MAX_AGE_SECONDS = 300
CANDIDATE_COMPARISON_LIMIT = 50


class DispatchConflict(Exception):
    pass


def _fuel_estimate_payload(estimate):
    decimal_fields = (
        "fuel_rate_lph",
        "travel_time_seconds",
        "estimated_fuel_liters",
        "price_per_liter",
        "estimated_fuel_cost_php",
    )
    payload = {
        "status": estimate.status,
        "reason": estimate.reason,
        "fuel_rate_basis": estimate.fuel_rate_basis,
        "fuel_rate_basis_label": {
            "CURRENT_AI": "Current AI",
            "HISTORICAL_AI_BASELINE": "Historical AI Baseline",
            "FLEET_REFERENCE_BASELINE": "Fleet Reference Baseline",
            "UNAVAILABLE": "Unavailable",
        }.get(estimate.fuel_rate_basis, estimate.fuel_rate_basis),
        "fuel_rate_provenance": getattr(estimate, "fuel_rate_provenance", None),
        "fuel_type": estimate.fuel_type,
        "fuel_grade": estimate.fuel_grade,
        "currency": estimate.currency,
        "price_provider": estimate.price_provider,
        "price_source_mode": estimate.price_source_mode,
        "price_effective_at": estimate.price_effective_at,
        "fuel_source_timestamp": estimate.fuel_source_timestamp,
        "history_sample_count": estimate.history_sample_count,
    }
    payload.update(
        {
            field: str(value) if value is not None else None
            for field in decimal_fields
            if (value := getattr(estimate, field, None)) is not None
        }
    )
    for field in decimal_fields:
        payload.setdefault(field, None)
    return payload


def require_operator(user):
    if resolve_role(user) not in OPERATORS:
        raise PermissionError


def driver_conflicts(request, driver, *, exclude_assignment_id=None):
    start, end = request.scheduled_pickup_at, planning_end(request)
    candidates = (
        DispatchAssignment.objects.filter(
            driver=driver,
            transport_request__status__in=(
                TransportRequest.Status.APPROVED,
                TransportRequest.Status.READY_FOR_DISPATCH,
            ),
            transport_request__scheduled_pickup_at__lt=end,
        )
        .exclude(execution_status=DispatchAssignment.ExecutionStatus.COMPLETED)
        .select_related("transport_request")
    )
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
    schedule = evaluate_driver_schedule(driver, request.scheduled_pickup_at)
    if schedule.status != "ON_SHIFT":
        raise serializers.ValidationError({"driver": f"{schedule.reason_code}: {schedule.reason}"})
    if driver_conflicts(request, driver, exclude_assignment_id=exclude_assignment_id):
        raise serializers.ValidationError({"driver": "Driver has an overlapping assignment."})


def planning_fingerprint(request_id):
    request = TransportRequest.objects.select_related("flight_context").get(pk=request_id)
    return planning_fingerprints([request])[str(request.pk)]


def planning_fingerprints(requests):
    """Build board fingerprints with one shared snapshot of fleet state."""
    requests = list(requests)
    request_fields = (
        "status",
        "scheduled_pickup_at",
        "pickup_latitude",
        "pickup_longitude",
        "destination_latitude",
        "destination_longitude",
        "passenger_count",
        "required_vehicle_type",
        "request_type",
        "request_category",
        "estimated_weight_kg",
        "estimated_duration_minutes",
        "updated_at",
    )
    common = {
        "vehicles": list(
            Vehicle.objects.order_by("pk").values_list(
                "pk",
                "is_active",
                "vehicle_type",
                "passenger_capacity",
                "payload_capacity_kg",
                "updated_at",
            )
        ),
        "drivers": list(
            Driver.objects.order_by("pk").values_list(
                "pk",
                "employment_status",
                "license_expiry_date",
                "medical_certificate_expiry_date",
                "work_shift",
                "weekly_rest_days",
                "updated_at",
            )
        ),
        "inspections": list(
            VehicleInspection.objects.order_by("vehicle_id", "pk").values_list(
                "pk", "vehicle_id", "inspection_date", "result", "updated_at"
            )
        ),
        "maintenance": list(
            VehicleMaintenanceRecord.objects.order_by("vehicle_id", "pk").values_list(
                "pk", "vehicle_id", "status", "updated_at"
            )
        ),
        "number_coding_rules": list(
            NumberCodingRule.objects.order_by("pk").values_list(
                "pk",
                "authority",
                "jurisdiction",
                "weekday",
                "restricted_last_digits",
                "start_time",
                "end_time",
                "effective_from",
                "effective_until",
                "is_active",
                "updated_at",
            )
        ),
        "number_coding_suspensions": list(
            NumberCodingSuspension.objects.order_by("pk").values_list(
                "pk",
                "authority",
                "jurisdiction",
                "starts_at",
                "ends_at",
                "is_active",
                "updated_at",
            )
        ),
        "number_coding_exemptions": list(
            VehicleCodingExemption.objects.order_by("pk").values_list(
                "pk",
                "vehicle_id",
                "authority",
                "jurisdiction",
                "starts_at",
                "ends_at",
                "is_active",
                "updated_at",
            )
        ),
        "telemetry": list(
            TelemetryEvent.objects.order_by("vehicle_id", "-recorded_at")
            .distinct("vehicle_id")
            .values_list("vehicle_id", "recorded_at", "location")
        ),
        "assignments": list(
            DispatchAssignment.objects.exclude(
                execution_status=DispatchAssignment.ExecutionStatus.COMPLETED
            )
            .order_by("pk")
            .values_list(
                "pk",
                "transport_request_id",
                "vehicle_id",
                "driver_id",
                "execution_status",
                "updated_at",
            )
        ),
    }
    fingerprints = {}
    for request in requests:
        material = {
            **common,
            "request": {field: str(getattr(request, field)) for field in request_fields},
            "flight": None,
        }
        flight = getattr(request, "flight_context", None)
        if flight:
            material["flight"] = [
                str(flight.estimated_arrival_at),
                str(flight.actual_arrival_at),
                str(flight.last_successful_refresh_at),
                flight.refresh_status,
            ]
        encoded = json.dumps(material, sort_keys=True, default=str, separators=(",", ":"))
        fingerprints[str(request.pk)] = hashlib.sha256(encoded.encode()).hexdigest()
    return fingerprints


def recommendation_token(request_id, vehicle_id, driver_id, fingerprint=None):
    return signing.dumps(
        {
            "request_id": str(request_id),
            "vehicle_id": vehicle_id,
            "driver_id": driver_id,
            "planning_fingerprint": fingerprint or planning_fingerprint(request_id),
        },
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
        "planning_fingerprint": planning_fingerprint(request_id),
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
    if request.status != TransportRequest.Status.READY_FOR_DISPATCH:
        raise serializers.ValidationError(
            {"status": "Only requests ready for dispatch can be assigned."}
        )
    existing = (
        DispatchAssignment.objects.select_for_update().filter(transport_request=request).first()
    )
    if existing and existing.execution_status != DispatchAssignment.ExecutionStatus.ASSIGNED:
        raise serializers.ValidationError(
            {"execution_status": "An assignment cannot be changed after execution starts."}
        )
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
        if previous_driver.pk != driver.pk or previous_vehicle.pk != vehicle.pk:
            existing.accepted_at = None
            existing.accepted_by = None
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
    event = DispatchAssignmentEvent.objects.create(
        assignment=assignment,
        event_type=(
            DispatchAssignmentEvent.EventType.ASSIGNMENT_CHANGED
            if existing
            else DispatchAssignmentEvent.EventType.ASSIGNMENT_CONFIRMED
        ),
        previous_driver=previous_driver,
        previous_vehicle=previous_vehicle,
        new_driver=driver,
        new_vehicle=vehicle,
        performed_by=user,
        selection_mode=selection_mode,
        reason=normalized_reason,
    )
    transaction.on_commit(
        lambda: notify_capability_users(
            module="DISPATCH_BOARD",
            action="VIEW",
            notification_type=UserNotification.Type.DISPATCH_CONFIRMED,
            title="Dispatch Confirmed",
            message=f"Dispatch was confirmed for {request.request_number}.",
            target_url=f"/transport-requests/{request.pk}",
            source_key=f"dispatch-assignment-event:{event.pk}:{event.event_type.lower()}",
            exclude_user_id=user.pk,
        ),
        robust=True,
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
        TransportRequest.objects.filter(status=TransportRequest.Status.READY_FOR_DISPATCH)
        .exclude(dispatch_assignment__isnull=False)
        .order_by("scheduled_pickup_at", "pk")
    )
    if request_ids is not None:
        requests = [item for item in requests if str(item.pk) in {str(pk) for pk in request_ids}]
    all_drivers = list(Driver.objects.order_by("pk"))
    drivers = [driver for driver in all_drivers if driver_eligibility(driver)[0] == "ELIGIBLE"]
    all_vehicles = list(
        with_maintenance_readiness(with_latest_inspection(Vehicle.objects.order_by("device_id")))
    )
    vehicles = [
        vehicle
        for vehicle in all_vehicles
        if vehicle.is_active
        and inspection_readiness(vehicle).eligible
        and maintenance_readiness(vehicle).eligible
    ]
    feasible = {}
    coding = {}
    fingerprints = {item.pk: planning_fingerprint(item.pk) for item in requests}
    for item in requests:
        coding[item.pk] = {
            vehicle.pk: evaluate_vehicle_number_coding(vehicle, item.scheduled_pickup_at)
            for vehicle in all_vehicles
        }
        feasible[item.pk] = {
            vehicle.pk
            for vehicle in vehicles
            if coding[item.pk][vehicle.pk].eligible
            and not allocation_conflicts(item, vehicle)
            and (
                vehicle.passenger_capacity is None
                or vehicle.passenger_capacity >= item.passenger_count
            )
            and (
                not item.required_vehicle_type or vehicle.vehicle_type == item.required_vehicle_type
            )
            and (
                not is_supply_request(item)
                or item.estimated_weight_kg is None
                or (
                    vehicle.payload_capacity_kg is not None
                    and vehicle.payload_capacity_kg >= item.estimated_weight_kg
                )
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
    matrix_vehicle_ids = {
        vehicle.device_id
        for vehicle in vehicles
        if any(vehicle.pk in feasible[item.pk] for item in requests)
    }
    located = matrix.eligible_vehicle_origins(sorted(matrix_vehicle_ids))
    origin_by_vehicle = {item["vehicle_id"]: item for item in located}
    matrix_results = {}
    for item in requests:
        request_vehicle_ids = [
            vehicle.device_id
            for vehicle in vehicles
            if vehicle.pk in feasible[item.pk] and vehicle.device_id in origin_by_vehicle
        ]
        if request_vehicle_ids:
            matrix_results[item.pk] = matrix.build_dispatch_matrix(
                request_vehicle_ids, [item.pk], include_assigned=True
            )
    vehicle_by_code = {vehicle.device_id: vehicle for vehicle in vehicles}
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
                        "name": compact_driver_name(driver),
                        "code": driver.driver_code,
                        "reason": eligibility,
                        "details": reasons,
                    }
                )
            elif evaluate_driver_schedule(driver, item.scheduled_pickup_at).status != "ON_SHIFT":
                schedule = evaluate_driver_schedule(driver, item.scheduled_pickup_at)
                exclusions[str(item.pk)].append(
                    {
                        "kind": "DRIVER",
                        "name": compact_driver_name(driver),
                        "code": driver.driver_code,
                        "reason": schedule.reason_code,
                        "details": [schedule.reason],
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
        matrix_result = matrix_results.get(item.pk)
        matrix_row = (
            {vehicle_code: row for row, vehicle_code in enumerate(matrix_result["vehicle_ids"])}
            if matrix_result
            else {}
        )
        request_column = 0
        for vehicle in all_vehicles:
            reason = ""
            details = []
            readiness = inspection_readiness(vehicle)
            maintenance = maintenance_readiness(vehicle)
            if not vehicle.is_active:
                reason, details = "INACTIVE", ["Vehicle is inactive."]
            elif not readiness.eligible:
                reason, details = readiness.result or "INSPECTION_REQUIRED", [readiness.reason]
            elif not maintenance.eligible:
                reason, details = "ACTIVE_MAINTENANCE", [maintenance.reason]
            elif not coding[item.pk][vehicle.pk].eligible:
                evaluation = coding[item.pk][vehicle.pk]
                reason, details = (
                    "NUMBER_CODING_RESTRICTION"
                    if evaluation.status == "RESTRICTED"
                    else "NUMBER_CODING_UNKNOWN",
                    [evaluation.reason],
                )
            elif (
                vehicle.passenger_capacity is not None
                and vehicle.passenger_capacity < item.passenger_count
            ):
                reason, details = (
                    "INSUFFICIENT_CAPACITY",
                    ["Passenger capacity is below the request requirement."],
                )
            elif (
                is_supply_request(item)
                and item.estimated_weight_kg is not None
                and vehicle.payload_capacity_kg is None
            ):
                reason, details = (
                    "PAYLOAD_CAPACITY_UNKNOWN",
                    [
                        "Vehicle payload capacity is not recorded, so compatibility "
                        "cannot be confirmed."
                    ],
                )
            elif (
                is_supply_request(item)
                and item.estimated_weight_kg is not None
                and vehicle.payload_capacity_kg < item.estimated_weight_kg
            ):
                reason, details = (
                    "INSUFFICIENT_PAYLOAD_CAPACITY",
                    ["Vehicle payload capacity is below the estimated load weight."],
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
    for item in requests:
        matrix_result = matrix_results.get(item.pk)
        if not matrix_result:
            continue
        for row, vehicle_code in enumerate(matrix_result["vehicle_ids"]):
            vehicle = vehicle_by_code[vehicle_code]
            column = 0
            if (
                vehicle.pk not in feasible[item.pk]
                or matrix_result["cell_statuses"][row][column] != "OK"
            ):
                continue
            for driver in drivers:
                if evaluate_driver_schedule(
                    driver, item.scheduled_pickup_at
                ).status == "ON_SHIFT" and not driver_conflicts(item, driver):
                    metrics = {
                        "travel_time_seconds": matrix_result["durations_seconds"][row][column],
                        "distance_meters": matrix_result["distances_meters"][row][column],
                        "traffic_delay_seconds": matrix_result["traffic_delays_seconds"][row][
                            column
                        ],
                    }
                    candidates.append((item, vehicle, driver, metrics))
                    if len(comparisons[str(item.pk)]) < CANDIDATE_COMPARISON_LIMIT:
                        comparisons[str(item.pk)].append(
                            {
                                "driver": driver,
                                "vehicle": vehicle,
                                **metrics,
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
        sum(metrics["travel_time_seconds"] or 0 for _, _, _, metrics in candidates)
        + len(candidates)
        + 1
    )
    model.maximize(
        sum(
            var * (max_duration - metrics["travel_time_seconds"] - index)
            for index, (var, (_, _, _, metrics)) in enumerate(
                zip(variables, candidates, strict=True)
            )
        )
    )
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.solve(model)
    selected = []
    selected_requests = set()
    fuel_estimates = {}

    def candidate_fuel_estimate(vehicle, travel_time_seconds):
        key = (vehicle.pk, travel_time_seconds)
        if key not in fuel_estimates:
            fuel_estimates[key] = _fuel_estimate_payload(
                estimate_trip_fuel_cost(vehicle, travel_time_seconds)
            )
        return fuel_estimates[key]

    for variable, (item, vehicle, driver, metrics) in zip(variables, candidates, strict=True):
        if solver.value(variable):
            selected_requests.add(item.pk)
            selected.append(
                {
                    "transport_request": item,
                    "vehicle": vehicle,
                    "driver": driver,
                    **metrics,
                    "recommendation_token": recommendation_token(
                        item.pk, vehicle.pk, driver.pk, fingerprints[item.pk]
                    ),
                    "planning_fingerprint": fingerprints[item.pk],
                    "fuel_estimate": candidate_fuel_estimate(
                        vehicle, metrics["travel_time_seconds"]
                    ),
                    "explanation": [
                        "Driver eligibility is ELIGIBLE",
                        "Vehicle is active",
                        (
                            "Payload capacity is satisfied"
                            if is_supply_request(item) and item.estimated_weight_kg is not None
                            else "Payload capacity not evaluated because load weight is unknown"
                            if is_supply_request(item)
                            else "Passenger capacity is satisfied"
                        ),
                        "Required vehicle type is matched"
                        if item.required_vehicle_type
                        else "No specific vehicle type is required",
                        "Driver schedule conflict: none",
                        "Vehicle schedule conflict: none",
                        {
                            "CLEAR": "Number coding: clear for scheduled pickup",
                            "EXEMPT": "Number coding: verified exemption",
                            "SUSPENDED": "Number coding: temporary suspension active",
                        }[coding[item.pk][vehicle.pk].status],
                        "Fresh eligible vehicle position is available",
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
                    "airport_pickup_timing": (
                        airport_pickup_timing(
                            item.flight_context,
                            metrics["travel_time_seconds"],
                        )
                        if item.request_type == TransportRequest.RequestType.AIRPORT_PICKUP
                        and hasattr(item, "flight_context")
                        else None
                    ),
                }
            )
            for comparison in comparisons[str(item.pk)]:
                if comparison["driver"].pk == driver.pk and comparison["vehicle"].pk == vehicle.pk:
                    comparison["result"] = "RECOMMENDED"
    for request_candidates in comparisons.values():
        for comparison in request_candidates:
            comparison["fuel_estimate"] = candidate_fuel_estimate(
                comparison["vehicle"], comparison["travel_time_seconds"]
            )
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
