# FTMS LILYGO Phase 2 firmware

This directory contains the repository source for the FTMS LILYGO T-A7670E Phase 2
telemetry firmware. It reads an MPU6050 and performs TensorFlow Lite Micro INT8
driver-behavior inference at the edge before sending FTMS telemetry schema 1.2 by HTTPS.

The model uses these eight inputs in order: `AccX`, `AccY`, `AccZ`, `GyroX`, `GyroY`,
`GyroZ`, `acc_magnitude`, and `gyro_magnitude`. Model data is in
`driver_behavior_model.h`; feature scaling and class order are in
`driver_behavior_preprocessing.h`.

The trained classes map to `driving_event` as follows:

| Model class | FTMS value |
| --- | --- |
| `sudden_acceleration` | `HARSH_ACCELERATION` |
| `sudden_braking` | `HARSH_BRAKING` |
| `sudden_left_turn` | `SHARP_TURN` |
| `sudden_right_turn` | `SHARP_TURN` |

This model has no `NORMAL` class. No motion, an unavailable prediction, failed inference,
or an unknown label is transmitted as JSON `null`, never as a stale or fabricated event.

Copy `ftms_lilygo_config.example.h` to `ftms_lilygo_config.h` and set the local device,
network endpoint, APN, and Bluetooth adapter values. The local header is ignored by Git;
never commit credentials, pairing secrets, or device-specific addresses.

The repository proves that this firmware source is implemented. It does not prove that a
physical board has been flashed with, or is currently running, this build.
