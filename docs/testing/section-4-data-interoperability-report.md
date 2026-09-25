# Section 4 Data Interoperability Audit

Date: 2026-09-24  
Scope: safe reference/master import data plus the existing trusted JSON source-system transport ingestion. This section intentionally does not add manual CSV/Excel transport-request creation.

## Verdicts

| Area | Status | Evidence |
| --- | --- | --- |
| CSV Import | PASS | `POST /api/v1/vehicles/partner-fuel-prices/import/` accepts UTF-8 CSV fuel-price reference data, trims values, validates required headers, rejects unknown/duplicate headers, rejects unsupported types, reports row errors, and returns `total_rows`, `accepted_rows`, `rejected_rows`, `errors`, and `duration_ms`. |
| Excel Import | PASS | Same endpoint accepts genuine `.xlsx` workbooks by reading the first worksheet from OOXML, rejects corrupted workbooks, rejects formula cells, ignores blank rows, validates headers/types/enums, and applies the same summary contract. |
| JSON Import | PASS | Existing trusted transport source endpoint `POST /api/v1/integrations/transport-requests/` is authenticated with integration bearer credentials, binds the source system server-side, validates schema and source-specific payloads, is idempotent for equivalent replays, and returns `409` on conflicting replay. |
| Invalid File Detection | PASS | Automated tests cover unsupported extensions, empty files, non-UTF-8 CSV, missing/unknown headers, corrupt XLSX, invalid enum/reference values, wrong numeric types, duplicates, unsafe/formula-like values, and oversize files. |
| Bulk Upload | PASS | Automated test imports 1,000 CSV rows into the test database and asserts all rows are accepted with an integer `duration_ms` response. |
| Export Accuracy | PASS | Section 3 transport report exports are reused. Tests verify authorization, filters, row counts, CSV quoting of special characters, XLSX workbook structure, formula protection, PDF signature, and exclusion of private requester/contact/address fields. |

## Import Contract

Fuel-price reference imports use multipart form data:

```text
POST /api/v1/vehicles/partner-fuel-prices/import/
file=@sample-import.csv
```

Required headers:

```text
fuel_type,fuel_grade,price_per_liter,provider,source_mode,effective_at
```

Optional headers:

```text
currency,is_active
```

Rules:

- `fuel_type`: `GASOLINE` or `DIESEL`.
- `fuel_grade`: blank or one of the vehicle fuel-grade enum values compatible with the fuel type.
- `price_per_liter`: positive finite decimal.
- `provider`: required, max 160 characters.
- `source_mode`: `MANUAL` or `EXTERNAL_CACHED`.
- `effective_at`: timezone-aware ISO 8601 datetime.
- `currency`: `PHP` only.
- `is_active`: `true/false`, `1/0`, or `yes/no`.
- Formula-like values beginning with `=`, `+`, `-`, or `@` are rejected.
- `.xlsx` formulas are not executed; formula cells are rejected.
- Duplicate import keys are rejected after accepting the first valid row. Existing matching database rows are rejected as duplicates.
- Row-level validation is partial: valid rows are inserted; invalid rows are rejected and listed in `errors`. File-level validation failures return `400` before inserting rows.

Summary response:

```json
{
  "total_rows": 2,
  "accepted_rows": 2,
  "rejected_rows": 0,
  "errors": [],
  "duration_ms": 12
}
```

## Samples

- `docs/testing/samples/interoperability/sample-import.csv`
- `docs/testing/samples/interoperability/sample-import.xlsx`
- `docs/testing/samples/interoperability/sample-import.json`

The CSV/XLSX samples contain only synthetic fuel-price reference rows. The JSON sample is synthetic source-system transport request input for the authenticated integration endpoint.

## Validation

Commands run locally:

```text
docker compose build backend
docker compose run --rm -T backend python manage.py test --keepdb fleet.tests.test_fuel_price_imports transport_requests.tests.test_source_integration transport_requests.tests.test_reports
docker compose run --rm -T backend python manage.py check
docker compose run --rm -T backend ruff check fleet/fuel_price_imports.py fleet/views.py fleet/urls.py fleet/tests/test_fuel_price_imports.py transport_requests/tests/test_reports.py
cd frontend && npm run typecheck && npm run build
git diff --check
```

Results:

- Backend focused tests: PASS, 28 tests.
- Django system check: PASS.
- Ruff focused lint: PASS.
- Frontend typecheck: PASS.
- Frontend production build: PASS; Vite reported the existing large chunk-size warning.
- Diff whitespace check: PASS.
