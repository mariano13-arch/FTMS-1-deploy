# Simulated telemetry pilot

The simulator uses only Python's standard library. It sends deterministic-looking pilot
samples for `LILYGO-001` directly to the Sprint 1 REST ingestion endpoint; MQTT and hardware
integration remain out of scope.

Start the Compose stack, apply migrations, and seed the demo vehicle:

```bash
docker compose up --build -d
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_demo_vehicle
```

Send one event with the defaults (`http://localhost:8000` and `LILYGO-001`):

```bash
python simulator/telemetry_simulator.py
```

Send five events using the complete supported interface:

```bash
python simulator/telemetry_simulator.py \
  --api-base-url http://localhost:8000 \
  --device-id LILYGO-001 \
  --count 5 \
  --interval 0.1
```

The third sample deliberately sends unavailable OBD-II fields as JSON `null`, never as
fabricated zeroes. Each run uses unique event IDs, increasing sequence numbers, and
timezone-aware UTC timestamps. A failed submission exits nonzero.
