# FTMS Current API Reference

This reference describes the implemented API on 2026-09-24. It is an evaluator-oriented summary of the Django URL configuration, views, serializers, and P2-A permission matrix—not a future-state design. Historical sprint contracts remain in `docs/api-contracts.md`; where they differ, this current reference governs.

Base URL examples use `http://localhost:8000`. JSON is used unless a file upload or CSV response is noted.

## Authentication and authorization

### Web staff

Web staff use Django session cookies through `StaffSessionAuthentication`. Obtain a CSRF token from `GET /api/v1/auth/csrf/`; all unsafe session-authenticated methods require the cookie and `X-CSRFToken` header. Login establishes one authoritative browser session per user, with idle and absolute expiry. A second completed login replaces the first session.

Enabled 2FA changes login into a password stage followed by `POST /api/v1/auth/2fa/verify/`. Authorization is deny-by-default through persisted `RolePermission` entries using `MODULE.ACTION` capabilities. Current staff roles are Fleet Admin, Fleet Manager, Dispatcher, and Fleet Staff.

### Driver Mobile

Driver Mobile uses a separate Django session login under `/api/v1/driver-auth/`. The identity must be an active non-staff user linked to a driver record. Driver-trip queries and actions are restricted to that driver's own assignments. Driver identity is not a staff role and cannot use staff APIs.

### Source subsystem integration

HMS, RMS, and supply-chain integrations use `Authorization: Bearer <key_identifier.secret>`. Credentials identify an active `IntegrationClient`, determine `source_system`, and are stored hashed. They are not staff sessions.

### Telemetry/device ingestion

The current `POST /api/v1/telemetry/` endpoint has no HTTP authentication and validates a registered, actively paired `device_id`. `POST /api/v1/sos/` is also currently unauthenticated and validates a registered device. This is the actual current mechanism, not a recommendation. Device registration and pairing administration require staff sessions and `DEVICES` capabilities.

## Common response conventions

- `400 Bad Request`: serializer, strict-field, filter, or workflow validation failed.
- `401 Unauthorized`: no valid session/integration credential, expired/replaced session, or invalid login.
- `403 Forbidden`: authenticated identity lacks the required capability; CSRF failures also use 403.
- `404 Not Found`: an authorized request targeted an unknown or out-of-scope resource.
- `409 Conflict`: supported idempotency key was reused with different data, or current workflow/allocation state conflicts.
- `429 Too Many Requests`: login, 2FA verification, or password-reset request throttling.

Factual examples:

```jsonc
// 400 — invalid telemetry schema
{"schema_version":["Only schema_version 1.0, 1.1, and 1.2 are supported."]}

// 401 — unauthenticated staff request
{"detail":"Authentication credentials were not provided."}

// 403 — staff transport creation is intentionally denied
{"detail":"Transport Request creation requires a trusted HMS, RMS, or supply-chain integration identity."}

// 200 — identical source retry is idempotent
{"external_reference":"HMS-2026-001","status":"RECEIVED"}

// 409 — same source reference, conflicting content
{"detail":"This source reference already exists with different request data."}
```

Errors can contain a string `detail`, field-to-message arrays, or a workflow-specific object. Clients should use the HTTP status as the primary classification.

## Endpoint reference

In the tables, `Staff + X.Y` means a valid staff session plus the named P2-A capability. `Staff` alone applies to self-service/per-user endpoints.

### Health, staff authentication, sessions, and 2FA

| Method | Path | Authentication / capability | Purpose and contract notes |
|---|---|---|---|
| GET | `/api/health/` | Public | Database-backed readiness; 200 `ok`, 503 when database is unavailable. |
| GET | `/api/v1/auth/csrf/` | Public | Sets CSRF cookie and returns masked `csrf_token`. |
| POST | `/api/v1/auth/login/` | Public + CSRF; throttled | Strict `username`, `password`; returns user/session or opaque 2FA challenge. |
| POST | `/api/v1/auth/2fa/verify/` | Public + CSRF; throttled | `challenge_token`, `method` (`totp`/`recovery`), `code`; establishes session. |
| GET | `/api/v1/auth/me/` | Staff | Current user, role, and capabilities. |
| POST | `/api/v1/auth/logout/` | Staff + CSRF | Ends authoritative session; 204. |
| POST | `/api/v1/auth/activity/` | Staff + CSRF | Empty body; records meaningful activity; 204. |
| GET/POST/POST | `/api/v1/auth/2fa/status/`, `setup/`, `confirm/` | Staff; POSTs require CSRF | Inspect, start, and confirm authenticator enrollment. Confirmation returns one-time recovery codes. |
| POST | `/api/v1/auth/2fa/disable/` | Staff + CSRF | Requires current password plus TOTP or unused recovery code. |

### Password recovery and password change

| Method | Path | Authentication / capability | Purpose and contract notes |
|---|---|---|---|
| POST | `/api/v1/auth/forgot-password/` | Public + CSRF; throttled | `email`; always returns the same generic 200 response for validly formed known/unknown addresses. |
| POST | `/api/v1/auth/reset-password/` | Public + CSRF | `uid`, expiring single-use `token`, `new_password`, `confirm_password`; validators apply and sessions are revoked. |
| POST | `/api/v1/auth/change-password/` | Staff + CSRF | `current_password`, new password and confirmation; successful change logs the user out. |
| POST | `/api/v1/auth/staff/setup-password/` | Public + CSRF | One-time invitation setup for eligible staff with no usable password. |

### Per-user notifications

All results are scoped to `request.user`; one staff user cannot read or mark another user's notifications.

| Method | Path | Authentication | Purpose |
|---|---|---|---|
| GET | `/api/v1/auth/notifications/` | Staff | Paginated list; `unread_only`, `page`, `page_size` (max 50). |
| GET | `/api/v1/auth/notifications/unread-count/` | Staff | Current unread count. |
| POST | `/api/v1/auth/notifications/{id}/read/` | Staff + CSRF | Idempotently marks owned notification read. |
| POST | `/api/v1/auth/notifications/mark-all-read/` | Staff + CSRF | Marks all owned unread notifications and returns `updated`. |

### Users, roles, and permissions

| Method | Path | Capability | Purpose |
|---|---|---|---|
| GET/POST | `/api/v1/auth/staff/` | `USERS_ACCESS.VIEW_USERS` / `CREATE_USER` | List sanitized managed staff or create invitation-based account. Direct password setting is rejected. |
| PATCH | `/api/v1/auth/staff/{user_id}/role/` | `USERS_ACCESS.ASSIGN_ROLE` | Assign supported staff role. |
| PATCH | `/api/v1/auth/staff/{user_id}/status/` | `USERS_ACCESS.CHANGE_USER_STATUS` | Activate/deactivate managed staff. |
| POST | `/api/v1/auth/staff/{user_id}/resend-invitation/` | `USERS_ACCESS.EDIT_USER` | Resend setup invitation to eligible pending account. |
| GET | `/api/v1/auth/role-permissions/` | `USERS_ACCESS.MANAGE_ROLE_PERMISSIONS` | Return valid modules/actions, roles, and current matrix. |
| PUT | `/api/v1/auth/role-permissions/{role}/` | `USERS_ACCESS.MANAGE_ROLE_PERMISSIONS` | Atomically replace a managed role's permission entries. |

### Source-system transport ingestion

| Method | Path | Authentication | Purpose and important fields |
|---|---|---|---|
| POST | `/api/v1/integrations/transport-requests/` | Integration bearer | Create from source-owned `external_reference`. Core fields include type/category, requester, pickup/destination coordinates, schedule, capacity/load requirements, priority, notes, and optional flight context. `source_system` comes from the credential. |
| GET | `/api/v1/integrations/transport-requests/{external_reference}/` | Integration bearer | Poll source-scoped request/workflow result, execution status, completion timestamp, rejection note, and delivery state. |

The uniqueness key is `(source_system, external_reference)`. An identical retry returns 200 with the existing result; initial creation returns 201; conflicting reuse returns 409. Completion results are pollable. A durable outbox seam exists, but no source callback contract or callback delivery worker is currently configured; do not claim callback push.

### Staff transport requests and dispatch

Normal requests originate from trusted source integrations. Staff `POST /api/v1/transport-requests/` is intentionally denied.

| Method | Path | Capability | Purpose / notable fields |
|---|---|---|---|
| GET | `/api/v1/transport-requests/` | `TRANSPORT_REQUESTS.VIEW` | Paginated list. Filters: search, status, priority, source, type, scheduled date, assignment, ordering. |
| GET/PATCH | `/api/v1/transport-requests/{uuid}/` | `VIEW` / `EDIT` | Detail/event history; edits only while workflow state remains editable, otherwise 409. |
| GET | `/api/v1/transport-requests/summary/`, `calendar/` | `TRANSPORT_REQUESTS.VIEW` | Operational counts and date-window calendar. |
| GET | `/api/v1/transport-requests/{uuid}/route/` | `TRANSPORT_REQUESTS.VIEW` | TomTom route result. Provider failure does not fabricate a straight-line route. |
| POST/GET | `/api/v1/transport-requests/places/suggest/`, `/places/details/{type}/{place_id}/` | `TRANSPORT_REQUESTS.VIEW` | TomTom place search using a client session UUID; configuration/provider failures are explicit. |
| POST | `/api/v1/transport-requests/{uuid}/flight/refresh/` | `TRANSPORT_REQUESTS.EDIT` plus current operator restriction | Refresh airport-pickup flight context; unavailable/configuration states remain explicit. |
| POST | `/{uuid}/approve/`, `reject/`, `request-more-details/`, `resubmit/`, `prepare-dispatch/`, `cancel/` | Matching `TRANSPORT_REQUESTS` action | Workflow transition with `note`; invalid state/allocation can return 409. Prefix is `/api/v1/transport-requests`. |
| GET | `/api/v1/transport-requests/dispatch-board/` | `DISPATCH_BOARD.VIEW` | Dispatch board and factual assignment summary. |
| GET | `/api/v1/transport-requests/dispatch-assignments/` | `DISPATCH_BOARD.VIEW` | Paginated assignment history/filtering. |
| POST | `/api/v1/transport-requests/dispatch-matrix/` | `DISPATCH_BOARD.VIEW` | Candidate matrix preview; does not confirm dispatch. |
| POST | `/dispatch-board/recommendations/`, `/recommendation-route/`, `/consolidation-recommendations/` | `DISPATCH_BOARD.GENERATE_RECOMMENDATION` | OR-Tools/candidate recommendation operations. Recommendations are advisory. |
| POST | `/dispatch-board/confirm/`, `/consolidations/confirm/`, `/consolidations/{id}/prepare/` | `DISPATCH_BOARD.DISPATCH` | Explicit human confirmation/preparation. |
| POST | `/api/v1/transport-requests/{uuid}/assign-vehicle/` | `DISPATCH_BOARD.ASSIGN` | Explicit vehicle assignment; allocation conflict may return 409. |

### Dashboard

| Method | Path | Capability | Purpose |
|---|---|---|---|
| GET | `/api/v1/dashboard/summary/` | `DASHBOARD.VIEW` | Operational KPIs assembled from authoritative request, dispatch, telemetry, inspection, and maintenance data. |

### Driver Mobile authentication and trips

| Method | Path | Authentication | Purpose |
|---|---|---|---|
| GET/POST | `/api/v1/driver-auth/csrf/`, `/login/` | Public; login CSRF-protected | Driver session bootstrap/login. |
| GET/POST | `/api/v1/driver-auth/me/`, `/logout/` | Driver | Current driver and logout. |
| POST | `/api/v1/driver-auth/setup-password/` | Public + CSRF | Expiring one-time driver setup token. |
| GET | `/api/v1/driver-trips/`, `/{trip_id}/` | Driver, own assignment | Assigned trip list/detail. |
| POST | `/api/v1/driver-trips/{trip_id}/accept/` | Driver, own assignment + CSRF | `confirmed_at`; accepts assigned trip. |
| GET | `/api/v1/driver-trips/{trip_id}/route/`, `/vehicle-position/` | Driver, own assignment | Active route and provenance-aware latest position. |
| POST | `/api/v1/driver-trips/{trip_id}/transition/` | Driver, own assignment + CSRF | Strict `action` from currently allowed execution actions. |

### Vehicles, inspections, maintenance, and drivers

| Methods and path family | Capability | Purpose |
|---|---|---|
| GET/POST `/api/v1/vehicles/`; GET/PATCH `/{device_id}/` | `VEHICLES.VIEW` / `CREATE` / `EDIT` | Paginated registry and mutable vehicle details. |
| POST `/{device_id}/deactivate/` or `reactivate/` | `VEHICLES.CHANGE_STATUS` | Idempotent lifecycle actions; no hard-delete endpoint. |
| GET `/{device_id}/photo/` | `VEHICLES.VIEW` | Vehicle image response. |
| GET `/inspection-definition/`; GET/POST `/{device_id}/inspections/`; GET/PATCH inspection detail | `INSPECTIONS.VIEW` / `CREATE` / `CORRECT` | Checklist definition and append/correction workflow. |
| GET/POST `/maintenance/`; GET `/maintenance/{id}/`; POST `/maintenance/{id}/transition/` | `MAINTENANCE.VIEW` / `CREATE`; transition requires `SCHEDULE`, `START`, `COMPLETE`, or `CANCEL` based on requested state | Maintenance records and controlled state transitions. |
| GET/POST vehicle document list; GET/PATCH detail; GET file | `VEHICLES.MANAGE_DOCUMENTS` | Vehicle document metadata/upload/download. |
| GET/POST `/api/v1/drivers/`; GET/PATCH `/{id}/`; GET photo | `DRIVERS.VIEW` / `CREATE` / `EDIT` | Driver registry. |
| GET/POST driver document list; GET detail/file | `DRIVERS.MANAGE_DOCUMENTS` | Driver document management. |

Lists generally return DRF `count`, `next`, `previous`, `results`; accepted filters and maximum page sizes are strict and family-specific.

### Live fleet, telemetry, geofences, devices, SOS, and alerts

| Method | Path | Authentication / capability | Purpose |
|---|---|---|---|
| POST | `/api/v1/telemetry/` | Current implementation: public | Strict versioned telemetry ingest; see contract below. |
| GET | `/api/v1/vehicles/{device_id}/latest-status/` | `LIVE_MAP.VIEW` | Deterministic latest event for known vehicle/device identity. |
| GET | `/api/v1/fleet-live/vehicles/` | `LIVE_MAP.VIEW` | Current fleet state with latest telemetry. |
| GET | `/api/v1/fleet-live/assignments/{id}/route/`, `/vehicles/{id}/trail/` | `LIVE_MAP.VIEW` | Active route and bounded trail. |
| GET | `/api/v1/fleet-live/safety-events/` | `DRIVER_SAFETY.VIEW` | Paginated driver-safety events. |
| GET | `/api/v1/fleet-live/geofence-events/` | `ALERTS_SOS.VIEW` | Paginated geofence events. |
| GET/POST | `/api/v1/fleet-live/geofences/` | `LIVE_MAP.VIEW` / `MANAGE_GEOFENCES` | List/create geofences. |
| GET/PATCH | `/api/v1/fleet-live/geofences/{uuid}/` | `LIVE_MAP.VIEW` / `MANAGE_GEOFENCES` | Read/update geofence. |
| GET | `/api/v1/alerts/active-attention/` | `ALERTS_SOS.VIEW` | Aggregated current attention feed. |
| GET/POST | `/api/v1/sos/` | GET: `ALERTS_SOS.VIEW`; POST: current implementation public | List active SOS or activate/clear using registered `device_id`. |
| GET/POST | `/api/v1/telemetry-devices/` | `DEVICES.VIEW` / `REGISTER` | Paginated registered devices or register ID. |
| GET | `/api/v1/telemetry-devices/{device_id}/` | `DEVICES.VIEW` | Device/binding detail. |
| POST | `/api/v1/telemetry-devices/{device_id}/pair/`, `/unpair/` | `DEVICES.PAIR` / `UNPAIR` | Controlled binding; conflicts use 409. |

#### Current telemetry contract

- Supported `schema_version`: `1.0`, `1.1`, `1.2`.
- Required identity/order fields: globally unique `event_id`, non-negative `sequence_number`, registered and actively paired `device_id`, timezone-aware `recorded_at`.
- Coordinates are WGS84 latitude/longitude. Version 1.0 implies `position_source=GNSS`; 1.1+ requires `GNSS` or `CELLULAR_LBS`. LBS requires positive `position_accuracy_m` and forbids GNSS speed.
- Version 1.2 adds `obd_source`. OBD values require a source; current values include physical and `SIMULATED_TEST` provenance. Simulated values must never be presented as physical OBD evidence.
- `driving_event` is required/non-null in 1.0 and nullable in later versions. OBD values (`rpm`, `coolant_c`, `engine_load_pct`) are nullable.
- Initial ingest returns 201; an identical `event_id` retry returns 200 with `duplicate=true`; different data under that ID returns 409.
- Latest selection uses recorded time with deterministic tie-breakers. Late older observations are retained but do not replace latest status.

MQTT accepts the same payload on `ftms/v1/telemetry/{device_id}` with topic/device matching. WebSocket staff live status is available at `/ws/v1/vehicles/{device_id}/status/` with authenticated snapshot/update events.

### Fuel analytics and operational settings

| Methods and paths | Capability | Purpose / truthfulness notes |
|---|---|---|
| GET `/api/v1/analytics/fuel/model-info/`, `/readiness/`, `/dashboard/`; POST `/predict/` | `FUEL_ANALYTICS.VIEW` | Model metadata, feature readiness, dashboard, and prediction. Predictions can be unavailable when required features are absent; estimates are not measured consumption. |
| GET `/api/v1/analytics/maintenance/model-info/`, `/readiness/`; POST `/predict/` | `MAINTENANCE.VIEW` | Maintenance model evidence. The current model is research-only/not production-ready where reported by these endpoints; mechanic confirmation remains required. |
| GET/POST `/api/v1/vehicles/partner-fuel-prices/` | `SYSTEM_SETTINGS.VIEW` / `MANAGE_PRICES` | Read current preferred-source setting/history or record a configured partner price. |
| GET/POST `/api/v1/vehicles/number-coding/rules/`, `/suspensions/`, `/exemptions/`; GET/PATCH `/{record_id}/` | `SYSTEM_SETTINGS.VIEW` / `MANAGE_NUMBER_CODING` | Number-coding operational rules, dated suspensions, and exemptions. |

### Reports and CSV exports

All JSON reports require `REPORTS.VIEW`. Every CSV endpoint additionally requires `REPORTS.EXPORT`; access to the JSON report alone does not authorize export.

| JSON report path | CSV path |
|---|---|
| `/api/v1/reports/transport-requests/` | `/api/v1/reports/transport-requests/csv/` |
| `/api/v1/reports/dispatch-trips/` | `/api/v1/reports/dispatch-trips/csv/` |
| `/api/v1/reports/fleet-assignments/` | `/api/v1/reports/fleet-assignments/{kind}/csv/` |
| `/api/v1/reports/safety-geofence/` | `/api/v1/reports/safety-geofence/{kind}/csv/` |
| `/api/v1/reports/device-telemetry/` | `/api/v1/reports/device-telemetry/{kind}/csv/` |
| `/api/v1/reports/inspection-maintenance/` | `/api/v1/reports/inspection-maintenance/{kind}/csv/` |
| `/api/v1/reports/fuel-reference/` | `/api/v1/reports/fuel-reference/{kind}/csv/` |
| `/api/v1/reports/driver-safety-calibration/` | No CSV route currently implemented |

Report filters are strict, family-specific, timezone-aware where applicable, and generally paginate detailed collections. CSV `kind` values are validated by each report view; unsupported kinds return a client error.

## Intentionally unsupported or incomplete behavior

- Source callback push is not implemented; integrations poll the result endpoint.
- General offline synchronization/conflict resolution is not implemented.
- Staff manual creation of normal transport requests is not supported.
- No OAuth or JWT authentication is implemented.
- No fabricated route is returned when TomTom route acquisition fails.
- Telemetry/SOS device-level HTTP authentication is not yet implemented; current validation is device identity/state validation only.
# Audit Logs

## `GET /api/v1/auth/audit-logs/`

Read-only centralized audit log endpoint for Fleet Admin users.

Filters:

- `occurred_after`
- `occurred_before`
- `actor`
- `action`
- `target_type`
- `outcome`
- `page`
- `page_size`

Ordering is `occurred_at` descending. There are no public create, update, or delete endpoints for audit events.

# Driver Receipts

Driver receipt endpoints are driver-authenticated and ownership-scoped.

## `POST /api/v1/driver-trips/{trip_id}/receipts/`

Create a driver-confirmed fuel or toll receipt for the authenticated driver's eligible assignment. Uses `multipart/form-data`.

Accepted fields:

- `expense_type`: `FUEL` or `TOLL`
- `transaction_at`
- `amount`
- `receipt_number`
- `merchant_or_operator`
- `receipt_image`: JPEG or PNG, max 5 MB
- `liters`, `unit_price`, `fuel_type`, `fuel_grade` for fuel receipts
- `toll_plaza` for toll receipts

The server derives driver and vehicle from the assignment. No OCR processing happens in this endpoint.

## `GET /api/v1/driver-trips/{trip_id}/receipts/`

List receipts for the authenticated driver's eligible assignment, newest first.

## `POST /api/v1/driver-trips/{trip_id}/receipts/ocr-preview/`

Analyze a JPEG or PNG receipt image (max 5 MB) for the authenticated driver's eligible
assignment. Uses `multipart/form-data` with `receipt_image` and `expense_type` (`FUEL` or
`TOLL`). The response contains transient, editable candidate values and safe warnings; it never
creates a receipt or returns raw OCR text.

Common candidates are `merchant_or_operator`, `transaction_at`, `transaction_date`, `amount`,
and `receipt_number`. Fuel previews may also include `liters`, `unit_price`, `fuel_type`, and
`fuel_grade`; toll previews may include `toll_plaza`. Unknown candidates are `null`. A date-only
result uses `transaction_date` because the service does not invent a transaction time or timezone.

OCR failure or a scan with no useful fields returns a successful manual-fallback response with
null candidates and warnings. Invalid, unsupported, corrupted, or oversized images return 400.

## `GET /api/v1/driver-receipts/{receipt_id}/`

Read one owned receipt.

## `GET /api/v1/driver-receipts/{receipt_id}/image/`

Return the private receipt image for an owned receipt. Public media URLs are not exposed.
