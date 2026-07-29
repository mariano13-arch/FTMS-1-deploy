# Planned telemetry contract v1

This is a future shared contract for the simulator and LILYGO device. Sprint 0 does not implement telemetry publishing, ingestion, storage, or processing.

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

- Timestamps will be stored in UTC. `recorded_at` is the device observation time and differs from server `received_at`.
- Speed uses kilometers per hour, distance kilometers, fuel liters, and temperature Celsius.
- Coordinates are planned as a PostGIS `Point`.
- Unsupported OBD-II values must be `null`, never falsely converted to zero.
- `event_id` supports deduplication; `sequence_number` supports device-stream ordering and gap detection.
