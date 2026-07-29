# Fleet and Transportation Management System

FTMS is a capstone project for a logistics fleet platform. Sprint 1 adds a bounded
simulated-telemetry vertical slice to the Sprint 0 development foundation: a seeded pilot
vehicle, REST ingestion, PostGIS persistence, latest-status lookup, a simulator, and one
React status card. Authentication, dispatching, maps, MQTT ingestion, optimization,
analytics, and real IoT integration are not implemented.

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
- Telemetry ingestion: http://localhost:8000/api/v1/telemetry/
- Pilot latest status: http://localhost:8000/api/v1/vehicles/LILYGO-001/latest-status/
- MQTT: `localhost:1883` (anonymous access is development-only)

Prepare the Sprint 1 database state and run the simulator:

```bash
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_demo_vehicle
python simulator/telemetry_simulator.py \
  --api-base-url http://localhost:8000 \
  --device-id LILYGO-001 \
  --count 5 \
  --interval 0.1
```

The seed command idempotently reconciles `LILYGO-001`, plate `DEMO-001`, display name
`Sprint 1 Demo Vehicle`, and active status. Local Sprint 1 ingestion is intentionally
unauthenticated and must not be exposed as a production API.

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

See `docs/architecture.md`, `docs/development-workflow.md`, `docs/api-contracts.md`,
`docs/telemetry-contract-v1.md`, and `simulator/README.md` for design, contract, and
contribution details.
