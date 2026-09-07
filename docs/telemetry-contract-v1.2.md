# Telemetry contract v1.2

Version 1.2 retains all schema 1.1 position and nullable driver-behavior semantics and
adds explicit provenance for supported OBD observations.

```json
{
  "schema_version": "1.2",
  "event_id": "evt-obd-source-1",
  "sequence_number": 313,
  "device_id": "LILYGO-002",
  "recorded_at": "2026-09-07T12:00:00+08:00",
  "latitude": 14.5,
  "longitude": 121.0,
  "position_source": "CELLULAR_LBS",
  "position_accuracy_m": 550,
  "gnss_speed_kph": null,
  "rpm": 2345,
  "coolant_c": 91,
  "engine_load_pct": 47,
  "obd_source": "SIMULATED_TEST",
  "driving_event": null
}
```

Example numbers illustrate the payload shape only and must not be reused as operational
telemetry.

- `obd_source` is `SIMULATED_TEST`, `PHYSICAL_OBD`, or null.
- If any of `rpm`, `coolant_c`, or `engine_load_pct` is non-null, `obd_source` is required.
- When all supported OBD fields are null, `obd_source` may be null.
- OBD Sim Pro observations must use `SIMULATED_TEST`; the server never substitutes
  `PHYSICAL_OBD`.
- Missing OBD values remain null. PID 010D vehicle speed is not accepted as
  `gnss_speed_kph` or another supported OBD field.
- Position provenance remains independent: an LBS or GNSS position is not labeled
  simulated merely because its OBD readings came from a simulator.

Schemas 1.0 and 1.1 do not accept `obd_source`; their existing behavior is unchanged.
