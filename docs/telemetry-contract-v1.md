# Telemetry contract v1

Sprint 1 implements this shared contract for the local simulator through REST ingestion.
It does not implement MQTT or real LILYGO hardware integration.

```json
{
  "schema_version": "1.0",
  "event_id": "evt-000311",
  "sequence_number": 311,
  "device_id": "LILYGO-001",
  "recorded_at": "2026-07-29T09:18:20+08:00",
  "latitude": 14.5186,
  "longitude": 121.0196,
  "gnss_speed_kph": 38.2,
  "rpm": 1750,
  "coolant_c": 88,
  "engine_load_pct": 34,
  "driving_event": "NORMAL"
}
```

- `schema_version` must be exactly `"1.0"`.
- `event_id` is required and globally unique; `sequence_number` must be a non-negative integer.
- `device_id` must identify an active `Vehicle`.
- `recorded_at` must include a timezone. It is normalized and stored in UTC, and differs
  from the server-generated and persisted `received_at`.
- Latitude is `-90..90`, longitude is `-180..180`, speed is `0..300` km/h, RPM is
  `0..12000`, and engine load is `0..100` percent.
- Coordinates are stored as a PostGIS point with SRID 4326 in longitude/latitude order.
- Unsupported OBD-II values must be `null`, never falsely converted to zero.
- `driving_event` is one of `NORMAL`, `HARSH_BRAKING`, `HARSH_ACCELERATION`, or
  `SHARP_TURN`.

Accepted events are append-only. Replaying the exact semantic event is idempotent; reusing
its ID for different data returns `409 Conflict`.

The seeded local pilot is exactly:

```text
device_id: LILYGO-001
plate_number: DEMO-001
display_name: Sprint 1 Demo Vehicle
is_active: true
```

Run the standard-library simulator with:

```bash
python simulator/telemetry_simulator.py \
  --api-base-url http://localhost:8000 \
  --device-id LILYGO-001 \
  --count 5 \
  --interval 0.1
```

This REST endpoint is intentionally unauthenticated for local Sprint 1 development only.
See `docs/api-contracts.md` for complete request, success, duplicate, validation, conflict,
latest-status, and unknown-device JSON examples.
