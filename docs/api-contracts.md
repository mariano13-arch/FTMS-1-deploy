# API contracts

## `GET /api/health/`

The readiness endpoint performs a lightweight database query.

Successful response (`200 OK`):

```json
{
  "status": "ok",
  "service": "ftms-backend",
  "database": "ok"
}
```

An unavailable database returns `503` with a safe response that excludes credentials,
internal hosts, SQL, exception details, and stack traces.

## `POST /api/v1/telemetry/`

Sprint 1 ingestion is unauthenticated for local development only. It accepts the strict
telemetry `1.0` contract.

Valid request:

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

New event (`201 Created`):

```json
{
  "status": "created",
  "duplicate": false,
  "event": {
    "schema_version": "1.0",
    "event_id": "evt-000311",
    "sequence_number": 311,
    "device_id": "LILYGO-001",
    "recorded_at": "2026-07-29T01:18:20Z",
    "received_at": "2026-07-29T01:18:21.123456Z",
    "latitude": 14.5186,
    "longitude": 121.0196,
    "gnss_speed_kph": 38.2,
    "rpm": 1750,
    "coolant_c": 88.0,
    "engine_load_pct": 34.0,
    "driving_event": "NORMAL"
  }
}
```

Identical retransmission (`200 OK`):

```json
{
  "status": "duplicate",
  "duplicate": true,
  "event": {
    "schema_version": "1.0",
    "event_id": "evt-000311",
    "sequence_number": 311,
    "device_id": "LILYGO-001",
    "recorded_at": "2026-07-29T01:18:20Z",
    "received_at": "2026-07-29T01:18:21.123456Z",
    "latitude": 14.5186,
    "longitude": 121.0196,
    "gnss_speed_kph": 38.2,
    "rpm": 1750,
    "coolant_c": 88.0,
    "engine_load_pct": 34.0,
    "driving_event": "NORMAL"
  }
}
```

Validation failure (`400 Bad Request`):

```json
{
  "schema_version": [
    "Only schema_version 1.0 is supported."
  ]
}
```

Conflicting event ID (`409 Conflict`):

```json
{
  "detail": "event_id already exists with different telemetry data."
}
```

The server generates and persists `received_at`. Timezone-aware `recorded_at` values are
normalized to UTC. Unsupported OBD-II values remain JSON `null`; legitimate zeroes remain
zero. Coordinates are stored as PostGIS points with SRID 4326.

## `GET /api/v1/vehicles/{device_id}/latest-status/`

Known vehicle without telemetry (`200 OK`):

```json
{
  "vehicle": {
    "device_id": "LILYGO-001",
    "plate_number": "DEMO-001",
    "display_name": "Sprint 1 Demo Vehicle"
  },
  "latest": null
}
```

Known vehicle with telemetry (`200 OK`):

```json
{
  "vehicle": {
    "device_id": "LILYGO-001",
    "plate_number": "DEMO-001",
    "display_name": "Sprint 1 Demo Vehicle"
  },
  "latest": {
    "schema_version": "1.0",
    "event_id": "evt-000311",
    "sequence_number": 311,
    "device_id": "LILYGO-001",
    "recorded_at": "2026-07-29T01:18:20Z",
    "received_at": "2026-07-29T01:18:21.123456Z",
    "latitude": 14.5186,
    "longitude": 121.0196,
    "gnss_speed_kph": 38.2,
    "rpm": 1750,
    "coolant_c": 88.0,
    "engine_load_pct": 34.0,
    "driving_event": "NORMAL"
  }
}
```

Unknown device (`404 Not Found`):

```json
{
  "detail": "No Vehicle matches the given query."
}
```

Latest means `recorded_at` first, followed by sequence number, server receipt time, and
primary key as deterministic tie-breakers. A late-arriving older observation cannot replace
the current status. No telemetry update or delete endpoint exists.

## MQTT and WebSocket

MQTT uses QoS 1 at `ftms/v1/telemetry/{device_id}` and the exact REST request payload
above. The topic suffix must equal the payload `device_id`; retained, malformed,
oversized, extra-field, invalid, mismatched, and conflicting messages are rejected.
Identical retransmissions remain idempotent.

Connect to `/ws/v1/vehicles/{device_id}/status/`. A known vehicle receives:

```json
{
  "type": "vehicle.status.snapshot",
  "data": {
    "vehicle": {
      "device_id": "LILYGO-001",
      "plate_number": "DEMO-001",
      "display_name": "Sprint 1 Demo Vehicle"
    },
    "latest": null
  }
}
```

A newly committed actual-latest event sends `vehicle.status.updated`; its `data` is
exactly the latest-status REST response shown above. Duplicates, conflicts, and stored
late arrivals do not broadcast. Unknown vehicles close with code `4404`. The
local-development WebSocket is unauthenticated. Delivery failure never changes a
successful persistence result.
