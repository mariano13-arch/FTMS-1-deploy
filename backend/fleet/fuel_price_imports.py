import csv
import io
import re
import time
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import PurePath
from xml.etree import ElementTree

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_naive

from fleet.models import FuelPriceRecord, Vehicle

REQUIRED_HEADERS = {
    "fuel_type",
    "fuel_grade",
    "price_per_liter",
    "provider",
    "source_mode",
    "effective_at",
}
OPTIONAL_HEADERS = {"currency", "is_active"}
ALLOWED_HEADERS = REQUIRED_HEADERS | OPTIONAL_HEADERS
MAX_IMPORT_BYTES = 1_000_000
FORMULA_PREFIXES = ("=", "+", "-", "@")
SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,180}$")
XLSX_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


class ImportFileError(ValueError):
    pass


@dataclass(frozen=True)
class ImportRow:
    number: int
    values: dict[str, str]


def import_fuel_prices(uploaded_file):
    started = time.perf_counter()
    name = _validated_filename(uploaded_file.name)
    content = uploaded_file.read()
    if not content:
        raise ImportFileError("Import file is empty.")
    if len(content) > MAX_IMPORT_BYTES:
        raise ImportFileError(f"Import file exceeds {MAX_IMPORT_BYTES} bytes.")

    suffix = PurePath(name).suffix.lower()
    if suffix == ".csv":
        rows = _read_csv(content)
    elif suffix == ".xlsx":
        rows = _read_xlsx(content)
    else:
        raise ImportFileError("Unsupported import file type. Use .csv or .xlsx.")

    if not rows:
        raise ImportFileError("Import file has no data rows.")

    records = []
    errors = []
    seen_keys = set()
    parsed_by_key = {}
    for row in rows:
        record, row_errors, key = _parse_record(row)
        if row_errors:
            errors.extend(row_errors)
            continue
        if key in seen_keys:
            errors.append(_row_error(row.number, "duplicate", "Duplicate fuel price row in file."))
            continue
        seen_keys.add(key)
        parsed_by_key[key] = row.number
        records.append(record)

    if records:
        existing_keys = _existing_keys(seen_keys)
        if existing_keys:
            records = [
                record
                for record in records
                if _record_key(record) not in existing_keys
            ]
            errors.extend(
                _row_error(row_number, "duplicate", "Fuel price row already exists.")
                for key, row_number in parsed_by_key.items()
                if key in existing_keys
            )

    with transaction.atomic():
        FuelPriceRecord.objects.bulk_create(records, batch_size=500)

    duration_ms = int((time.perf_counter() - started) * 1000)
    return {
        "total_rows": len(rows),
        "accepted_rows": len(records),
        "rejected_rows": len(rows) - len(records),
        "errors": sorted(errors, key=lambda item: (item["row"], item["field"])),
        "duration_ms": duration_ms,
    }


def _validated_filename(name):
    if not name or PurePath(name).name != name:
        raise ImportFileError("Import filename is not safe.")
    if "\x00" in name or not SAFE_FILENAME_RE.match(name):
        raise ImportFileError("Import filename is not safe.")
    return name


def _read_csv(content):
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportFileError("CSV import must be UTF-8 encoded.") from exc

    try:
        reader = csv.reader(io.StringIO(text), strict=True)
        raw_rows = list(reader)
    except csv.Error as exc:
        raise ImportFileError(f"Malformed CSV import: {exc}") from exc

    if not raw_rows or not any(value.strip() for value in raw_rows[0]):
        raise ImportFileError("Import file is missing headers.")
    headers = [_normalize_header(value) for value in raw_rows[0]]
    _validate_headers(headers)

    rows = []
    for index, values in enumerate(raw_rows[1:], start=2):
        if not any(str(value).strip() for value in values):
            continue
        padded = values + [""] * (len(headers) - len(values))
        rows.append(
            ImportRow(
                number=index,
                values=dict(zip(headers, (_trim(value) for value in padded), strict=False)),
            )
        )
    return rows


def _read_xlsx(content):
    try:
        workbook = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ImportFileError("XLSX import is not a valid workbook.") from exc
    with workbook:
        try:
            sheet_xml = workbook.read("xl/worksheets/sheet1.xml")
        except KeyError as exc:
            raise ImportFileError("XLSX import is missing the first worksheet.") from exc
        shared_strings = _shared_strings(workbook)
        try:
            root = ElementTree.fromstring(sheet_xml)
        except ElementTree.ParseError as exc:
            raise ImportFileError("XLSX first worksheet is corrupted.") from exc

    raw_rows = []
    for row in root.findall(".//main:sheetData/main:row", XLSX_NS):
        cells = {}
        for cell in row.findall("main:c", XLSX_NS):
            cells[_xlsx_column_index(cell.attrib.get("r", ""))] = _xlsx_cell_value(
                cell, shared_strings
            )
        if cells:
            raw_rows.append([cells.get(index, "") for index in range(max(cells) + 1)])

    raw_rows = [row for row in raw_rows if any(_trim(value) for value in row)]
    if not raw_rows:
        raise ImportFileError("Import file is empty.")
    headers = [_normalize_header(value) for value in raw_rows[0]]
    _validate_headers(headers)
    return [
        ImportRow(
            number=index,
            values=dict(zip(headers, (_trim(value) for value in values), strict=False)),
        )
        for index, values in enumerate(raw_rows[1:], start=2)
        if any(_trim(value) for value in values)
    ]


def _shared_strings(workbook):
    try:
        shared_xml = workbook.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ElementTree.fromstring(shared_xml)
    return [
        "".join(text.text or "" for text in item.findall(".//main:t", XLSX_NS))
        for item in root.findall("main:si", XLSX_NS)
    ]


def _xlsx_cell_value(cell, shared_strings):
    if cell.find("main:f", XLSX_NS) is not None:
        raise ImportFileError("XLSX formula cells are not supported.")
    value_type = cell.attrib.get("t")
    if value_type == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//main:t", XLSX_NS))
    value = cell.find("main:v", XLSX_NS)
    if value is None or value.text is None:
        return ""
    if value_type == "s":
        try:
            return shared_strings[int(value.text)]
        except (IndexError, ValueError) as exc:
            raise ImportFileError("XLSX shared string table is corrupted.") from exc
    return value.text


def _xlsx_column_index(cell_reference):
    letters = "".join(character for character in cell_reference if character.isalpha())
    if not letters:
        return 0
    index = 0
    for character in letters.upper():
        index = index * 26 + ord(character) - ord("A") + 1
    return index - 1


def _validate_headers(headers):
    duplicate_headers = sorted({header for header in headers if headers.count(header) > 1})
    if duplicate_headers:
        raise ImportFileError(f"Duplicate headers: {', '.join(duplicate_headers)}.")
    missing = sorted(REQUIRED_HEADERS - set(headers))
    unknown = sorted(set(headers) - ALLOWED_HEADERS)
    if missing:
        raise ImportFileError(f"Missing required headers: {', '.join(missing)}.")
    if unknown:
        raise ImportFileError(f"Unknown headers: {', '.join(unknown)}.")


def _parse_record(row):
    values = row.values
    errors = []
    for field, value in values.items():
        if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
            errors.append(_row_error(row.number, field, "Formula-like values are not supported."))

    fuel_type = values.get("fuel_type", "")
    fuel_grade = values.get("fuel_grade", "")
    price = _parse_price(values.get("price_per_liter", ""), row.number, errors)
    provider = values.get("provider", "")
    source_mode = values.get("source_mode", "")
    effective_at = _parse_effective_at(values.get("effective_at", ""), row.number, errors)
    currency = values.get("currency") or FuelPriceRecord.Currency.PHP
    is_active = _parse_bool(values.get("is_active", "true"), row.number, errors)

    if fuel_type not in FuelPriceRecord.FuelType.values:
        errors.append(_row_error(row.number, "fuel_type", "Unsupported fuel type."))
    if source_mode not in FuelPriceRecord.SourceMode.values:
        errors.append(_row_error(row.number, "source_mode", "Unsupported source mode."))
    if currency != FuelPriceRecord.Currency.PHP:
        errors.append(_row_error(row.number, "currency", "Only PHP currency is supported."))
    if not provider:
        errors.append(_row_error(row.number, "provider", "Provider is required."))
    if len(provider) > 160:
        errors.append(_row_error(row.number, "provider", "Provider is too long."))
    if fuel_grade and fuel_grade not in Vehicle.FuelGrade.values:
        errors.append(_row_error(row.number, "fuel_grade", "Unsupported fuel grade."))

    if errors:
        return None, errors, None

    record = FuelPriceRecord(
        fuel_type=fuel_type,
        fuel_grade=fuel_grade,
        price_per_liter=price,
        currency=currency,
        provider=provider,
        source_mode=source_mode,
        effective_at=effective_at,
        is_active=is_active,
    )
    try:
        record.full_clean(exclude=("retrieved_at",))
    except ValidationError as exc:
        for field, messages in exc.message_dict.items():
            for message in messages:
                errors.append(_row_error(row.number, field, str(message)))
    return record if not errors else None, errors, _record_key(record)


def _parse_price(value, row_number, errors):
    try:
        price = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        errors.append(_row_error(row_number, "price_per_liter", "Enter a positive finite price."))
        return Decimal("0")
    if not price.is_finite() or price <= 0:
        errors.append(_row_error(row_number, "price_per_liter", "Enter a positive finite price."))
    return price


def _parse_effective_at(value, row_number, errors):
    parsed = parse_datetime(str(value))
    if parsed is None or is_naive(parsed):
        errors.append(
            _row_error(row_number, "effective_at", "Enter a timezone-aware ISO datetime.")
        )
    return parsed


def _parse_bool(value, row_number, errors):
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    errors.append(_row_error(row_number, "is_active", "Enter true or false."))
    return True


def _record_key(record):
    return (
        record.fuel_type,
        record.fuel_grade,
        record.provider,
        record.source_mode,
        record.effective_at,
    )


def _existing_keys(keys):
    if not keys:
        return set()
    providers = {key[2] for key in keys}
    effective_values = {key[4] for key in keys}
    candidates = FuelPriceRecord.objects.filter(
        provider__in=providers,
        effective_at__in=effective_values,
    )
    return {_record_key(record) for record in candidates if _record_key(record) in keys}


def _normalize_header(value):
    return _trim(value).lower()


def _trim(value):
    return str(value or "").strip()


def _row_error(row, field, message):
    return {"row": row, "field": field, "message": message}
