# FTMS architecture

## Target architecture

FTMS uses a Django modular monolith. React presents the browser UI and communicates only with Django over REST and, in a later sprint, WebSocket. Django owns validation, permissions, application behavior, and all PostgreSQL/PostGIS access.

```text
React -> Django REST/WebSocket -> PostgreSQL 17 + PostGIS
                     |
                     +-> Redis/Channels and Celery

Sprint 1: simulator -> Django REST ingestion -> database -> latest-status REST -> React

Planned: LILYGO/simulator -> Mosquitto MQTT -> Django ingestion
                                        -> WebSocket -> React
```

## Component status

Implemented through Sprint 1:

- Minimal React page with a backend health state
- Django ASGI application and database-connected health endpoint
- PostgreSQL/PostGIS, Redis, Mosquitto, Celery, and local Compose configuration
- CI, tests, linting, and development documentation
- Minimal `fleet` and `telemetry` Django modules for a single simulated pilot vehicle
- Strict telemetry `1.0` REST ingestion with race-safe event ID idempotency
- Append-only PostGIS telemetry events and deterministic latest-status REST lookup
- Standard-library simulator and a five-second polling React pilot card

Planned, not implemented:

- MQTT telemetry ingestion and browser WebSocket updates
- Fleet CRUD, driver, dispatch, route, authentication, and mapping features
- Celery business jobs and ETL workflows
- OR-Tools dispatch optimization and XGBoost predictive analytics
- LILYGO edge firmware and TensorFlow Lite Micro classification

The Sprint 1 simulator intentionally calls REST directly. Mosquitto, Channels, Celery, and
their locked configuration remain available but are not used by this slice. Celery will
handle durable asynchronous work in a later approved sprint; OR-Tools and XGBoost likewise
remain future work.

The REST ingestion endpoint is unauthenticated for local Sprint 1 development only. The
backend assigns `received_at`, normalizes device observation times to UTC, and stores
coordinates as PostGIS points with SRID 4326. Latest status is chosen by `recorded_at`,
then sequence number, receipt time, and primary key; delayed older observations do not
replace a newer vehicle status.
