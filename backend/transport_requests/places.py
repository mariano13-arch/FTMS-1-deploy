import json
import math
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings

SUGGEST_URL = "https://api.tomtom.com/maps/orbis/places/suggest"
DETAILS_URL = "https://api.tomtom.com/maps/orbis/places/details"
TIMEOUT_SECONDS = 8
ALLOWED_TYPES = {"poi", "address", "street", "intersection", "area"}
TYPE_PATHS = {
    "poi": "pois",
    "address": "addresses",
    "street": "streets",
    "intersection": "intersections",
    "area": "areas",
}


class PlacesConfigurationError(Exception):
    pass


class PlacesServiceError(Exception):
    pass


class PlacesUnavailableError(PlacesServiceError):
    pass


class PlacesNotFoundError(PlacesServiceError):
    pass


def _headers(session_id, attributes, *, content=False):
    key = settings.TOMTOM_API_KEY.strip()
    if not key:
        raise PlacesConfigurationError
    headers = {
        "Accept": "application/json",
        "Accept-Language": "en-PH,en",
        "TomTom-Api-Version": "3",
        "TomTom-Api-Key": key,
        "Session-Id": str(session_id),
        "Attributes": attributes,
    }
    if content:
        headers["Content-Type"] = "application/json"
    return headers


def _read(request):
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read())
    except HTTPError as error:
        if error.code == 404:
            raise PlacesNotFoundError from error
        if error.code == 429 or error.code >= 500:
            raise PlacesUnavailableError from error
        raise PlacesServiceError from error
    except (URLError, TimeoutError, OSError) as error:
        raise PlacesUnavailableError from error
    except json.JSONDecodeError as error:
        raise PlacesServiceError from error


def suggest(query, session_id):
    body = {
        "query": query,
        "maxResults": 5,
        "filters": {
            "types": ["poi", "address", "street", "intersection", "area"],
            "countryCodesIso2": ["PH"],
        },
    }
    request = Request(
        SUGGEST_URL,
        data=json.dumps(body).encode(),
        method="POST",
        headers=_headers(session_id, "results(id,type,title,subtitles)", content=True),
    )
    payload = _read(request)
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise PlacesServiceError
    normalized = []
    for result in results:
        if not isinstance(result, dict) or result.get("type") not in ALLOWED_TYPES:
            continue
        if not all(
            isinstance(result.get(field), str) and result[field] for field in ("id", "title")
        ):
            continue
        subtitles = result.get("subtitles", [])
        normalized.append(
            {
                "id": result["id"],
                "type": result["type"],
                "title": result["title"],
                "subtitles": [value for value in subtitles if isinstance(value, str)][:3]
                if isinstance(subtitles, list)
                else [],
            }
        )
    return {"results": normalized[:5]}


def _display_address(payload):
    subtitles = payload.get("subtitles")
    if isinstance(subtitles, list):
        useful = [value.strip() for value in subtitles if isinstance(value, str) and value.strip()]
        if useful:
            return ", ".join(useful)
    address = payload.get("address")
    if not isinstance(address, dict):
        return ""
    street = " ".join(
        str(address.get(key, "")).strip() for key in ("houseNumber", "street")
    ).strip()
    parts = [
        street,
        address.get("municipalitySubdivision"),
        address.get("municipality"),
        address.get("postalCode"),
        address.get("country"),
    ]
    return ", ".join(str(value).strip() for value in parts if value and str(value).strip())


def details(place_type, place_id, session_id):
    if place_type not in TYPE_PATHS:
        raise ValueError("Unsupported place type")
    url = f"{DETAILS_URL}/{TYPE_PATHS[place_type]}/{quote(place_id, safe='')}"
    request = Request(
        url,
        headers=_headers(session_id, "id,type,title,subtitles,position,address"),
        method="GET",
    )
    payload = _read(request)
    try:
        coordinates = payload["position"]["coordinates"]
        longitude, latitude = float(coordinates[0]), float(coordinates[1])
        if payload["position"]["type"] != "Point" or not (
            -180 <= longitude <= 180 and -90 <= latitude <= 90
        ):
            raise ValueError
        if not math.isfinite(longitude) or not math.isfinite(latitude):
            raise ValueError
        display_address = _display_address(payload)
        if not display_address:
            raise ValueError
        return {
            "id": str(payload["id"]),
            "type": str(payload["type"]),
            "title": str(payload["title"]),
            "display_address": display_address,
            "latitude": latitude,
            "longitude": longitude,
        }
    except (KeyError, IndexError, TypeError, ValueError, OverflowError) as error:
        raise PlacesServiceError from error
