# Driver Receipts Phase 1 Report

## Purpose

Phase 1 creates the backend domain and driver API for driver-confirmed fuel and toll receipts. OCR is intentionally not implemented here; future OCR output must remain candidate data until the driver reviews, corrects, and submits confirmed values.

## Model

`TripExpenseReceipt` lives in `transport_requests` and records one operational receipt linked to a `DispatchAssignment`, authoritative `Driver`, and authoritative `Vehicle`.

Expense types:

- `FUEL`
- `TOLL`

Common fields:

- assignment, driver, vehicle
- transaction timestamp
- amount
- receipt number
- merchant/operator
- private receipt image
- confirmed/created/updated timestamps

Fuel fields:

- liters
- unit price
- fuel type
- fuel grade

Toll fields:

- toll plaza

No approval, reimbursement, paid, or accounting workflow is added in Phase 1.

## Authoritative Linkage

The API is scoped under a driver trip. The authenticated driver is resolved by `DriverAccess`; the assignment is selected only from assignments owned by that driver. The receipt driver and vehicle are derived server-side from the assignment. The mobile client cannot submit authoritative `driver`, `vehicle`, or `dispatch_assignment` values.

Eligible assignments must be:

- `TransportRequest.Status.READY_FOR_DISPATCH`
- accepted by the driver
- in execution status `EN_ROUTE_TO_PICKUP`, `AT_PICKUP`, `IN_TRANSIT`, `AT_DESTINATION`, or `COMPLETED`

These states represent active or completed trip execution and avoid accepting receipts for merely assigned but not yet accepted/released trips.

## Private Receipt Handling

Receipt uploads use multipart form data and accept JPEG/PNG only. The size limit is 5 MB, matching existing private document policy. API responses do not expose public media paths or filesystem paths. Receipt images are retrieved through authenticated driver-owned endpoints.

EXIF stripping: DEFERRED. The current backend has no existing image-rewrite dependency or safe EXIF-stripping pattern. This should be added before production camera rollout if a dependency such as Pillow is approved.

## API Endpoints

- `POST /api/v1/driver-trips/<trip_id>/receipts/`
- `GET /api/v1/driver-trips/<trip_id>/receipts/`
- `GET /api/v1/driver-receipts/<receipt_id>/`
- `GET /api/v1/driver-receipts/<receipt_id>/image/`

All endpoints require driver authentication and ownership.

## Validations

- amount must be positive
- transaction date/time cannot be in the future
- fuel liters must be positive when supplied
- fuel unit price must be positive when supplied
- fuel grade must match fuel type
- toll receipts reject fuel-only fields
- receipt image must be JPEG or PNG and at most 5 MB
- driver, vehicle, assignment, and confirmed timestamp are server-owned

If fuel liters and unit price are supplied, amount is validated against their product with a small currency tolerance. The backend does not overwrite amount.

## Duplicate Behavior

Phase 1 returns a non-blocking `duplicate_warning` when a same-assignment same-type receipt has the same receipt number, or the same amount and transaction timestamp. It does not reject duplicates because repeated legitimate toll/fuel transactions are possible.

## Security And Privacy

Receipt images are private operational/financial data. Raw OCR text is not stored because OCR is not implemented. Do not log receipt contents or put raw OCR output in centralized audit logs in later phases.

## Focused Test Evidence

Focused tests are in `backend/transport_requests/tests/test_driver_receipts.py`.

## Deferred Work

- Driver Mobile camera/gallery/manual receipt UI
- OCR candidate extraction endpoint
- EXIF stripping
- staff review/approval or reimbursement workflow
- centralized AuditEvent hooks for sanitized receipt submission events
