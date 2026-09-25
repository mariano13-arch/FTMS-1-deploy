from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pytesseract
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import TripExpenseReceipt

MAX_OCR_IMAGE_DIMENSION = 4000


class InvalidReceiptImage(ValueError):
    pass


class ReceiptOcrError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReceiptOcrResult:
    candidates: dict[str, str | None]
    warnings: list[str]


def _prepare_image(uploaded_file):
    try:
        uploaded_file.seek(0)
        source = Image.open(uploaded_file)
        if source.format not in {"JPEG", "PNG"}:
            source.close()
            raise InvalidReceiptImage("Only JPEG and PNG receipt images are allowed.")
        source.verify()
        source.close()
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        image = ImageOps.exif_transpose(image)
        image.load()
    except InvalidReceiptImage:
        raise
    except (Image.DecompressionBombError, OSError, UnidentifiedImageError, ValueError) as error:
        raise InvalidReceiptImage("Receipt image is invalid or corrupted.") from error

    image = image.convert("L")
    if max(image.size) > MAX_OCR_IMAGE_DIMENSION:
        image.thumbnail((MAX_OCR_IMAGE_DIMENSION, MAX_OCR_IMAGE_DIMENSION))

    # Copying into a fresh image removes metadata before OCR processing.
    clean_image = Image.new("L", image.size, "white")
    clean_image.paste(image)
    image.close()
    return clean_image


def extract_receipt_text(uploaded_file) -> str:
    image = _prepare_image(uploaded_file)
    try:
        return pytesseract.image_to_string(image, lang="eng")
    except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError, OSError) as error:
        raise ReceiptOcrError("Receipt OCR processing failed.") from error
    finally:
        image.close()


def _lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def _decimal(value: str, decimal_places: int) -> str | None:
    try:
        number = Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None
    if number <= 0:
        return None
    return f"{number:.{decimal_places}f}"


def _labeled_value(lines: list[str], labels: str, value_pattern: str) -> str | None:
    pattern = re.compile(
        rf"\b(?:{labels})\b\s*(?:NO\.?|NUMBER|#|:|-)?\s*({value_pattern})",
        re.IGNORECASE,
    )
    for line in lines:
        match = pattern.search(line)
        if match:
            return match.group(1).strip(" .:-")
    return None


def _parse_amount(lines: list[str]) -> str | None:
    labels = r"GRAND\s+TOTAL|TOTAL\s+AMOUNT|AMOUNT\s+DUE|TOTAL"
    currency_number = r"(?:PHP|PHP\s*₱|₱|P)?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.\d{2})|[0-9]+\.\d{2})"
    pattern = re.compile(rf"\b(?:{labels})\b\s*[:=-]?\s*{currency_number}\b", re.IGNORECASE)
    for line in lines:
        match = pattern.search(line)
        if match:
            return _decimal(match.group(1), 2)
    return None


def _parse_date(lines: list[str]) -> tuple[str | None, str | None]:
    labeled = re.compile(
        r"\b(?:DATE|TRANSACTION\s+DATE|DATE/TIME)\b\s*[:=-]?\s*"
        r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})"
        r"(?:\s+(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?))?",
        re.IGNORECASE,
    )
    for line in lines:
        match = labeled.search(line)
        if not match:
            continue
        date_token, time_token = match.groups()
        parsed_date = None
        if "-" in date_token:
            try:
                parsed_date = datetime.strptime(date_token, "%Y-%m-%d").date()
            except ValueError:
                continue
        else:
            first, second, year = (int(part) for part in date_token.split("/"))
            if first <= 12 and second <= 12 and first != second:
                return None, None
            date_format = "%m/%d/%Y" if first <= 12 else "%d/%m/%Y"
            try:
                parsed_date = datetime.strptime(date_token, date_format).date()
            except ValueError:
                continue
        if not time_token:
            return None, parsed_date.isoformat()
        normalized_time = re.sub(r"\s+", " ", time_token.upper()).strip()
        time_formats = (
            ("%I:%M %p", "%I:%M:%S %p")
            if "M" in normalized_time
            else ("%H:%M", "%H:%M:%S")
        )
        for time_format in time_formats:
            try:
                parsed_time = datetime.strptime(normalized_time, time_format).time()
                return datetime.combine(parsed_date, parsed_time).isoformat(), None
            except ValueError:
                continue
    return None, None


def _parse_merchant(lines: list[str]) -> str | None:
    value = _labeled_value(
        lines,
        r"MERCHANT|OPERATOR|STATION|FUEL\s+STATION|TOLL\s+OPERATOR",
        r"[A-Z0-9][A-Z0-9 &.'/-]{2,159}",
    )
    return value.title() if value and value.isupper() else value


def _parse_toll_plaza(lines: list[str]) -> str | None:
    value = _labeled_value(
        lines, r"TOLL\s+PLAZA|PLAZA", r"[A-Z0-9][A-Z0-9 &.'/-]{2,159}"
    )
    return value.title() if value and value.isupper() else value


def _parse_receipt_number(lines: list[str]) -> str | None:
    pattern = re.compile(
        r"\b(?:RECEIPT|OR|REFERENCE|REF|TRANSACTION)\s*"
        r"(?:NO\.?|NUMBER|#)\s*[:=-]?\s*([A-Z0-9][A-Z0-9/-]{1,79})\b",
        re.IGNORECASE,
    )
    for line in lines:
        match = pattern.search(line)
        if match:
            return match.group(1).strip(" .:-")
    return None


def _parse_fuel(lines: list[str]) -> dict[str, str | None]:
    liters = _labeled_value(lines, r"LITERS?|LTR", r"[0-9]+(?:[.,][0-9]{1,3})?")
    unit_price = _labeled_value(
        lines,
        r"PRICE\s*/\s*L|UNIT\s+PRICE|PRICE\s+PER\s+LITER",
        r"(?:PHP|₱|P)?\s*[0-9]+(?:[.,][0-9]{1,4})?",
    )
    joined = "\n".join(lines).upper()
    grades = (
        ("PREMIUM_DIESEL", r"\bPREMIUM\s+DIESEL\b"),
        ("REGULAR_DIESEL", r"\bREGULAR\s+DIESEL\b"),
        ("UNLEADED_91", r"\bUNLEADED\s+91\b"),
        ("PREMIUM_95", r"\bPREMIUM\s+95\b"),
        ("PREMIUM_97", r"\bPREMIUM\s+97\b"),
    )
    fuel_grade = next((value for value, pattern in grades if re.search(pattern, joined)), None)
    fuel_type = None
    if re.search(r"\bDIESEL\b", joined):
        fuel_type = "DIESEL"
    elif re.search(r"\bGASOLINE\b", joined):
        fuel_type = "GASOLINE"
    return {
        "liters": _decimal(liters.replace(",", "."), 3) if liters else None,
        "unit_price": (
            _decimal(
                re.sub(r"^(?:PHP|₱|P)\s*", "", unit_price, flags=re.IGNORECASE).replace(
                    ",", "."
                ),
                4,
            )
            if unit_price
            else None
        ),
        "fuel_type": fuel_type,
        "fuel_grade": fuel_grade,
    }


def parse_receipt_candidates(text: str, expense_type: str) -> ReceiptOcrResult:
    lines = _lines(text)
    transaction_at, transaction_date = _parse_date(lines)
    candidates: dict[str, str | None] = {
        "merchant_or_operator": _parse_merchant(lines),
        "transaction_at": transaction_at,
        "transaction_date": transaction_date,
        "amount": _parse_amount(lines),
        "receipt_number": _parse_receipt_number(lines),
    }
    if expense_type == TripExpenseReceipt.ExpenseType.FUEL:
        candidates.update(_parse_fuel(lines))
    else:
        candidates["toll_plaza"] = _parse_toll_plaza(lines)

    warnings = []
    if candidates["amount"] is None:
        warnings.append("No total amount could be identified.")
    if candidates["transaction_at"] is None and candidates["transaction_date"] is None:
        warnings.append("Receipt date could not be determined.")
    if expense_type == TripExpenseReceipt.ExpenseType.FUEL and candidates["liters"] is None:
        warnings.append("Fuel quantity was not identified.")
    if not any(value is not None for value in candidates.values()):
        warnings = ["No receipt fields could be identified. Enter the values manually."]
    return ReceiptOcrResult(candidates=candidates, warnings=warnings)


def analyze_receipt(uploaded_file, expense_type: str) -> ReceiptOcrResult:
    text = extract_receipt_text(uploaded_file)
    if not text.strip():
        return parse_receipt_candidates("", expense_type)
    return parse_receipt_candidates(text, expense_type)
