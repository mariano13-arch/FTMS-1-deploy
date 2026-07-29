# ADR 0001: Django modular monolith

- Status: Accepted
- Date: 2026-07-29

## Context

The capstone pilot needs one coherent application boundary, geospatial persistence, asynchronous work, browser updates, and a future path for MQTT telemetry. A small team must be able to develop, test, and deploy it reliably.

## Decision

Use Django and Django REST Framework as a modular monolith, PostgreSQL 17 with PostGIS as the authoritative database, Redis for Channels and Celery, and Mosquitto as the MQTT broker.

## Consequences

Domain modules can remain separated inside one deployable backend while sharing transactions, permissions, migrations, and operational tooling. PostGIS supplies mature geospatial capabilities. Redis supports ephemeral messaging and queued work; Mosquitto provides a focused IoT protocol boundary.

This avoids the networking, deployment, observability, consistency, and team-coordination cost of premature microservices. Modules can be extracted later only if measured scale or ownership boundaries justify it.
