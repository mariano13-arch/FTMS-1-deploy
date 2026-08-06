# Fleet and Transportation Management System

FTMS is a capstone project for a logistics fleet platform. Sprint 4 adds Transport Requests
as the authenticated operational vertical slice, while retaining the secure Vehicle Registry,
MQTT/WebSocket pilot, REST fallback, and OpenStreetMap/Leaflet live marker. Dispatch execution,
route optimization, analytics, device authentication, and physical IoT integration are not implemented.

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
- Transport Requests: http://localhost:5173/transport-requests
- Backend: http://localhost:8000
- Health API: http://localhost:8000/api/health/
- Telemetry ingestion: http://localhost:8000/api/v1/telemetry/
- Pilot latest status: http://localhost:8000/api/v1/vehicles/LILYGO-001/latest-status/
- MQTT: `localhost:1883` (anonymous access is development-only)
- WebSocket: `ws://localhost:8000/ws/v1/vehicles/LILYGO-001/status/`

Prepare the database state and run the REST simulator:

```bash
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_demo_vehicle
docker compose exec backend python manage.py seed_transport_requests
python simulator/telemetry_simulator.py \
  --api-base-url http://localhost:8000 \
  --device-id LILYGO-001 \
  --count 5 \
  --interval 0.1
```

The seed commands idempotently reconcile the demo vehicle and create realistic development
Transport Request records. The vehicle command reconciles `LILYGO-001`, plate `DEMO-001`, display name
`Sprint 1 Demo Vehicle`, and active status. Local MQTT is anonymous and the REST and
Registry, latest-status, and WebSocket access require an authorized staff session.
REST/MQTT ingestion remains anonymous and local-development-only pending device security.

Sprint 4 uses `Asia/Manila` as its default operational timezone while retaining
timezone-aware timestamps (stored instants may remain UTC). Calendar grouping and the
scheduled-today summary use that operational timezone. Sprint 4 uses manual vehicle assignment and a configurable planning duration for schedule
conflict detection; planning duration is not route ETA. Dispatch Queue contains approved
requests, while `READY_FOR_DISPATCH` is the handoff to future driver assignment and trip
lifecycle work. The daily/weekly calendar is served from the real request calendar API;
weekly columns may scroll inside the calendar panel on narrower screens.

On desktop, the application sidebar can switch between expanded and mini modes. Mini mode
keeps accessible navigation icons while hiding long visual labels, and the main content
automatically uses the released width. The preference is stored only in the current browser;
tablet and mobile layouts continue to use the overlay navigation drawer. This shell refinement
requires no API key and no database schema migration.

Still planned: HRMS driver synchronization, driver assignment, OR-Tools recommendation,
Google Routes and real ETA, active trips, safety monitoring, proof of service, fuel and cost
estimation, and feedback.

Create regular staff through the hidden validated password prompt:

```bash
docker compose exec backend python manage.py create_staff_user \
  --username fleetmanager --role FLEET_MANAGER
```

Create Super Admins only with `createsuperuser`. Configure credentialed origins and
secure-cookie behavior with the four `DJANGO_CORS_*`, `DJANGO_CSRF_*`, and
`DJANGO_*_COOKIE_SECURE` settings shown in `.env.example`; wildcard origins are forbidden.

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
- If live updates fail, inspect `mqtt-ingestor`, Mosquitto, and Redis logs, then confirm
  `VITE_WS_BASE_URL`; the UI polls REST every five seconds until WebSocket reconnects.
- If map tiles fail, telemetry remains in the card; confirm the browser can reach
  OpenStreetMap and that content blockers allow its tile host.
- If a port is occupied, stop the conflicting local service; only development ports are published.
- The initial database can take a short time to become healthy before Django starts.

See `docs/architecture.md`, `docs/development-workflow.md`, `docs/api-contracts.md`,
`docs/telemetry-contract-v1.md`, and `simulator/README.md` for design, contract, and
contribution details.
