# Section 3 Dashboard Validation Report

## Status Summary

1. Real-Time Dashboard: PASS
2. Dashboard Accuracy: PASS
3. Interactive Charts: PASS
4. Historical Reports: PASS
5. KPI Monitoring: PASS
6. Report Export: PASS

## Dashboard Auto-Refresh

- Frontend path: `frontend/src/features/dashboard/DashboardPage.tsx`
- API source: `GET /api/v1/dashboard/summary/`
- Backend path: `backend/transport_requests/dashboard.py`
- Mechanism: browser polling with `window.setInterval`
- Interval: 30 seconds
- Visibility behavior: polling re-fetches only when `document.visibilityState === "visible"`
- Refresh failure behavior: an error is recorded, but the last valid dashboard summary remains rendered
- No full page reload is required

## KPI Definitions

- Transport Request Status: current `TransportRequest.status` counts
- Dispatch Queue: `dispatch_board_summary` eligibility and blocker counts
- Active Trip Status: `DispatchAssignment.execution_status` excluding `COMPLETED`
- Completed Trips: `DispatchAssignment.completed_at` grouped by local date for the last 7 days
- Fleet State: vehicle active/inactive counts plus distinct currently assigned vehicles
- Driver State: driver employment status counts plus distinct currently assigned drivers
- Inspection Results: today's `VehicleInspection.result` counts
- Maintenance Activity: current non-completed/non-cancelled maintenance plus completed today
- Operational Safety Events: today's `DriverSafetyEvent` records excluding simulated telemetry provenance
- Geofence Activity: today's persisted `GeofenceEvent` entries/exits/restricted entries
- Device / Telemetry Coverage: device registry, active binding, and latest genuine persisted telemetry
- Fuel Evidence Coverage: fuel-rate resolver evidence basis for active vehicles
- Active SOS: active `VehicleEmergencySOS` records

## Validation Methodology

Focused backend tests seed deterministic database records and compare API values against exact expected counts, status filters, date boundaries, pagination, and empty-state behavior.

Focused frontend tests verify dashboard rendering, 30-second automatic re-fetch, refresh failure handling, report filtering, report drill-down links, and export calls preserving current filters.

## Chart Filters And Drill-Down

- Dashboard chart cards open factual detail drawers.
- Dashboard drawer drill-down link maps each aggregate to its existing operational module via `module_url`.
- Transport Request Summary supports date range, source, request type, status, priority, pagination, and row drill-down to the request detail page.
- Report visual breakdowns update when filters change because they are derived from the filtered backend dataset.

## Historical Report Categories

Available report categories:

- Transport Request Summary
- Dispatch & Trip Execution
- Fleet Assignment Summary
- Inspection & Maintenance
- Safety, Geofence & SOS Activity
- Device & Telemetry Availability
- Fuel Predictions & Reference Data
- Driver Safety Calibration

Evaluator examples:

- Transport/trip history: Transport Request Summary and Dispatch & Trip Execution
- Driver safety/history: Safety, Geofence & SOS Activity and Driver Safety Calibration
- Fuel or maintenance history: Fuel Predictions & Reference Data and Inspection & Maintenance

## Export Formats

Evaluator-ready transport request exports:

- CSV: `/api/v1/reports/transport-requests/csv/`
- Excel: `/api/v1/reports/transport-requests/xlsx/`
- PDF: `/api/v1/reports/transport-requests/pdf/`

All three use the same report filters, require staff access plus `REPORTS.VIEW` and `REPORTS.EXPORT`, exclude private requester/contact/address fields, handle empty result sets, and sanitize spreadsheet formula prefixes in exported text cells.

## Focused Test Results

- Backend dashboard/report tests: `transport_requests.tests.test_reports transport_requests.tests.test_dashboard`
- Frontend dashboard/report tests: `src/features/dashboard/DashboardPage.test.tsx src/features/reports/ReportsPage.test.tsx`
- Django check: passed
- Ruff on changed backend files: passed after formatting cleanup

## Manual Demonstration Steps

1. Open `/dashboard`.
2. Show the "Last updated" timestamp and leave the page open; it re-fetches every 30 seconds without a page reload.
3. Compare one card, such as Transport Request Status, with `GET /api/v1/dashboard/summary/`.
4. Open `/reports/transport-requests`.
5. Apply a status or source filter and confirm the summary, breakdown, and table update.
6. Click a request row's `View` link to drill down to its operational detail page.
7. Set a custom historical date range.
8. Export the filtered report with `Export CSV`.
9. Export the same filtered report with `Export Excel`.
10. Export the same filtered report with `Export PDF`.

## Sample Evidence

Safe synthetic samples are stored under `docs/testing/samples/`:

- `sample-report.csv`
- `sample-report.xlsx`
- `sample-report.pdf`

They contain generated evaluator-safe rows only and do not contain production or personal data.
