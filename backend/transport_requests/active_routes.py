from django.utils import timezone

from telemetry.models import TelemetryEvent
from telemetry.presentation import current_event_for_vehicle, valid_position

from . import matrix, routing
from .models import DispatchAssignment


def _request_places(item):
    pickup = {
        "name": item.pickup_name,
        "latitude": float(item.pickup_latitude),
        "longitude": float(item.pickup_longitude),
    }
    destination = {
        "name": item.destination_name,
        "latitude": float(item.destination_latitude),
        "longitude": float(item.destination_longitude),
    }
    return pickup, destination


def _vehicle_position(vehicle):
    event = current_event_for_vehicle(vehicle)
    coordinates = valid_position(event)
    authoritative_position = coordinates is not None and (
        event.position_source != TelemetryEvent.PositionSource.SIMULATED_TEST
        or matrix.simulated_position_is_allowed(vehicle, event)
    )
    position_current = authoritative_position and matrix.dispatch_position_is_eligible(
        vehicle, event
    )
    position_state = (
        "CURRENT" if position_current else "STALE" if authoritative_position else "UNAVAILABLE"
    )
    vehicle_position = None
    position_age_seconds = None
    position_recorded_at = None
    if authoritative_position:
        position_recorded_at = event.recorded_at
        position_age_seconds = max(0, int((timezone.now() - event.recorded_at).total_seconds()))
        vehicle_position = {
            **coordinates,
            "recorded_at": event.recorded_at,
            "is_stale": position_state == "STALE",
            "source": event.position_source,
        }
    return event, position_state, position_recorded_at, position_age_seconds, vehicle_position


def active_assignment_route(assignment):
    item = assignment.transport_request
    pickup, destination = _request_places(item)
    event, position_state, position_recorded_at, position_age_seconds, vehicle_position = (
        _vehicle_position(assignment.vehicle)
    )

    execution_status = assignment.execution_status
    planned_route = None
    planned_route_status = "NOT_APPLICABLE"
    if execution_status in {
        DispatchAssignment.ExecutionStatus.ASSIGNED,
        DispatchAssignment.ExecutionStatus.EN_ROUTE_TO_PICKUP,
    }:
        try:
            # Use the canonical request-route identity so an already cached
            # pickup-to-destination TomTom route is reused.
            planned_route = routing.get_route(item)
        except (routing.RouteConfigurationError, routing.RouteServiceError):
            planned_route = None
        planned_route_status = "AVAILABLE" if planned_route else "TEMPORARILY_UNAVAILABLE"

    if execution_status in {
        DispatchAssignment.ExecutionStatus.AT_DESTINATION,
        DispatchAssignment.ExecutionStatus.COMPLETED,
    }:
        return {
            "phase": (
                "COMPLETED"
                if execution_status == DispatchAssignment.ExecutionStatus.COMPLETED
                else "ARRIVED"
            ),
            "execution_status": execution_status,
            "route_status": "NOT_ACTIVE",
            "position_state": position_state,
            "position_recorded_at": position_recorded_at,
            "position_age_seconds": position_age_seconds,
            "route_basis": None,
            "vehicle_position": vehicle_position,
            "pickup": pickup,
            "destination": destination,
            "route": None,
            "planned_route_status": "NOT_APPLICABLE",
            "planned_route": None,
        }

    if execution_status in {
        DispatchAssignment.ExecutionStatus.ASSIGNED,
        DispatchAssignment.ExecutionStatus.EN_ROUTE_TO_PICKUP,
    }:
        phase = "TO_PICKUP"
        if vehicle_position is None:
            return {
                "phase": phase,
                "execution_status": execution_status,
                "route_status": "POSITION_UNAVAILABLE",
                "position_state": "UNAVAILABLE",
                "position_recorded_at": None,
                "position_age_seconds": None,
                "route_basis": None,
                "vehicle_position": None,
                "pickup": pickup,
                "destination": destination,
                "route": None,
                "planned_route_status": planned_route_status,
                "planned_route": planned_route,
            }
        origin = [vehicle_position["longitude"], vehicle_position["latitude"]]
        target = [pickup["longitude"], pickup["latitude"]]
        route_basis = (
            "CURRENT_VEHICLE_POSITION"
            if position_state == "CURRENT"
            else "LAST_KNOWN_VEHICLE_POSITION"
        )
        identity = f"driver:{assignment.pk}:{phase}:{event.pk}"
    else:
        phase = "TO_DESTINATION"
        if execution_status == DispatchAssignment.ExecutionStatus.IN_TRANSIT:
            if vehicle_position is None:
                return {
                    "phase": phase,
                    "execution_status": execution_status,
                    "route_status": "POSITION_UNAVAILABLE",
                    "position_state": "UNAVAILABLE",
                    "position_recorded_at": None,
                    "position_age_seconds": None,
                    "route_basis": None,
                    "vehicle_position": None,
                    "pickup": pickup,
                    "destination": destination,
                    "route": None,
                    "planned_route_status": "NOT_APPLICABLE",
                    "planned_route": None,
                }
            origin = [vehicle_position["longitude"], vehicle_position["latitude"]]
            route_basis = (
                "CURRENT_VEHICLE_POSITION"
                if position_state == "CURRENT"
                else "LAST_KNOWN_VEHICLE_POSITION"
            )
            identity = f"driver:{assignment.pk}:{phase}:{event.pk}"
        else:
            origin = [pickup["longitude"], pickup["latitude"]]
            route_basis = "PICKUP"
            identity = f"driver:{assignment.pk}:{phase}:pickup"
        target = [destination["longitude"], destination["latitude"]]

    try:
        route = routing.get_route_between(identity, origin, target)
    except (routing.RouteConfigurationError, routing.RouteServiceError):
        route = None
    return {
        "phase": phase,
        "execution_status": execution_status,
        "route_status": "AVAILABLE" if route else "TEMPORARILY_UNAVAILABLE",
        "position_state": position_state,
        "position_recorded_at": position_recorded_at,
        "position_age_seconds": position_age_seconds,
        "route_basis": route_basis,
        "vehicle_position": vehicle_position,
        "pickup": pickup,
        "destination": destination,
        "route": route,
        "planned_route_status": planned_route_status,
        "planned_route": planned_route,
    }


def recommendation_route(item, vehicle):
    """Build road geometry only for the dispatcher-selected recommendation."""
    pickup, destination = _request_places(item)
    event, position_state, position_recorded_at, position_age_seconds, vehicle_position = (
        _vehicle_position(vehicle)
    )
    planned_route = None
    try:
        planned_route = routing.get_route(item)
    except (routing.RouteConfigurationError, routing.RouteServiceError):
        pass

    route = None
    route_basis = None
    route_status = "POSITION_UNAVAILABLE"
    if vehicle_position is not None:
        route_basis = (
            "CURRENT_VEHICLE_POSITION"
            if position_state == "CURRENT"
            else "LAST_KNOWN_VEHICLE_POSITION"
        )
        try:
            route = routing.get_route_between(
                f"recommendation:{item.pk}:{vehicle.pk}:{event.pk}",
                [vehicle_position["longitude"], vehicle_position["latitude"]],
                [pickup["longitude"], pickup["latitude"]],
            )
        except (routing.RouteConfigurationError, routing.RouteServiceError):
            pass
        route_status = "AVAILABLE" if route else "TEMPORARILY_UNAVAILABLE"

    return {
        "phase": "TO_PICKUP",
        "execution_status": "RECOMMENDATION",
        "route_status": route_status,
        "position_state": position_state,
        "position_recorded_at": position_recorded_at,
        "position_age_seconds": position_age_seconds,
        "route_basis": route_basis,
        "vehicle_position": vehicle_position,
        "pickup": pickup,
        "destination": destination,
        "route": route,
        "planned_route_status": "AVAILABLE" if planned_route else "TEMPORARILY_UNAVAILABLE",
        "planned_route": planned_route,
    }
