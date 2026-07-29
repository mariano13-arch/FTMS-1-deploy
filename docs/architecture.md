# FTMS architecture

## Target architecture

FTMS uses a Django modular monolith. React presents the browser UI and communicates only with Django over REST and, in a later sprint, WebSocket. Django owns validation, permissions, application behavior, and all PostgreSQL/PostGIS access.

```text
React -> Django REST/WebSocket -> PostgreSQL 17 + PostGIS
                     |
                     +-> Redis/Channels and Celery

Planned: LILYGO/simulator -> Mosquitto MQTT -> Django ingestion -> database
                                                       -> WebSocket -> React
```

## Component status

Implemented in Sprint 0:

- Minimal React page with a backend health state
- Django ASGI application and database-connected health endpoint
- PostgreSQL/PostGIS, Redis, Mosquitto, Celery, and local Compose configuration
- CI, tests, linting, and development documentation

Planned, not implemented:

- MQTT telemetry ingestion and browser WebSocket updates
- Fleet, driver, dispatch, route, authentication, and mapping features
- Celery business jobs and ETL workflows
- OR-Tools dispatch optimization and XGBoost predictive analytics
- LILYGO edge firmware and TensorFlow Lite Micro classification

Celery will handle durable asynchronous work; ETL will validate and transform telemetry within the modular monolith. OR-Tools and XGBoost will be introduced only when their later sprint requirements are approved.
