# Telemetry contract v1.1

Version 1.1 extends, rather than redefines, the 1.0 telemetry contract. All 1.0
payloads retain their existing GNSS semantics. Version 1.1 adds explicit position
provenance and permits GNSS speed to be null only for cellular LBS observations.

```json
{
  "schema_version": "1.1",
  "event_id": "evt-source-aware-1",
  "sequence_number": 312,
  "device_id": "LILYGO-002",
  "recorded_at": "2026-07-29T09:18:20+08:00",
  "latitude": 14.5,
  "longitude": 121.0,
  "position_source": "CELLULAR_LBS",
  "position_accuracy_m": 550,
  "gnss_speed_kph": null,
  "rpm": null,
  "coolant_c": null,
  "engine_load_pct": null,
  "driving_event": null
}
```

The coordinates and accuracy above illustrate payload shape only. Senders must use
actual modem observations and must never reuse example values as operational telemetry.

- `position_source` is required in 1.1 and is `GNSS` or `CELLULAR_LBS`.
- Both sources require actual latitude and longitude values.
- GNSS requires `gnss_speed_kph` in the existing `0..300` km/h range. Accuracy may be null.
- Cellular LBS requires `position_accuracy_m > 0` and `gnss_speed_kph: null`.
- OBD vehicle speed must never be placed in `gnss_speed_kph`.
- `driving_event` may be null when no driver-behavior observation is available. If
  present, it remains one of `NORMAL`, `HARSH_BRAKING`, `HARSH_ACCELERATION`, or
  `SHARP_TURN`; receivers must not interpret null as `NORMAL`.
- Coordinates, speed, accuracy, and source must never be inferred or fabricated.

All other validation, active device-binding resolution, ordering, idempotency, transport,
and freshness semantics remain as documented for version 1.0.

Senders requiring explicit OBD provenance use the additive
[version 1.2 contract](telemetry-contract-v1.2.md). Version 1.1 does not accept
`obd_source`.
