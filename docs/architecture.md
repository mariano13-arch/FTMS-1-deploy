# FTMS architecture

## Target architecture

FTMS uses a Django modular monolith. React communicates with Django over REST and
WebSocket. Django owns validation, application behavior, and all PostGIS access.

```text
React -> Django REST/WebSocket -> PostgreSQL 17 + PostGIS
                     |
                     +-> Redis/Channels and Celery

REST simulator -> shared ingestion service -> PostGIS
MQTT simulator -> Mosquitto -> Django MQTT ingestor -> shared ingestion service
                                             |-> PostGIS
                                             `-> Channels/Redis -> WebSocket -> React
```

## Component status

Implemented through Sprint 3:

- Minimal React page with a backend health state
- Django ASGI application and database-connected health endpoint
- PostgreSQL/PostGIS, Redis, Mosquitto, Celery, and local Compose configuration
- CI, tests, linting, and development documentation
- Minimal `fleet` and `telemetry` Django modules for a single simulated pilot vehicle
- Strict telemetry `1.0` REST ingestion with race-safe event ID idempotency
- Append-only PostGIS telemetry events and deterministic latest-status REST lookup
- REST and MQTT simulators, a dedicated reconnecting MQTT ingestor, and shared ingestion
- Commit-safe latest-only Channels/Redis broadcasts and vehicle WebSocket snapshots
- React reconnect with five-second REST fallback and one Leaflet/OpenStreetMap marker

Planned, not implemented:

- Driver, dispatch, route, and device-authentication features
- Celery business jobs and ETL workflows
- OR-Tools dispatch optimization and XGBoost predictive analytics
- LILYGO edge firmware and TensorFlow Lite Micro classification

Leaflet/OpenStreetMap is the bounded Sprint 2 live-location presentation layer. Google
Maps/Routes routing and OR-Tools dispatch optimization remain explicitly planned work.
Celery business jobs, physical LILYGO integration, and TensorFlow Lite Micro remain future
work.

REST/MQTT ingestion remains anonymous and local-development-only; WebSocket reads require
an authorized staff session. The
backend assigns `received_at`, normalizes device observation times to UTC, and stores
coordinates as PostGIS points with SRID 4326. Latest status is chosen by `recorded_at`,
then sequence number, receipt time, and primary key; delayed older observations do not
replace a newer vehicle status. Mosquitto disables retained publications for this
ephemeral telemetry stream.
## Sprint 3 security architecture

Django sessions and CSRF protect the registry, latest-status, and origin-validated
Channels WebSocket. Superusers resolve to `SUPER_ADMIN`; regular active staff require an
explicit `FLEET_MANAGER` or `DISPATCHER` profile, with missing profiles denied. Login is
CSRF-protected, generically denied, and throttled to five attempts per minute by default.
Cookies are HTTP-only, SameSite Lax, and secure-configurable.

The registry extends the existing vehicle identity without changing telemetry history.
`device_id` is immutable. Deactivation preserves history and blocks REST/MQTT ingestion;
reactivation restores it. Anonymous REST/MQTT device ingestion remains a temporary local
limitation; MQTT authentication and TLS remain future work.
