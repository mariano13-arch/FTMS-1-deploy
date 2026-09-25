import hashlib
import json
import math
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache

ROUTING_URL = "https://api.tomtom.com/maps/orbis/routing/routes/calculate"
ROUTE_CACHE_TTL_SECONDS = 120
ROUTE_TIMEOUT_SECONDS = 8


class RouteConfigurationError(Exception):
    pass


class RouteCoordinateError(Exception):
    pass


class RouteServiceError(Exception):
    pass


def _coordinate(value, *, latitude):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise RouteCoordinateError from error
    limit = 90 if latitude else 180
    if not math.isfinite(number) or not -limit <= number <= limit:
        raise RouteCoordinateError
    return number


def _request_coordinates(item):
    return (
        [
            _coordinate(item.pickup_longitude, latitude=False),
            _coordinate(item.pickup_latitude, latitude=True),
        ],
        [
            _coordinate(item.destination_longitude, latitude=False),
            _coordinate(item.destination_latitude, latitude=True),
        ],
    )


def _merge_geometry(legs):
    coordinates = []
    for leg in legs:
        path = leg.get("path") if isinstance(leg, dict) else None
        points = (
            path.get("coordinates")
            if isinstance(path, dict) and path.get("type") == "LineString"
            else None
        )
        if not isinstance(points, list) or len(points) < 2:
            raise RouteServiceError
        for point in points:
            if not isinstance(point, list) or len(point) != 2:
                raise RouteServiceError
            normalized = [
                _coordinate(point[0], latitude=False),
                _coordinate(point[1], latitude=True),
            ]
            if not coordinates or coordinates[-1] != normalized:
                coordinates.append(normalized)
    if len(coordinates) < 2:
        raise RouteServiceError
    return {"type": "LineString", "coordinates": coordinates}


def _normalize(payload):
    try:
        route = payload["routes"][0]
        summary = route["summary"]
        result = {
            "distance_meters": int(summary["lengthInMeters"]),
            "duration_seconds": int(summary["travelDurationInSeconds"]),
            "traffic_delay_seconds": int(summary.get("trafficDelayDurationInSeconds", 0)),
            "departure_time": summary["departureDateTime"],
            "arrival_time": summary["arrivalDateTime"],
            "geometry": _merge_geometry(route["legs"]),
        }
    except (KeyError, IndexError, TypeError, ValueError, OverflowError) as error:
        raise RouteServiceError from error
    if (
        min(result["distance_meters"], result["duration_seconds"], result["traffic_delay_seconds"])
        < 0
    ):
        raise RouteServiceError
    return result


def _calculate(origin, destination):
    api_key = settings.TOMTOM_API_KEY.strip()
    if not api_key:
        raise RouteConfigurationError
    body = {
        "routePlanningLocations": {
            "origin": {"type": "Point", "coordinates": origin},
            "destination": {"type": "Point", "coordinates": destination},
        },
        "traffic": "live",
        "routeType": "fast",
        "travelMode": "car",
        "vehicleEngineType": "combustion",
        "departureDateTime": "now",
        "maxPathAlternativeRoutes": 0,
    }
    request = Request(
        ROUTING_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "TomTom-Api-Version": "3",
            "TomTom-Api-Key": api_key,
            "Attributes": "routes(summary,legs.path)",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=ROUTE_TIMEOUT_SECONDS) as response:
            return _normalize(json.loads(response.read()))
    except RouteServiceError:
        raise
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
        raise RouteServiceError from error


def get_route(item):
    origin, destination = _request_coordinates(item)
    return get_route_between(str(item.pk), origin, destination)


def get_route_between(identity, origin, destination):
    origin = [
        _coordinate(origin[0], latitude=False),
        _coordinate(origin[1], latitude=True),
    ]
    destination = [
        _coordinate(destination[0], latitude=False),
        _coordinate(destination[1], latitude=True),
    ]
    material = json.dumps([str(identity), origin, destination, "live"], separators=(",", ":"))
    cache_key = f"transport-route:v1:{hashlib.sha256(material.encode()).hexdigest()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    result = {"traffic_mode": "live", **_calculate(origin, destination)}
    cache.set(cache_key, result, ROUTE_CACHE_TTL_SECONDS)
    return result
