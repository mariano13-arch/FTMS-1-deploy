# Development workflow

`main` is the stable branch. Do not develop features directly on it.

1. Synchronize `main` using fast-forward only.
2. Create a narrowly scoped feature branch.
3. Add tests and run all relevant CI-equivalent checks.
4. Open a pull request targeting `main`.
5. Require another project member to review before merge.

Required CI checks include frontend lint, type-check, tests, and build; backend lint, Django checks, migration drift check, and tests against PostGIS; and Compose configuration validation.

Use Conventional Commits, for example:

- `chore: configure local development services`
- `feat: add vehicle registration`
- `fix: handle unavailable database in health check`
- `docs: clarify telemetry units`

Never force-push shared branches or commit credentials.

## Sprint 1 local telemetry exercise

After starting Compose, apply migrations and run the idempotent seed command:

```bash
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_demo_vehicle
docker compose exec backend python manage.py seed_demo_vehicle
```

Then send pilot data with:

```bash
python simulator/telemetry_simulator.py \
  --api-base-url http://localhost:8000 \
  --device-id LILYGO-001 \
  --count 5 \
  --interval 0.1
```

The simulator requires no third-party Python packages.

## Sprint 2 real-time exercise

Configure `MQTT_HOST`, `MQTT_PORT`, `MQTT_TOPIC_PREFIX`, `MQTT_QOS`,
`VITE_API_BASE_URL`, and `VITE_WS_BASE_URL` as shown in `.env.example`. The MQTT ingestor
retries initial and later broker connections. React reconnects with exponential backoff
capped at 30 seconds and polls REST every five seconds only while WebSocket is unavailable.
Telemetry is stale when `recorded_at` is more than 60 seconds old.

The Leaflet marker receives `[latitude, longitude]`; PostGIS stores the same point as
longitude X and latitude Y. OpenStreetMap attribution remains visible. If MQTT, Redis,
WebSocket, frontend, or tiles fail, inspect the corresponding Compose service logs and
confirm the configured host URLs. These local anonymous interfaces must not be exposed.
