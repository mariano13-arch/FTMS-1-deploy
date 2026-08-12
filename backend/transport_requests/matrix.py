import hashlib
import json
import math
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from fleet.models import Vehicle
from telemetry.models import TelemetryEvent

from .models import TransportRequest

MATRIX_URL = "https://api.tomtom.com/routing/matrix/2"
MATRIX_TIMEOUT_SECONDS = 12
MATRIX_CACHE_TTL_SECONDS = 60
MAX_CELLS = 100


class MatrixError(Exception):
    pass


class MatrixConfigurationError(MatrixError):
    pass


class MatrixUpstreamError(MatrixError):
    pass


class MatrixCandidateError(MatrixError):
    pass


class MatrixLimitError(MatrixError):
    pass


def _coordinate(value, *, latitude):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError from error
    limit = 90 if latitude else 180
    if not math.isfinite(number) or not -limit <= number <= limit:
        raise ValueError
    return number


def eligible_vehicle_origins(vehicle_ids=None):
    cutoff = timezone.now() - timedelta(seconds=settings.DISPATCH_TELEMETRY_MAX_AGE_SECONDS)
    latest = TelemetryEvent.objects.filter(vehicle_id=OuterRef("pk")).order_by(
        "-recorded_at", "-sequence_number", "-received_at", "-pk"
    )
    queryset = (
        Vehicle.objects.filter(is_active=True)
        .annotate(
            latest_telemetry_id=Subquery(latest.values("pk")[:1]),
            latest_telemetry_recorded_at=Subquery(latest.values("recorded_at")[:1]),
        )
        .filter(latest_telemetry_recorded_at__gte=cutoff)
        .order_by("device_id")
    )
    if vehicle_ids is not None:
        queryset = queryset.filter(device_id__in=vehicle_ids)
    vehicles = list(queryset)
    events = {
        event.pk: event
        for event in TelemetryEvent.objects.filter(
            pk__in=[vehicle.latest_telemetry_id for vehicle in vehicles]
        )
    }
    origins = []
    for vehicle in vehicles:
        event = events.get(vehicle.latest_telemetry_id)
        try:
            latitude = _coordinate(event.location.y, latitude=True)
            longitude = _coordinate(event.location.x, latitude=False)
        except (AttributeError, ValueError):
            continue
        origins.append(
            {"vehicle_id": vehicle.device_id, "latitude": latitude, "longitude": longitude}
        )
    return origins


def eligible_request_destinations(request_ids=None):
    queryset = TransportRequest.objects.filter(
        status=TransportRequest.Status.APPROVED, assigned_vehicle__isnull=True
    ).order_by("id")
    if request_ids is not None:
        queryset = queryset.filter(pk__in=request_ids)
    destinations = []
    for item in queryset:
        try:
            latitude = _coordinate(item.pickup_latitude, latitude=True)
            longitude = _coordinate(item.pickup_longitude, latitude=False)
        except ValueError:
            continue
        destinations.append(
            {"request_id": str(item.pk), "latitude": latitude, "longitude": longitude}
        )
    return destinations


def _safe_cell_status(cell):
    detailed = cell.get("detailedError")
    inner = detailed.get("innerError") if isinstance(detailed, dict) else None
    code = (
        inner.get("code")
        if isinstance(inner, dict)
        else detailed.get("code")
        if isinstance(detailed, dict)
        else ""
    )
    if code in {"NO_ROUTE_FOUND", "MAP_MATCHING_FAILURE"}:
        return "NO_ROUTE"
    if code == "OUT_OF_REGION":
        return "OUT_OF_REGION"
    return "CELL_ERROR"


def _normalize(payload, origins, destinations):
    data = payload.get("data") if isinstance(payload, dict) else None
    rows, columns = len(origins), len(destinations)
    if not isinstance(data, list) or len(data) != rows * columns:
        raise MatrixUpstreamError
    durations = [[None for _ in range(columns)] for _ in range(rows)]
    distances = [[None for _ in range(columns)] for _ in range(rows)]
    delays = [[None for _ in range(columns)] for _ in range(rows)]
    statuses = [[None for _ in range(columns)] for _ in range(rows)]
    seen = set()
    for cell in data:
        try:
            row, column = cell["originIndex"], cell["destinationIndex"]
            if (
                isinstance(row, bool)
                or isinstance(column, bool)
                or not isinstance(row, int)
                or not isinstance(column, int)
            ):
                raise ValueError
            if not 0 <= row < rows or not 0 <= column < columns or (row, column) in seen:
                raise ValueError
            seen.add((row, column))
            summary = cell.get("routeSummary")
            if isinstance(summary, dict):
                duration = int(summary["travelTimeInSeconds"])
                distance = int(summary["lengthInMeters"])
                delay = int(summary.get("trafficDelayInSeconds", 0))
                if min(duration, distance, delay) < 0:
                    raise ValueError
                (
                    durations[row][column],
                    distances[row][column],
                    delays[row][column],
                    statuses[row][column],
                ) = duration, distance, delay, "OK"
            elif "detailedError" in cell:
                statuses[row][column] = _safe_cell_status(cell)
            else:
                raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise MatrixUpstreamError from error
    if len(seen) != rows * columns or any(status is None for row in statuses for status in row):
        raise MatrixUpstreamError
    return {
        "traffic_mode": "live",
        "depart_at": "now",
        "vehicle_ids": [origin["vehicle_id"] for origin in origins],
        "request_ids": [destination["request_id"] for destination in destinations],
        "durations_seconds": durations,
        "distances_meters": distances,
        "traffic_delays_seconds": delays,
        "cell_statuses": statuses,
        "vehicle_count": rows,
        "request_count": columns,
        "cell_count": rows * columns,
    }


def _call_tomtom(origins, destinations):
    key = settings.TOMTOM_API_KEY.strip()
    if not key:
        raise MatrixConfigurationError
    body = {
        "origins": [
            {"point": {"latitude": item["latitude"], "longitude": item["longitude"]}}
            for item in origins
        ],
        "destinations": [
            {"point": {"latitude": item["latitude"], "longitude": item["longitude"]}}
            for item in destinations
        ],
        "options": {
            "departAt": "now",
            "traffic": "live",
            "routeType": "fastest",
            "travelMode": "car",
        },
    }
    request = Request(
        f"{MATRIX_URL}?{urlencode({'key': key})}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=MATRIX_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read())
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise MatrixUpstreamError from error
    return _normalize(payload, origins, destinations)


def build_dispatch_matrix(vehicle_ids=None, request_ids=None):
    origins = eligible_vehicle_origins(vehicle_ids)
    if not origins:
        raise MatrixCandidateError("No eligible vehicles with current locations.")
    destinations = eligible_request_destinations(request_ids)
    if not destinations:
        raise MatrixCandidateError("No dispatch-eligible requests with valid pickup locations.")
    cell_count = len(origins) * len(destinations)
    if cell_count > MAX_CELLS:
        raise MatrixLimitError(
            "The synchronous dispatch matrix exceeds the current 100-cell Sprint 5D limit."
        )
    material = json.dumps(
        {
            "origins": origins,
            "destinations": destinations,
            "traffic": "live",
            "departAt": "now",
            "routeType": "fastest",
            "travelMode": "car",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    cache_key = f"dispatch-matrix:v1:{hashlib.sha256(material.encode()).hexdigest()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    result = _call_tomtom(origins, destinations)
    cache.set(cache_key, result, MATRIX_CACHE_TTL_SECONDS)
    return result
