from decimal import Decimal
from itertools import combinations

from django.core import signing
from django.db import transaction
from django.utils import timezone
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from rest_framework import serializers

from fleet.models import Driver, Vehicle
from fleet.serializers import driver_eligibility

from . import matrix
from .dispatch import driver_conflicts, require_operator
from .models import (
    DispatchAssignment,
    DispatchAssignmentEvent,
    DispatchPlan,
    DispatchPlanEvent,
    DispatchPlanStop,
    TransportRequest,
)
from .services import allocation_conflicts, apply_transition, lock_relevant_vehicles

CONSOLIDATION_SALT = "dispatch-consolidation-recommendation-v1"
MAX_AGE_SECONDS = 300
MAX_GROUP_REQUESTS = 4
SEARCH_SECONDS = 1
WEIGHT_SCALE = Decimal("100")


def _weight_units(value):
    return int(Decimal(value) * WEIGHT_SCALE)


def _eligible_request(item):
    if item.status != TransportRequest.Status.APPROVED:
        return "Only approved requests can be consolidated."
    if item.request_category != TransportRequest.RequestCategory.DELIVERY_LOGISTICS:
        return "Passenger transport is not eligible for consolidation."
    if item.estimated_weight_kg is None:
        return "Comparable load quantity unavailable."
    if hasattr(item, "dispatch_assignment"):
        return "Existing confirmed assignment prevents grouping."
    return ""


def _vehicle_supports(requests, vehicle):
    if not vehicle.is_active:
        return False
    if vehicle.payload_capacity_kg is None:
        return False
    if any(
        item.required_vehicle_type and item.required_vehicle_type != vehicle.vehicle_type
        for item in requests
    ):
        return False
    return all(not allocation_conflicts(item, vehicle) for item in requests)


def _driver_supports(requests, driver):
    return driver_eligibility(driver)[0] == "ELIGIBLE" and all(
        not driver_conflicts(item, driver) for item in requests
    )


def _points(origin, requests):
    values = [{"id": "origin", "latitude": origin["latitude"], "longitude": origin["longitude"]}]
    for item in requests:
        values.extend(
            [
                {
                    "id": f"pickup:{item.pk}",
                    "latitude": item.pickup_latitude,
                    "longitude": item.pickup_longitude,
                },
                {
                    "id": f"delivery:{item.pk}",
                    "latitude": item.destination_latitude,
                    "longitude": item.destination_longitude,
                },
            ]
        )
    values.append({"id": "end", "latitude": origin["latitude"], "longitude": origin["longitude"]})
    return values


def solve_route(requests, origin, payload_capacity_kg, matrix_result):
    node_count = 2 + 2 * len(requests)
    end_node = node_count - 1
    manager = pywrapcp.RoutingIndexManager(node_count, 1, [0], [end_node])
    routing = pywrapcp.RoutingModel(manager)
    durations = matrix_result["durations_seconds"]
    distances = matrix_result["distances_meters"]
    statuses = matrix_result["cell_statuses"]
    if any(
        statuses[row][column] != "OK" for row in range(node_count) for column in range(node_count)
    ):
        return None

    def duration_callback(from_index, to_index):
        start, end = manager.IndexToNode(from_index), manager.IndexToNode(to_index)
        return 0 if end == end_node else durations[start][end]

    transit = routing.RegisterTransitCallback(duration_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit)
    routing.AddDimension(transit, 0, 24 * 60 * 60, True, "TravelTime")
    travel_time_dimension = routing.GetDimensionOrDie("TravelTime")
    demands = [0]
    for item in requests:
        units = _weight_units(item.estimated_weight_kg)
        demands.extend([units, -units])
    demands.append(0)
    demand = routing.RegisterUnaryTransitCallback(lambda index: demands[manager.IndexToNode(index)])
    capacity = _weight_units(payload_capacity_kg)
    routing.AddDimensionWithVehicleCapacity(demand, 0, [capacity], True, "Capacity")
    for offset in range(len(requests)):
        pickup_node, delivery_node = 1 + offset * 2, 2 + offset * 2
        pickup, delivery = manager.NodeToIndex(pickup_node), manager.NodeToIndex(delivery_node)
        routing.AddPickupAndDelivery(pickup, delivery)
        routing.solver().Add(routing.VehicleVar(pickup) == routing.VehicleVar(delivery))
        routing.solver().Add(
            travel_time_dimension.CumulVar(pickup) <= travel_time_dimension.CumulVar(delivery)
        )
    parameters = pywrapcp.DefaultRoutingSearchParameters()
    parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    )
    parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    parameters.time_limit.seconds = SEARCH_SECONDS
    parameters.log_search = False
    solution = routing.SolveWithParameters(parameters)
    if not solution:
        return None
    index = routing.Start(0)
    ordered_nodes = []
    total_time = total_distance = peak = load = 0
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        next_index = solution.Value(routing.NextVar(index))
        next_node = manager.IndexToNode(next_index)
        if node not in (0, end_node):
            load += demands[node]
            peak = max(peak, load)
            ordered_nodes.append(node)
        if next_node != end_node:
            total_time += durations[node][next_node]
            total_distance += distances[node][next_node]
        index = next_index
    stops = []
    for sequence, node in enumerate(ordered_nodes, 1):
        request_index, is_delivery = divmod(node - 1, 2)
        item = requests[request_index]
        stops.append(
            {
                "sequence": sequence,
                "request_id": str(item.pk),
                "request_number": item.request_number,
                "stop_type": "DELIVERY" if is_delivery else "PICKUP",
                "label": item.destination_name if is_delivery else item.pickup_name,
                "latitude": item.destination_latitude if is_delivery else item.pickup_latitude,
                "longitude": item.destination_longitude if is_delivery else item.pickup_longitude,
                "load_change_kg": str(
                    -item.estimated_weight_kg if is_delivery else item.estimated_weight_kg
                ),
            }
        )
    baseline_time = baseline_distance = 0
    for offset in range(len(requests)):
        pickup, delivery = 1 + offset * 2, 2 + offset * 2
        baseline_time += durations[0][pickup] + durations[pickup][delivery]
        baseline_distance += distances[0][pickup] + distances[pickup][delivery]
    return {
        "stops": stops,
        "peak_load_kg": str(Decimal(peak) / WEIGHT_SCALE),
        "capacity_kg": str(payload_capacity_kg),
        "capacity_utilization_percent": round(peak * 100 / capacity, 1),
        "separate": {
            "vehicles": len(requests),
            "travel_time_seconds": baseline_time,
            "distance_meters": baseline_distance,
        },
        "consolidated": {
            "vehicles": 1,
            "travel_time_seconds": total_time,
            "distance_meters": total_distance,
        },
        "difference": {
            "vehicles": len(requests) - 1,
            "travel_time_seconds": baseline_time - total_time,
            "distance_meters": baseline_distance - total_distance,
        },
    }


def _token(result):
    return signing.dumps(
        {
            "request_ids": result["request_ids"],
            "driver_id": result["driver"].pk,
            "vehicle_id": result["vehicle"].pk,
            "stops": [
                (item["request_id"], item["stop_type"], item["sequence"])
                for item in result["route"]["stops"]
            ],
        },
        salt=CONSOLIDATION_SALT,
        compress=True,
    )


def recommendations(selected_request_id):
    selected = TransportRequest.objects.get(pk=selected_request_id)
    selected_reason = _eligible_request(selected)
    if selected_reason:
        return {
            "generated_at": timezone.now(),
            "recommendation": None,
            "exclusions": [selected_reason],
            "limit": MAX_GROUP_REQUESTS,
        }
    candidates = list(
        TransportRequest.objects.filter(
            status=TransportRequest.Status.APPROVED,
            request_category=TransportRequest.RequestCategory.DELIVERY_LOGISTICS,
            estimated_weight_kg__isnull=False,
            dispatch_assignment__isnull=True,
        )
        .exclude(pk=selected.pk)
        .order_by("scheduled_pickup_at", "pk")[: MAX_GROUP_REQUESTS - 1]
    )
    if not candidates:
        return {
            "generated_at": timezone.now(),
            "recommendation": None,
            "exclusions": ["No other eligible delivery request is available."],
            "limit": MAX_GROUP_REQUESTS,
        }
    vehicles = list(Vehicle.objects.filter(is_active=True).order_by("device_id"))
    origins = {item["vehicle_id"]: item for item in matrix.eligible_vehicle_origins()}
    drivers = [
        item
        for item in Driver.objects.all().order_by("driver_code")
        if driver_eligibility(item)[0] == "ELIGIBLE"
    ]
    exclusions = []
    best = None
    groups = (
        [selected, *extra]
        for size in range(1, len(candidates) + 1)
        for extra in combinations(candidates, size)
    )
    for group in groups:
        group_label = " + ".join(item.request_number for item in group[1:])
        compatible_vehicles = [
            item
            for item in vehicles
            if item.device_id in origins and _vehicle_supports(group, item)
        ]
        compatible_drivers = [item for item in drivers if _driver_supports(group, item)]
        if not compatible_drivers:
            exclusions.append(f"{group_label}: No common eligible Driver.")
            continue
        if not compatible_vehicles:
            exclusions.append(
                f"{group_label}: No common payload-compatible GIS Vehicle."
            )
            continue
        for vehicle in compatible_vehicles:
            if sum(item.estimated_weight_kg for item in group) > vehicle.payload_capacity_kg:
                exclusions.append(
                    f"{group_label}: Combined load exceeds vehicle payload."
                )
                continue
            matrix_result = matrix.build_point_matrix(_points(origins[vehicle.device_id], group))
            route = solve_route(
                group, origins[vehicle.device_id], vehicle.payload_capacity_kg, matrix_result
            )
            if not route:
                exclusions.append(f"{group_label}: TomTom road route unavailable.")
                continue
            if route["difference"]["travel_time_seconds"] <= 0:
                exclusions.append(
                    f"{group_label}: Consolidation does not reduce "
                    "planned travel time."
                )
                continue
            result = {
                "request_ids": [str(item.pk) for item in group],
                "requests": group,
                "driver": compatible_drivers[0],
                "vehicle": vehicle,
                "route": route,
            }
            if (
                best is None
                or len(group) > len(best["requests"])
                or (
                    len(group) == len(best["requests"])
                    and route["consolidated"]["travel_time_seconds"]
                    < best["route"]["consolidated"]["travel_time_seconds"]
                )
            ):
                best = result
    if best:
        best["recommendation_token"] = _token(best)
        best["explanation"] = [
            "Requests are approved delivery/logistics work with comparable kilogram loads.",
            "One eligible Driver and one active Vehicle satisfy the validated constraints.",
            "Peak load remains within the stored vehicle payload capacity.",
            "All required travel costs come from the TomTom road matrix.",
            "The consolidated route reduces planned travel versus separate service.",
        ]
    return {
        "generated_at": timezone.now(),
        "recommendation": best,
        "exclusions": list(dict.fromkeys(exclusions)),
        "limit": MAX_GROUP_REQUESTS,
    }


def _load_token(token):
    try:
        return signing.loads(token, salt=CONSOLIDATION_SALT, max_age=MAX_AGE_SECONDS)
    except signing.BadSignature as error:
        raise serializers.ValidationError(
            {"recommendation_token": "Consolidation recommendation is invalid or expired."}
        ) from error


@transaction.atomic
def confirm(token, user):
    require_operator(user)
    payload = _load_token(token)
    requests = list(
        TransportRequest.objects.select_for_update()
        .filter(pk__in=payload["request_ids"])
        .order_by("pk")
    )
    if len(requests) != len(payload["request_ids"]) or any(
        _eligible_request(item) for item in requests
    ):
        raise serializers.ValidationError(
            {"requests": "One or more requests are no longer eligible."}
        )
    vehicle = lock_relevant_vehicles(payload["vehicle_id"]).get(payload["vehicle_id"])
    driver = Driver.objects.select_for_update().filter(pk=payload["driver_id"]).first()
    if (
        not vehicle
        or not driver
        or not _vehicle_supports(requests, vehicle)
        or not _driver_supports(requests, driver)
    ):
        raise serializers.ValidationError({"resources": "Driver or Vehicle is no longer eligible."})
    if sum(item.estimated_weight_kg for item in requests) > vehicle.payload_capacity_kg:
        raise serializers.ValidationError({"vehicle": "Combined load exceeds vehicle payload."})
    expected = {str(item.pk) for item in requests}
    stop_pairs = [(item[0], item[1]) for item in payload["stops"]]
    expected_pairs = [
        (request_id, stop_type) for request_id in expected for stop_type in ("PICKUP", "DELIVERY")
    ]
    if sorted(stop_pairs) != sorted(expected_pairs):
        raise serializers.ValidationError(
            {"recommendation_token": "Consolidation stop context is invalid."}
        )
    plan = DispatchPlan.objects.create(vehicle=vehicle, driver=driver, confirmed_by=user)
    request_by_id = {str(item.pk): item for item in requests}
    for request_id, stop_type, sequence in payload["stops"]:
        DispatchPlanStop.objects.create(
            plan=plan,
            transport_request=request_by_id[request_id],
            stop_type=stop_type,
            sequence=sequence,
        )
    for item in requests:
        assignment = DispatchAssignment.objects.create(
            plan=plan,
            transport_request=item,
            vehicle=vehicle,
            driver=driver,
            selection_mode=DispatchAssignment.SelectionMode.OPTIMIZED,
            confirmed_by=user,
        )
        item.assigned_vehicle = vehicle
        item.save(update_fields=["assigned_vehicle", "updated_at"])
        DispatchAssignmentEvent.objects.create(
            assignment=assignment,
            new_driver=driver,
            new_vehicle=vehicle,
            performed_by=user,
            selection_mode=DispatchAssignment.SelectionMode.OPTIMIZED,
            reason="Confirmed consolidated dispatch plan.",
        )
    DispatchPlanEvent.objects.create(
        plan=plan,
        event_type="CONSOLIDATION_CONFIRMED",
        performed_by=user,
        details={"request_ids": payload["request_ids"], "stops": payload["stops"]},
    )
    return plan


@transaction.atomic
def prepare(plan_id, user):
    require_operator(user)
    plan = (
        DispatchPlan.objects.select_for_update().select_related("driver", "vehicle").get(pk=plan_id)
    )
    assignments = list(plan.assignments.select_for_update().select_related("transport_request"))
    requests = [item.transport_request for item in assignments]
    if not assignments or any(item.status != TransportRequest.Status.APPROVED for item in requests):
        raise serializers.ValidationError(
            {"requests": "Every plan request must still be approved."}
        )
    if not plan.vehicle.is_active or driver_eligibility(plan.driver)[0] != "ELIGIBLE":
        raise serializers.ValidationError({"resources": "Plan resources are no longer eligible."})
    for item in requests:
        if item.assigned_vehicle_id != plan.vehicle_id:
            raise serializers.ValidationError(
                {"vehicle": "Plan assignments are no longer synchronized."}
            )
        if driver_conflicts(item, plan.driver) or allocation_conflicts(item, plan.vehicle):
            raise serializers.ValidationError(
                {"schedule": "The consolidated plan now conflicts with an external assignment."}
            )
    for item in requests:
        apply_transition(
            item,
            TransportRequest.Status.READY_FOR_DISPATCH,
            user,
            "PREPARED_FOR_DISPATCH",
            "Prepared as a consolidated dispatch plan.",
        )
    DispatchPlanEvent.objects.create(
        plan=plan,
        event_type="CONSOLIDATION_PREPARED",
        performed_by=user,
        details={"request_ids": [str(item.pk) for item in requests]},
    )
    return plan
