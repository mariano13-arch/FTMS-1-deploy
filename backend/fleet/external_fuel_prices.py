from __future__ import annotations

import re
import socket
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from django.db import transaction
from django.utils import timezone

from fleet.models import FuelPriceRecord

SOURCE_URL = "https://www.globalpetrolprices.com/Philippines/"
PRODUCT_URLS = {
    "GASOLINE": f"{SOURCE_URL}gasoline_prices/",
    "DIESEL": f"{SOURCE_URL}diesel_prices/",
}
PROVIDER = "GlobalPetrolPrices"
FETCH_TIMEOUT_SECONDS = 12
USER_AGENT = "FTMS/1.0 (Philippines weekly fuel-price cache)"
SUPPORTED_PRODUCTS = ("GASOLINE", "DIESEL")


ResponseClassification = Literal[
    "NORMAL_PRICE_PAGE",
    "INTERSTITIAL_OR_CHALLENGE",
    "UNEXPECTED_HTML",
    "HTTP_ERROR",
    "NETWORK_ERROR",
]


@dataclass(frozen=True)
class SourceResponse:
    body: str
    status: int
    final_url: str
    content_type: str
    body_length: int
    title: str | None
    classification: ResponseClassification
    missing_labels: tuple[str, ...] = ()

    @property
    def safe_location(self) -> str:
        parts = urlsplit(self.final_url)
        return f"{parts.hostname or 'unknown'}{parts.path or '/'}"


class FuelPriceFetchError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        classification: ResponseClassification,
        status: int | None = None,
        final_url: str | None = None,
        content_type: str | None = None,
    ):
        super().__init__(message)
        self.classification = classification
        self.status = status
        self.final_url = final_url
        self.content_type = content_type


class _VisibleTextParser(HTMLParser):
    """Extract visible text while excluding scripts and styles."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "title"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "title"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data):
        if not self._ignored_depth:
            value = " ".join(data.split())
            if value:
                self.parts.append(value)


class _TableTextParser(HTMLParser):
    """Retain table row/cell relationships while tolerating nested markup."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._table = []
        elif self._table_depth == 1 and tag == "tr":
            self._row = []
        elif self._table_depth == 1 and tag in {"td", "th"}:
            self._cell_parts = []

    def handle_endtag(self, tag):
        if self._table_depth == 1 and tag in {"td", "th"} and self._cell_parts is not None:
            if self._row is not None:
                self._row.append(" ".join(self._cell_parts).strip())
            self._cell_parts = None
        elif self._table_depth == 1 and tag == "tr":
            if self._table is not None and self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table_depth:
            if self._table_depth == 1 and self._table:
                self.tables.append(self._table)
                self._table = None
            self._table_depth -= 1

    def handle_data(self, data):
        if self._cell_parts is not None:
            value = " ".join(data.split())
            if value:
                self._cell_parts.append(value)


@dataclass(frozen=True)
class ExternalFuelPriceObservation:
    fuel_type: str
    price_per_liter: Decimal
    effective_at: datetime
    retrieved_at: datetime
    fuel_grade: str = ""
    currency: str = FuelPriceRecord.Currency.PHP
    provider: str = PROVIDER


@dataclass(frozen=True)
class ProductResult:
    fuel_type: str
    status: Literal["CREATED", "EXISTING", "FAILED"]
    reason: str
    observation: ExternalFuelPriceObservation | None = None
    record_id: int | None = None


@dataclass(frozen=True)
class FuelPriceRefreshReport:
    products: dict[str, ProductResult]
    fetch_error: str | None = None
    responses: tuple[SourceResponse, ...] = ()
    classification: ResponseClassification = "UNEXPECTED_HTML"


_DATE_TOKEN = (
    r"(?:\d{1,2}[-\s](?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)[-\s]\d{4}|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2})"
)
_DATE_FORMATS = (
    "%d-%b-%Y",
    "%d-%B-%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%Y-%m-%d",
)


def _html_title(html: str) -> str | None:
    match = re.search(r"<title\b[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return " ".join(re.sub(r"<[^>]+>", " ", match.group(1)).split())[:160] or None


def _classify_response(
    html: str, *, status: int, final_url: str, content_type: str, product: str | None
) -> SourceResponse:
    text = _visible_text(html)
    title = _html_title(html)
    semantic_text = f"{title or ''} {text}".strip()
    lowered = semantic_text.casefold()
    challenge_markers = (
        "captcha",
        "verify you are human",
        "checking your browser",
        "access denied",
        "attention required",
        "cloudflare ray id",
        "sign in to continue",
        "subscription required",
    )
    if any(marker in lowered for marker in challenge_markers):
        classification: ResponseClassification = "INTERSTITIAL_OR_CHALLENGE"
        missing_labels: tuple[str, ...] = ()
    else:
        expected = ["PHP"]
        expected.append(f"{product.title()} prices" if product else "Gasoline prices")
        if product is None:
            expected.extend(("Diesel prices", "USD"))
        missing = [label for label in expected if label.casefold() not in lowered]
        if not re.search(_DATE_TOKEN, semantic_text, re.IGNORECASE):
            missing.append("effective date")
        missing_labels = tuple(missing)
        valid_content_type = "html" in content_type.casefold()
        if html.strip() and valid_content_type and not missing_labels:
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
        missing_labels=missing_labels,
    )


def _fetch_source_page(url: str, *, product: str | None = None) -> tuple[SourceResponse, datetime]:
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    )
    try:
        with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", 200)
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "")
            if status < 200 or status >= 300:
                raise FuelPriceFetchError(
                    f"Source returned HTTP {status}.",
                    classification="HTTP_ERROR",
                    status=status,
                    final_url=final_url,
                    content_type=content_type,
                )
            html = response.read().decode("utf-8", errors="replace")
            return (
                _classify_response(
                    html,
                    status=status,
                    final_url=final_url,
                    content_type=content_type,
                    product=product,
                ),
                timezone.now(),
            )
    except HTTPError as exc:
        raise FuelPriceFetchError(
            f"Source returned HTTP {exc.code}.",
            classification="HTTP_ERROR",
            status=exc.code,
            final_url=exc.geturl(),
            content_type=exc.headers.get("Content-Type", "") if exc.headers else "",
        ) from exc
    except (URLError, TimeoutError, socket.timeout, OSError) as exc:
        raise FuelPriceFetchError(
            f"Source request failed: {type(exc).__name__}.",
            classification="NETWORK_ERROR",
            final_url=url,
        ) from exc


def fetch_philippines_fuel_prices() -> tuple[SourceResponse, datetime]:
    return _fetch_source_page(SOURCE_URL)


def _visible_text(html: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(html)
    return " ".join(parser.parts)


def _product_section(text: str, product: str) -> str | None:
    heading = re.compile(
        rf"\b(?:Philippines\s+)?{product}\s+prices?\b", re.IGNORECASE
    )
    match = heading.search(text)
    if not match:
        return None
    next_heading = re.search(
        r"\b(?:Philippines\s+)?(?:gasoline|diesel|LPG|kerosene)\s+prices?\b",
        text[match.end() :],
        re.IGNORECASE,
    )
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.start() : end]


def _parse_date(section: str) -> date:
    match = re.search(_DATE_TOKEN, section, re.IGNORECASE)
    if not match:
        raise ValueError("Effective date is missing or invalid.")
    token = re.sub(r"\s+", " ", match.group(0)).strip()
    for date_format in _DATE_FORMATS:
        try:
            return datetime.strptime(token, date_format).date()
        except ValueError:
            continue
    raise ValueError("Effective date is missing or invalid.")


def _parse_php_price(section: str) -> Decimal:
    match = re.search(
        r"\bPHP\b\s*(?:/\s*lit(?:er|re)?|per\s+lit(?:er|re))?\s*[:=]?\s*"
        r"([+-]?(?:\d+(?:[.,]\d+)?|NaN|Infinity))\b",
        section,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError("PHP price per liter is missing or invalid.")
    token = match.group(1)
    if "," in token and "." not in token:
        token = token.replace(",", ".")
    else:
        token = token.replace(",", "")
    try:
        price = Decimal(token)
    except InvalidOperation:
        raise ValueError("PHP price per liter is malformed.") from None
    if not price.is_finite() or price <= 0:
        raise ValueError("PHP price per liter must be finite and positive.")
    return price


_NUMBER_TOKEN = r"[+-]?(?:\d+(?:[.,]\d+)?|NaN|Infinity)"


def _decimal_price(token: str) -> Decimal:
    normalized = token.strip()
    if "," in normalized and "." not in normalized:
        normalized = normalized.replace(",", ".")
    else:
        normalized = normalized.replace(",", "")
    try:
        price = Decimal(normalized)
    except InvalidOperation:
        raise ValueError("Current PHP price per liter is malformed.") from None
    if not price.is_finite() or price <= 0:
        raise ValueError("Current PHP price per liter must be finite and positive.")
    return price


def _single_price(candidates: list[str], *, source: str) -> Decimal:
    prices = {_decimal_price(token) for token in candidates}
    if not prices:
        raise ValueError(f"PHP price per liter is missing or invalid in {source}.")
    if len(prices) != 1:
        raise ValueError(f"Ambiguous conflicting current PHP/Liter values in {source}.")
    return prices.pop()


def _cell_numbers(cell: str) -> list[str]:
    return re.findall(rf"(?<![\w.])({_NUMBER_TOKEN})(?![\w.])", cell, re.IGNORECASE)


def _parse_product_table_price(html: str) -> Decimal | None:
    parser = _TableTextParser()
    parser.feed(html)
    candidates: list[str] = []

    for table in parser.tables:
        normalized_rows = [[" ".join(cell.split()) for cell in row] for row in table]
        table_text = " ".join(cell for row in normalized_rows for cell in row).casefold()

        # Explicit current-price field labeled with its PHP/Liter unit.
        if "current price" in table_text and re.search(
            r"price\s*\(\s*php\s*/\s*lit(?:er|re)\s*\)", table_text, re.IGNORECASE
        ):
            for row in normalized_rows:
                row_text = " ".join(row)
                label_index = next(
                    (
                        index
                        for index, cell in enumerate(row)
                        if re.search(
                            r"price\s*\(\s*php\s*/\s*lit(?:er|re)\s*\)",
                            cell,
                            re.IGNORECASE,
                        )
                    ),
                    None,
                )
                if label_index is not None:
                    candidates.extend(
                        token
                        for index, cell in enumerate(row)
                        if index != label_index
                        for token in _cell_numbers(cell)
                    )
                    candidates.extend(
                        re.findall(
                            rf"price\s*\(\s*php\s*/\s*lit(?:er|re)\s*\)\s*[:=]?\s*({_NUMBER_TOKEN})",
                            row_text,
                            re.IGNORECASE,
                        )
                    )

        # Currency table: use the PHP row at the explicitly labeled Liter column.
        liter_indexes = {
            index
            for row in normalized_rows
            for index, cell in enumerate(row)
            if re.fullmatch(
                r"(?:price\s*)?\(?\s*(?:php\s*/\s*)?lit(?:er|re)\s*\)?",
                cell,
                re.IGNORECASE,
            )
        }
        if liter_indexes:
            for row in normalized_rows:
                php_index = next(
                    (index for index, cell in enumerate(row) if cell.strip().upper() == "PHP"),
                    None,
                )
                if php_index is None:
                    continue
                for liter_index in liter_indexes:
                    if liter_index < len(row) and liter_index != php_index:
                        candidates.extend(_cell_numbers(row[liter_index]))

    return _single_price(candidates, source="semantic table") if candidates else None


def _parse_current_price_text(html: str) -> Decimal:
    text = _visible_text(html)
    patterns = (
        rf"\bcurrent\s+price\b.{{0,180}}?\bPHP\b\s*({_NUMBER_TOKEN})\s*(?:per\s+)?lit(?:er|re)\b",
        rf"\bcurrent\s+price\b.{{0,120}}?\bprice\s*\(\s*PHP\s*/\s*lit(?:er|re)\s*\)\s*[:=]?\s*({_NUMBER_TOKEN})",
        rf"\bcurrent\s+price\b\s*[:=]?\s*({_NUMBER_TOKEN}).{{0,80}}?\bprice\s*\(\s*PHP\s*/\s*lit(?:er|re)\s*\)",
        rf"\bcurrent\s+price\b.{{0,80}}?\bPHP\b\s*({_NUMBER_TOKEN}).{{0,80}}?\bprice\s*\(\s*PHP\s*/\s*lit(?:er|re)\s*\)",
    )
    candidates = [
        match.group(1)
        for pattern in patterns
        for match in re.finditer(pattern, text, re.IGNORECASE)
    ]
    return _single_price(candidates, source="current-price narrative")


def _parse_product_php_price(html: str) -> Decimal:
    table_price = _parse_product_table_price(html)
    if table_price is not None:
        return table_price
    return _parse_current_price_text(html)


def parse_philippines_fuel_prices(
    html: str, *, retrieved_at: datetime | None = None
) -> dict[str, ProductResult]:
    retrieved_at = retrieved_at or timezone.now()
    if timezone.is_naive(retrieved_at):
        retrieved_at = timezone.make_aware(retrieved_at)
    text = _visible_text(html)
    results: dict[str, ProductResult] = {}

    for fuel_type in SUPPORTED_PRODUCTS:
        try:
            section = _product_section(text, fuel_type)
            if section is None:
                raise ValueError(f"Explicit {fuel_type.lower()} section was not found.")
            effective_date = _parse_date(section)
            effective_at = timezone.make_aware(
                datetime.combine(effective_date, time.min),
                timezone.get_current_timezone(),
            )
            if effective_at > retrieved_at:
                raise ValueError("Effective date is in the future.")
            observation = ExternalFuelPriceObservation(
                fuel_type=fuel_type,
                price_per_liter=_parse_php_price(section),
                effective_at=effective_at,
                retrieved_at=retrieved_at,
            )
            results[fuel_type] = ProductResult(
                fuel_type=fuel_type,
                status="EXISTING",
                reason="VALIDATED_NOT_YET_PERSISTED",
                observation=observation,
            )
        except (ValueError, OverflowError) as exc:
            results[fuel_type] = ProductResult(
                fuel_type=fuel_type, status="FAILED", reason=str(exc)
            )
    return results


def parse_product_page(
    response: SourceResponse,
    fuel_type: str,
    *,
    retrieved_at: datetime,
) -> ProductResult:
    if fuel_type not in SUPPORTED_PRODUCTS:
        return ProductResult(fuel_type, "FAILED", "Unsupported product identity.")
    if response.classification != "NORMAL_PRICE_PAGE":
        missing = ", ".join(response.missing_labels) or "normal public price content"
        return ProductResult(
            fuel_type,
            "FAILED",
            f"SOURCE_UNAVAILABLE: {response.classification}; missing {missing}.",
        )
    if timezone.is_naive(retrieved_at):
        retrieved_at = timezone.make_aware(retrieved_at)
    try:
        section = _product_section(_visible_text(response.body), fuel_type)
        if section is None:
            raise ValueError(f"Explicit {fuel_type.lower()} section was not found.")
        effective_date = _parse_date(f"{response.title or ''} {section}")
        effective_at = timezone.make_aware(
            datetime.combine(effective_date, time.min),
            timezone.get_current_timezone(),
        )
        if effective_at > retrieved_at:
            raise ValueError("Effective date is in the future.")
        observation = ExternalFuelPriceObservation(
            fuel_type=fuel_type,
            price_per_liter=_parse_product_php_price(response.body),
            effective_at=effective_at,
            retrieved_at=retrieved_at,
        )
        return ProductResult(
            fuel_type,
            "EXISTING",
            "VALIDATED_PRODUCT_FALLBACK_NOT_YET_PERSISTED",
            observation,
        )
    except (ValueError, OverflowError) as exc:
        return ProductResult(fuel_type, "FAILED", str(exc))


def select_newest_observation(
    summary: ProductResult,
    fallback: ProductResult,
) -> ProductResult:
    if summary.observation is None:
        return fallback
    if fallback.observation is None:
        return summary
    summary_date = summary.observation.effective_at
    fallback_date = fallback.observation.effective_at
    if summary_date == fallback_date:
        if summary.observation.price_per_liter != fallback.observation.price_per_liter:
            return ProductResult(
                summary.fuel_type,
                "FAILED",
                "SOURCE_DATE_CONFLICT: same effective date has different PHP/L values.",
            )
        return summary
    selected = summary if summary_date > fallback_date else fallback
    source = "SUMMARY" if selected is summary else "PRODUCT_FALLBACK"
    return ProductResult(
        selected.fuel_type,
        selected.status,
        f"DATE_DISCREPANCY: selected newer {source} observation.",
        selected.observation,
        selected.record_id,
    )


def persist_external_fuel_prices(
    parsed: dict[str, ProductResult],
) -> dict[str, ProductResult]:
    persisted: dict[str, ProductResult] = {}
    for product_key, result in parsed.items():
        observation = result.observation
        if observation is None:
            persisted[product_key] = result
            continue

        with transaction.atomic():
            record, created = FuelPriceRecord.objects.get_or_create(
                fuel_type=observation.fuel_type,
                fuel_grade=observation.fuel_grade,
                currency=FuelPriceRecord.Currency.PHP,
                provider=observation.provider,
                source_mode=FuelPriceRecord.SourceMode.EXTERNAL_CACHED,
                effective_at=observation.effective_at,
                price_per_liter=observation.price_per_liter,
                defaults={"is_active": True},
            )
            if created:
                FuelPriceRecord.objects.filter(pk=record.pk).update(
                    retrieved_at=observation.retrieved_at
                )
        persisted[product_key] = ProductResult(
            fuel_type=observation.fuel_type,
            status="CREATED" if created else "EXISTING",
            reason=(
                "EXTERNAL_OBSERVATION_PERSISTED"
                if created
                else "EQUIVALENT_OBSERVATION_EXISTS"
            ),
            observation=observation,
            record_id=record.pk,
        )
    return persisted


def refresh_philippines_fuel_prices() -> FuelPriceRefreshReport:
    try:
        summary_response, retrieved_at = fetch_philippines_fuel_prices()
    except FuelPriceFetchError as exc:
        return FuelPriceRefreshReport(
            products={
                fuel_type: ProductResult(fuel_type, "FAILED", str(exc))
                for fuel_type in SUPPORTED_PRODUCTS
            },
            fetch_error=str(exc),
            classification=exc.classification,
        )

    if summary_response.classification == "INTERSTITIAL_OR_CHALLENGE":
        reason = "SOURCE_UNAVAILABLE: INTERSTITIAL_OR_CHALLENGE."
        return FuelPriceRefreshReport(
            products={
                fuel_type: ProductResult(fuel_type, "FAILED", reason)
                for fuel_type in SUPPORTED_PRODUCTS
            },
            fetch_error=reason,
            responses=(summary_response,),
            classification=summary_response.classification,
        )

    parsed = parse_philippines_fuel_prices(
        summary_response.body, retrieved_at=retrieved_at
    )
    responses = [summary_response]
    for fuel_type in SUPPORTED_PRODUCTS:
        if parsed[fuel_type].observation is not None:
            continue
        try:
            fallback_response, fallback_retrieved_at = _fetch_source_page(
                PRODUCT_URLS[fuel_type], product=fuel_type
            )
            responses.append(fallback_response)
            fallback = parse_product_page(
                fallback_response,
                fuel_type,
                retrieved_at=fallback_retrieved_at,
            )
            parsed[fuel_type] = select_newest_observation(parsed[fuel_type], fallback)
        except FuelPriceFetchError as exc:
            parsed[fuel_type] = ProductResult(
                fuel_type,
                "FAILED",
                f"SOURCE_UNAVAILABLE: {exc.classification}; {exc}",
            )

    return FuelPriceRefreshReport(
        products=persist_external_fuel_prices(parsed),
        responses=tuple(responses),
        classification=summary_response.classification,
    )
