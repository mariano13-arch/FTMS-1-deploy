# Simulated telemetry pilot

The standard-library REST simulator remains available. Sprint 2 adds a separate pinned
Paho MQTT simulator for `LILYGO-001`; physical hardware remains out of scope.

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

Create an isolated environment and run the required MQTT exercise:

```bash
python3 -m venv /tmp/ftms-sprint2-simulator
/tmp/ftms-sprint2-simulator/bin/pip install -r simulator/requirements.txt
/tmp/ftms-sprint2-simulator/bin/python simulator/mqtt_telemetry_simulator.py \
  --broker-host localhost \
  --broker-port 1883 \
  --topic-prefix ftms/v1/telemetry \
  --device-id LILYGO-001 \
  --count 5 \
  --interval 1 \
  --qos 1
```

It publishes QoS 1 with `retain=false` to
`ftms/v1/telemetry/LILYGO-001`, waits for each broker acknowledgement, changes
coordinates, and emits one nullable OBD-II sample. Output contains event identity but not
the payload or exact coordinates. Connection or publication failure exits nonzero.
