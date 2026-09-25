from __future__ import annotations

import re
import socket
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.utils import timezone

from fleet.external_fuel_prices import (
    FETCH_TIMEOUT_SECONDS,
    USER_AGENT,
    ExternalFuelPriceObservation,
    FuelPriceFetchError,
    ProductResult,
    SourceResponse,
    _html_title,
    _visible_text,
    persist_external_fuel_prices,
)

GASWATCH_URL = "https://gaswatchph.com/"
GASWATCH_PROVIDER = "GasWatchPH"
GASWATCH_GASOLINE_PROVIDER = "GasWatchPH [Metro Manila; reference=UNLEADED_91]"
GASWATCH_DIESEL_PROVIDER = "GasWatchPH [Metro Manila; reference=REGULAR_DIESEL]"
PRODUCTS = {
    "REGULAR_DIESEL": ("DIESEL", r"diesel"),
    "PREMIUM_DIESEL": ("DIESEL", r"(?:prem(?:ium)?\.?\s+diesel)"),
    "UNLEADED_91": ("GASOLINE", r"unleaded(?:\s*91)?"),
    "PREMIUM_95": ("GASOLINE", r"prem(?:ium)?\.?\s*95"),
    "PREMIUM_97": ("GASOLINE", r"prem(?:ium)?\.?\s*97"),
}


def _provider(fuel_grade: str) -> str:
    return f"GasWatchPH [Metro Manila; reference={fuel_grade}]"


@dataclass(frozen=True)
class GasWatchRefreshReport:
    products: dict[str, ProductResult]
    response: SourceResponse | None = None
    fetch_error: str | None = None
    station_metadata: str | None = None
    geographic_metadata: str | None = None


def _classify_gaswatch_response(
    html: str, *, status: int, final_url: str, content_type: str
) -> SourceResponse:
    title = _html_title(html)
    text = _visible_text(html)
    lowered = f"{title or ''} {text}".casefold()
    challenge_markers = (
        "captcha",
        "verify you are human",
        "checking your browser",
        "access denied",
        "cloudflare ray id",
    )
    expected = ("diesel", "unleaded")
    missing = tuple(label for label in expected if label not in lowered)
    if any(marker in lowered for marker in challenge_markers):
        classification = "INTERSTITIAL_OR_CHALLENGE"
    elif html.strip() and "html" in content_type.casefold() and not missing:
        classification = "NORMAL_PRICE_PAGE"
    else:
        classification = "UNEXPECTED_HTML"
    return SourceResponse(
        body=html,
        status=status,
        final_url=final_url,
        content_type=content_type,
        body_length=len(html.encode("utf-8")),
        title=title,
        classification=classification,
        missing_labels=missing,
    )


def fetch_gaswatch_ph() -> tuple[SourceResponse, datetime]:
    request = Request(
        GASWATCH_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    )
    try:
        with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", 200)
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "")
            if status < 200 or status >= 300:
                raise FuelPriceFetchError(
                    f"GasWatch PH returned HTTP {status}.",
                    classification="HTTP_ERROR",
                    status=status,
                    final_url=final_url,
                    content_type=content_type,
                )
            html = response.read().decode("utf-8", errors="replace")
            return (
                _classify_gaswatch_response(
                    html,
                    status=status,
                    final_url=final_url,
                    content_type=content_type,
                ),
                timezone.now(),
            )
    except HTTPError as exc:
        raise FuelPriceFetchError(
            f"GasWatch PH returned HTTP {exc.code}.",
            classification="HTTP_ERROR",
            status=exc.code,
            final_url=exc.geturl(),
        ) from exc
    except (URLError, TimeoutError, socket.timeout, OSError) as exc:
        raise FuelPriceFetchError(
            f"GasWatch PH request failed: {type(exc).__name__}.",
            classification="NETWORK_ERROR",
            final_url=GASWATCH_URL,
        ) from exc


_MONTH = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)
_DATE_PATTERNS = (
    (rf"\b({_MONTH})\s+(\d{{1,2}})(?:\s*[-–]\s*\d{{1,2}})?,\s*(\d{{4}})\b", "%B"),
    (rf"\b(\d{{1,2}})\s+({_MONTH})\s+(\d{{4}})\b", "day-first"),
    (r"\b(\d{4})-(\d{2})-(\d{2})\b", "iso"),
)


def _parse_effective_date(text: str):
    for pattern, kind in _DATE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        if kind == "iso":
            return datetime.strptime(match.group(0), "%Y-%m-%d").date()
        if kind == "day-first":
            token = f"{match.group(1)} {match.group(2)} {match.group(3)}"
            for fmt in ("%d %b %Y", "%d %B %Y"):
                try:
                    return datetime.strptime(token, fmt).date()
                except ValueError:
                    continue
        else:
            token = f"{match.group(1)} {match.group(2)}, {match.group(3)}"
            for fmt in ("%b %d, %Y", "%B %d, %Y"):
                try:
                    return datetime.strptime(token, fmt).date()
                except ValueError:
                    continue
    raise ValueError("GasWatch effective/update date is missing or invalid.")


_PRICE = r"[+-]?(?:\d+(?:[.,]\d+)?|NaN|Infinity)"


def _parse_price(text: str, fuel_grade: str) -> Decimal:
    _, product_label = PRODUCTS[fuel_grade]
    label = rf"(?:avg\.?|average)\s+{product_label}"
    bounded_metric = (
        r"(?:(?!\b(?:avg\.?|average|cheapest|premium|brand|station)\b).){0,160}?"
    )
    patterns = (
        rf"\b{label}\b{bounded_metric}(?:PHP|₱)\s*({_PRICE})\s*"
        rf"(?:PHP\s*)?(?:/|per\s+)\s*(?:L|lit(?:er|re))\b",
        rf"\b{label}\b{bounded_metric}(?:price\s*)?\(?\s*PHP\s*/\s*"
        rf"(?:L|lit(?:er|re))\s*\)?\s*[:=]?\s*(?:PHP|₱)?\s*({_PRICE})\b",
    )
    if fuel_grade == "REGULAR_DIESEL":
        patterns += (
            rf"\bMetro Manila average diesel price is\s*(?:PHP|₱)\s*({_PRICE})\s*/\s*L\b",
            rf"\bMetro Manila averages are\s*(?:PHP|₱)\s*({_PRICE})\s*/\s*L\s+for diesel\b",
        )
    elif fuel_grade == "UNLEADED_91":
        patterns += (
            rf"\bMetro Manila average diesel price is\s*(?:PHP|₱)\s*{_PRICE}\s*/\s*L"
            rf"\s+and unleaded is\s*(?:PHP|₱)\s*({_PRICE})\s*/\s*L\b",
            rf"\bMetro Manila averages are\s*(?:PHP|₱)\s*{_PRICE}\s*/\s*L\s+for diesel"
            rf"\s+and\s*(?:PHP|₱)\s*({_PRICE})\s*/\s*L\s+for unleaded\b",
        )
    candidates = {
        match.group(1)
        for pattern in patterns
        for match in re.finditer(pattern, text, re.IGNORECASE)
    }
    if not candidates:
        raise ValueError(f"Explicit overall {fuel_grade} PHP/L value is missing.")
    values = set()
    for token in candidates:
        normalized = (
            token.replace(",", ".")
            if "," in token and "." not in token
            else token.replace(",", "")
        )
        try:
            value = Decimal(normalized)
        except InvalidOperation:
            raise ValueError(f"Overall {fuel_grade} price is malformed.") from None
        if not value.is_finite() or value <= 0:
            raise ValueError(f"Overall {fuel_grade} price must be finite and positive.")
        values.add(value)
    if len(values) != 1:
        raise ValueError(f"Conflicting overall {fuel_grade} PHP/L values.")
    return values.pop()


def parse_gaswatch_ph_prices(
    response: SourceResponse, *, retrieved_at: datetime | None = None
) -> dict[str, ProductResult]:
    retrieved_at = retrieved_at or timezone.now()
    if timezone.is_naive(retrieved_at):
        retrieved_at = timezone.make_aware(retrieved_at)
    if response.classification != "NORMAL_PRICE_PAGE":
        reason = f"SOURCE_UNAVAILABLE: {response.classification}."
        return {
            fuel_grade: ProductResult(fuel_type, "FAILED", reason)
            for fuel_grade, (fuel_type, _) in PRODUCTS.items()
        }

    text = _visible_text(response.body)
    try:
        effective_date = _parse_effective_date(f"{response.title or ''} {text}")
        effective_at = timezone.make_aware(
            datetime.combine(effective_date, time.min),
            timezone.get_current_timezone(),
        )
        if effective_at > retrieved_at:
            raise ValueError("GasWatch effective date is in the future.")
        date_error = None
    except ValueError as exc:
        effective_at = None
        date_error = str(exc)

    results = {}
    for fuel_grade, (fuel_type, _) in PRODUCTS.items():
        try:
            if date_error:
                raise ValueError(date_error)
            observation = ExternalFuelPriceObservation(
                fuel_type=fuel_type,
                fuel_grade=fuel_grade,
                price_per_liter=_parse_price(text, fuel_grade),
                effective_at=effective_at,
                retrieved_at=retrieved_at,
                provider=_provider(fuel_grade),
            )
            results[fuel_grade] = ProductResult(
                fuel_type,
                "EXISTING",
                "VALIDATED_GASWATCH_NOT_YET_PERSISTED",
                observation,
            )
        except ValueError as exc:
            results[fuel_grade] = ProductResult(fuel_type, "FAILED", str(exc))
    return results


def _metadata(text: str) -> tuple[str | None, str | None]:
    station_match = re.search(
        r"\b(?:stations?\s+tracked|tracking)\s*[:=]?\s*([\d,]+\s+stations?)?",
        text,
        re.IGNORECASE,
    )
    geography = "Metro Manila" if re.search(r"\bMetro Manila\b", text, re.IGNORECASE) else None
    station = station_match.group(0).strip() if station_match else None
    return station, geography


def refresh_gaswatch_ph() -> GasWatchRefreshReport:
    try:
        response, retrieved_at = fetch_gaswatch_ph()
    except FuelPriceFetchError as exc:
        return GasWatchRefreshReport(
            products={
                fuel_grade: ProductResult(fuel_type, "FAILED", str(exc))
                for fuel_grade, (fuel_type, _) in PRODUCTS.items()
            },
            fetch_error=str(exc),
        )
    parsed = parse_gaswatch_ph_prices(response, retrieved_at=retrieved_at)
    station, geography = _metadata(_visible_text(response.body))
    return GasWatchRefreshReport(
        products=persist_external_fuel_prices(parsed),
        response=response,
        station_metadata=station,
        geographic_metadata=geography,
    )
