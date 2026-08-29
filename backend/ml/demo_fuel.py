"""Controlled fuel-model inputs for development verification only."""

from ml.fuel import predict_fuel

DEMO_DEVICE_ID = "LILYGO-001"
DEMO_PLATE_NUMBER = "DEMO-001"
DEMO_DISPLAY_NAME = "Sprint 1 Demo Vehicle"
DEMO_SOURCE_MODE = "demo_seed"
DEMO_HISTORY_LIMIT = 24

# These values are deterministic test fixtures. They are NOT_OPERATIONAL_TELEMETRY,
# were not reported by a vehicle ECU, and must never be copied to TelemetryEvent.
CONTROLLED_DEMO_INPUTS = {
    "Absolute_Load_pct": 45.0,
    "OAT_DegC": 30.0,
    "Short_Term_Fuel_Trim_Bank_1_pct": 1.5,
    "Short_Term_Fuel_Trim_Bank_2_pct": 0.5,
    "Long_Term_Fuel_Trim_Bank_1_pct": -1.0,
    "Long_Term_Fuel_Trim_Bank_2_pct": 0.0,
    "Generalized_Weight": 1500.0,
}
NOT_OPERATIONAL_TELEMETRY = frozenset(CONTROLLED_DEMO_INPUTS)


def build_demo_inputs(telemetry_event):
    """Combine real persisted speed/RPM with isolated demo-only fixture values."""
    if telemetry_event.rpm is None:
        raise ValueError("A persisted RPM value is required for demo fuel inference.")
    return {
        "Vehicle_Speed_km_per_h": float(telemetry_event.gnss_speed_kph),
        "Engine_RPM_RPM": float(telemetry_event.rpm),
        **CONTROLLED_DEMO_INPUTS,
    }


def run_demo_inference(telemetry_event):
    return predict_fuel(
        build_demo_inputs(telemetry_event),
        input_timestamp=telemetry_event.recorded_at,
    )
