import json
import math
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache

SEARCH_URL = "https://api.tomtom.com/search/2/search"
TIMEOUT_SECONDS = 8
ALLOWED_TYPES = {"poi", "address", "street", "intersection", "area"}
RESULT_TYPES = {
    "POI": "poi",
    "Point Address": "address",
    "Address Range": "address",
    "Street": "street",
    "Cross Street": "intersection",
    "Geography": "area",
}
CACHE_SECONDS = 15 * 60


class PlacesConfigurationError(Exception):
    pass


class PlacesServiceError(Exception):
    pass


class PlacesUnavailableError(PlacesServiceError):
    pass


class PlacesNotFoundError(PlacesServiceError):
    pass


def _api_key():
    key = settings.TOMTOM_SEARCH_API_KEY.strip() or settings.TOMTOM_API_KEY.strip()
    if not key:
        raise PlacesConfigurationError
    return key


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


def _cache_key(session_id, place_type, place_id):
    return f"places:{session_id}:{place_type}:{place_id}"


def _normalize(result):
    if not isinstance(result, dict):
        return None
    place_type = RESULT_TYPES.get(result.get("type"))
    address = result.get("address")
    display_address = (
        address.get("freeformAddress", "").strip() if isinstance(address, dict) else ""
    )
    poi = result.get("poi")
    title = poi.get("name") if isinstance(poi, dict) else display_address
    try:
        latitude = float(result["position"]["lat"])
        longitude = float(result["position"]["lon"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not place_type or not result.get("id") or not title or not display_address:
        return None
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return {
        "id": str(result["id"]),
        "type": place_type,
        "title": str(title),
        "subtitles": [] if display_address == title else [display_address],
        "display_address": display_address,
        "latitude": latitude,
        "longitude": longitude,
    }


def suggest(query, session_id):
    params = urlencode(
        {
            "key": _api_key(),
            "countrySet": "PH",
            "limit": 5,
            "typeahead": "true",
            "view": "Unified",
            "language": "en-US",
        }
    )
    payload = _read(Request(f"{SEARCH_URL}/{quote(query, safe='')}.json?{params}"))
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise PlacesServiceError
    suggestions = []
    for result in results:
        detail = _normalize(result)
        if detail is None:
            continue
        cache.set(_cache_key(session_id, detail["type"], detail["id"]), detail, CACHE_SECONDS)
        suggestions.append({key: detail[key] for key in ("id", "type", "title", "subtitles")})
    return {"results": suggestions[:5]}


def details(place_type, place_id, session_id):
    if place_type not in ALLOWED_TYPES:
        raise ValueError("Unsupported place type")
    result = cache.get(_cache_key(session_id, place_type, place_id))
    if not isinstance(result, dict):
        raise PlacesNotFoundError
    return result
