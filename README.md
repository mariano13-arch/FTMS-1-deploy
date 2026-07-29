# Fleet and Transportation Management System

FTMS is a capstone project for a logistics fleet platform. This repository currently contains only the Sprint 0 development foundation: a React frontend, Django API, and local supporting infrastructure. Authentication, fleet records, dispatching, maps, telemetry ingestion, optimization, analytics, and IoT integration are not implemented.

## Locked stack

- React, TypeScript, and Vite
- Django, Django REST Framework, Channels, Daphne, and Celery
- PostgreSQL 17 with PostGIS
- Redis and Mosquitto MQTT
- Planned later: Google Maps/Routes, OR-Tools, XGBoost, LILYGO T-A7670E R2, and TensorFlow Lite Micro

## Prerequisites

- Docker with Docker Compose
- For host-based development: Python 3.12 and Node.js 22

## Local setup

Copy `.env.example` to `.env` and keep the local-only defaults or replace them with your own development values. Never commit `.env`.

```bash
cp .env.example .env
docker compose up --build
```

Stop the stack without deleting the database volume:

```bash
docker compose down
```

Services:

- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- Health API: http://localhost:8000/api/health/
- MQTT: `localhost:1883` (anonymous access is development-only)

## Verification commands

Backend verification inside the running Compose stack:

```bash
docker compose exec backend ruff check .
docker compose exec backend python manage.py check
docker compose exec backend python manage.py makemigrations --check --dry-run
docker compose exec backend python manage.py test
```

These tests use the PostgreSQL/PostGIS service on the internal Compose network. Optional
host-based backend commands require Python dependencies plus a separately reachable
PostgreSQL/PostGIS instance and a matching host-accessible `DATABASE_URL`.

Frontend:

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm run test -- --run
npm run build
```

Repository:

```bash
docker compose config
```

## Troubleshooting

- If the backend is unhealthy, inspect `docker compose logs backend db` and confirm the database variables match.
- If the frontend reports an error, confirm the backend health URL responds and `VITE_API_BASE_URL` is correct.
- If a port is occupied, stop the conflicting local service; only development ports are published.
- The initial database can take a short time to become healthy before Django starts.

See `docs/architecture.md`, `docs/development-workflow.md`, and `docs/api-contracts.md` for design and contribution details.
