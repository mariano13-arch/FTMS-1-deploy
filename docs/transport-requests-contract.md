# Transport Requests contract

Transport Requests is the Sprint 4 operational vertical slice. It stores an inbound movement request, its planning window, optional manual vehicle allocation, workflow state, and immutable audit history in PostgreSQL. `READY_FOR_DISPATCH` is the handoff to future Driver Dispatch and Trip Lifecycle work; Sprint 4 does not create a Trip.

## Status workflow

| Current status | Allowed next status |
| --- | --- |
| `FOR_APPROVAL` | `APPROVED`, `REJECTED`, `NEEDS_MORE_DETAILS`, `CANCELLED` |
| `NEEDS_MORE_DETAILS` | `FOR_APPROVAL` through Resubmit, or `CANCELLED` |
| `APPROVED` | `READY_FOR_DISPATCH`, `CANCELLED` |
| `READY_FOR_DISPATCH` | `CANCELLED` |
| `REJECTED` | None |
| `CANCELLED` | None |

Request More Details requires a nonblank reason and records `REQUESTED_MORE_DETAILS`. Resubmit is explicit and records `RESUBMITTED`; editing never resubmits automatically. Rejection and cancellation also require notes. Approved and ready records cannot be directly edited by any role. Editing locks and rechecks the request inside one transaction; a workflow transition that wins the lock makes a stale edit fail with HTTP 409 without saving fields or an `EDITED` event. Every successful mutation appends an immutable `TransportRequestEvent` in the same transaction.

## Planning and allocation

`required_vehicle_type` is optional and uses the Fleet vehicle types. `estimated_duration_minutes` is 15–1440 minutes, defaults to 60, and defines a planning window from scheduled pickup through scheduled pickup plus duration. It is not route duration or ETA.

Vehicle assignment is manual. The server locks the request, then locks only the previous and selected vehicles in deterministic primary-key order before checking that the request is `APPROVED`, the vehicle is active, known capacity meets passenger count, an optional required type matches, and no active vehicle allocation overlaps. `APPROVED` and `READY_FOR_DISPATCH` requests with an assigned vehicle consume its schedule. The overlap rule is `existing_start < requested_end` and `existing_end > requested_start`. Conflicts return HTTP 409. Prepare for Dispatch repeats all checks in one transaction before the handoff.

Dispatch Queue means `APPROVED`, including both unassigned and assigned requests. `READY_FOR_DISPATCH` requests have already left that queue.

## Permissions

- Super Admin and Fleet Manager: view/create/edit eligible records, approve, reject, request more details, resubmit, manually assign/reassign, prepare for dispatch, cancel, and view history.
- Dispatcher: view/create, edit `FOR_APPROVAL` or `NEEDS_MORE_DETAILS`, resubmit, manually assign/reassign approved requests, prepare for dispatch, and view history. Dispatchers cannot approve, reject, request more details, or cancel.

## API

- `GET|POST /api/v1/transport-requests/`
- `GET|PATCH /api/v1/transport-requests/{id}/`
- `GET /api/v1/transport-requests/summary/`
- `GET /api/v1/transport-requests/calendar/?start=YYYY-MM-DD&end=YYYY-MM-DD`
- `POST /api/v1/transport-requests/{id}/approve/`
- `POST /api/v1/transport-requests/{id}/reject/`
- `POST /api/v1/transport-requests/{id}/request-more-details/`
- `POST /api/v1/transport-requests/{id}/resubmit/`
- `POST /api/v1/transport-requests/{id}/assign-vehicle/`
- `POST /api/v1/transport-requests/{id}/prepare-dispatch/`
- `POST /api/v1/transport-requests/{id}/cancel/`

The list supports pagination, search, ordering, comma-separated status values, priority, source system, request type, scheduled date, and `assignment=all|assigned|unassigned`. List rows omit full audit histories and expose only the latest real event marker; detail and action responses include the complete timeline.

Calendar ranges are validated and capped at 31 days. The default operational timezone is `Asia/Manila` (configurable with `DJANGO_TIME_ZONE`), so summary “today” counts and daily/weekly calendar grouping use Philippine local-date boundaries. Timestamps remain timezone-aware and PostgreSQL may store their instants in UTC; API datetimes remain ISO-8601. The endpoint excludes rejected and cancelled requests, calculates timezone-aware planning end times, and identifies real overlapping assigned-vehicle allocations. Unassigned requests are never labeled as vehicle conflicts. Weekly Calendar View keeps its header fixed and may scroll horizontally inside the calendar panel at narrow widths.

`source_system` identifies hotel, restaurant, manual staff, or other subsystem origins. A nonblank `external_reference` is unique within its source; duplicate submissions return HTTP 409.

## Current limitations

HRMS driver synchronization, driver assignment, OR-Tools recommendation, Google Routes and real ETA, Active Trips, Completed trips, safety monitoring, proof of service, fuel estimation, cost computation, and feedback are future work. No driver, distance, ETA, safety, cost, or trip records are fabricated in Sprint 4. This stabilization requires no new API key.

The shared desktop application shell supports expanded and icon-only mini-sidebar modes. Its local browser preference changes presentation only; module permissions, routes, and API behavior are unchanged. Main content, including Transport Requests and its internally scrolling weekly Calendar, expands into the available shell width. Active Trips and Completed remain future work, and this refinement requires no database migration.
