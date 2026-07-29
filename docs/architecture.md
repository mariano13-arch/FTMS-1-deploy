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

Implemented through Sprint 2:

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

- Fleet CRUD, driver, dispatch, route, and authentication features
- Celery business jobs and ETL workflows
- OR-Tools dispatch optimization and XGBoost predictive analytics
- LILYGO edge firmware and TensorFlow Lite Micro classification

Leaflet/OpenStreetMap is the bounded Sprint 2 live-location presentation layer. Google
Maps/Routes routing and OR-Tools dispatch optimization remain explicitly planned work.
Celery business jobs, physical LILYGO integration, and TensorFlow Lite Micro remain future
work.

REST, anonymous MQTT, and WebSocket are local-development-only and unauthenticated. The
backend assigns `received_at`, normalizes device observation times to UTC, and stores
coordinates as PostGIS points with SRID 4326. Latest status is chosen by `recorded_at`,
then sequence number, receipt time, and primary key; delayed older observations do not
replace a newer vehicle status. Mosquitto disables retained publications for this
ephemeral telemetry stream.
