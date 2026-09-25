# Driver Receipts Phase 3A OCR Report

## Scope

Phase 3A adds backend-only OCR candidate extraction for driver fuel and toll receipt images. OCR
preview is advisory: it does not create or update `TripExpenseReceipt`, and Driver Mobile is not
changed in this phase.

## Engine and dependencies

- Engine: Tesseract OCR, installed in the backend image with the Debian `tesseract-ocr` package.
- Python adapter: `pytesseract==0.3.13`.
- Image handling: `Pillow==11.3.0`.
- External OCR API: none.
- API key: none.

The backend remains based on `python:3.12-slim`, retains its GDAL dependency, and adds only the
Tesseract binary to the existing apt installation.

## Endpoint

`POST /api/v1/driver-trips/{trip_id}/receipts/ocr-preview/`

The endpoint requires a driver-authenticated session and an accepted, receipt-eligible assignment
owned by that driver. The request is `multipart/form-data` with:

- `receipt_image`: JPEG or PNG, maximum 5 MB.
- `expense_type`: `FUEL` or `TOLL`.

The same assignment scope used by confirmed receipt submission protects OCR preview. Driver,
vehicle, and unrelated assignment identifiers are not accepted.

## Processing and output

Pillow validates the image, applies EXIF orientation, converts it to grayscale, and limits only
excessively large dimensions. Processing uses a fresh metadata-free image in memory; neither the
source nor the processed image is persisted by the preview endpoint.

Tesseract output is normalized and parsed for labeled receipt values. The API returns common
candidates (`merchant_or_operator`, `transaction_at`, `transaction_date`, `amount`, and
`receipt_number`), fuel-only candidates (`liters`, `unit_price`, `fuel_type`, and `fuel_grade`),
or the toll-only `toll_plaza` candidate. Unknown values are `null`, and raw OCR text is never
returned.

Amounts require a recognized total label. Receipt numbers require a recognized identifier label.
Fuel type and grade mappings require explicit text. Ambiguous numeric dates are not guessed. A
recognized date without time is returned separately as `transaction_date`; no time or timezone is
invented.

## Privacy and failure behavior

Raw OCR text is transient. It is not stored in the database, receipt model, audit events, or logs.
Errors log only the fixed message `Receipt OCR processing failed`.

OCR engine failures and scans with no useful fields return null candidates plus a warning that
manual entry remains available. Invalid uploads return field-level validation errors. OCR preview
never submits a receipt, writes a fuel price, or creates an audit event.

## Test evidence

Focused tests cover driver ownership, fuel/toll preview, JPEG/PNG acceptance, unsupported,
oversized and corrupted files, parser behavior for Philippine currency totals, fuel quantity and
price, explicit fuel type/grade, toll data, labeled identifiers, conservative date handling,
absence of raw OCR output, no database/audit writes, and manual fallback.

Validation completed in the rebuilt backend image:

- Focused Phase 3A OCR tests: 12 passed.
- Phase 1 receipt regression tests: 7 passed.
- Combined focused regression: 19 passed.
- Django system check: no issues.
- Migration consistency: no changes detected.
- Tesseract binary: 5.5.0.
- Focused Ruff: passed.
- `git diff --check`: passed.

## Known limitations

Tesseract accuracy depends on focus, lighting, print quality, orientation, and receipt layout. The
parser intentionally ignores unlabeled or ambiguous values. English OCR is used in this phase;
confidence percentages are omitted because candidate-level confidence is not reliably associated.

## Phase 3B integration

Driver Mobile will send the selected image and expense type to the preview endpoint, populate only
the returned candidates into editable fields, and require the driver to review or correct them
before using the existing confirmed receipt submission endpoint.
