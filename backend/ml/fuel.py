import json
import math
from functools import lru_cache
from pathlib import Path

from telemetry.models import TelemetryEvent

MODEL_DIRECTORY = Path(__file__).resolve().parent / "models" / "fuel"
MODEL_PATH = MODEL_DIRECTORY / "ftms_xgboost_fuel_experiment_3_tuned.joblib"
CONTRACT_PATH = MODEL_DIRECTORY / "model_contract.json"
VALIDATED_TELEMETRY_SOURCE_MODE = "validated_vehicle_telemetry"


@lru_cache(maxsize=1)
def contract():
    with CONTRACT_PATH.open(encoding="utf-8") as contract_file:
        return json.load(contract_file)


def _base_result(status, *, input_timestamp=None):
    metadata = contract()
    return {
        "status": status,
        "model_name": metadata["model_name"],
        "model_version": metadata["model_version"],
        "target": metadata["target"],
        "estimated_fuel_lph": None,
        "input_timestamp": (
            input_timestamp.isoformat()
            if hasattr(input_timestamp, "isoformat")
            else input_timestamp
        ),
        "inputs": {},
        "missing_features": [],
        "invalid_features": [],
        "unexpected_features": [],
        "is_estimate": True,
    }


@lru_cache(maxsize=1)
def load_model():
    import joblib

    model = joblib.load(MODEL_PATH)
    if (
        model.__class__.__module__ != "xgboost.sklearn"
        or model.__class__.__name__ != "XGBRegressor"
    ):
        raise RuntimeError("The configured fuel artifact is not an XGBoost regressor.")
    feature_names = list(model.get_booster().feature_names or [])
    if feature_names != contract()["features"]:
        raise RuntimeError("The configured fuel artifact does not match the feature contract.")
    for name, expected in contract()["hyperparameters"].items():
        actual = getattr(model, name, None)
        if isinstance(expected, float):
            matches = actual is not None and math.isclose(float(actual), expected)
        else:
            matches = actual == expected
        if not matches:
            raise RuntimeError("The configured fuel artifact does not match its model contract.")
    return model


def model_info():
    metadata = contract()
    try:
        load_model()
        availability = "available"
    except Exception:
        availability = "unavailable"
    return {
        **metadata,
        "availability": availability,
        "is_estimate": True,
    }


def predict_fuel(inputs, *, input_timestamp=None):
    metadata = contract()
    required = metadata["features"]
    result = _base_result("prediction_blocked", input_timestamp=input_timestamp)
    if not isinstance(inputs, dict):
        result["status"] = "invalid_input"
        result["invalid_features"] = ["inputs"]
        return result

    unexpected = [name for name in inputs if name not in required]
    if unexpected:
        result["status"] = "invalid_input"
        result["unexpected_features"] = sorted(unexpected)
        return result

    missing = [name for name in required if name not in inputs]
    result["missing_features"] = missing
    if missing:
        return result

    normalized = {}
    invalid = []
    for name in required:
        value = inputs[name]
        if isinstance(value, bool):
            invalid.append(name)
            continue
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            invalid.append(name)
            continue
        if not math.isfinite(numeric_value):
            invalid.append(name)
            continue
        normalized[name] = numeric_value
    result["inputs"] = normalized
    if invalid:
        result["status"] = "invalid_input"
        result["invalid_features"] = invalid
        return result

    try:
        ordered_values = [[normalized[name] for name in required]]
        estimated_fuel_lph = float(load_model().predict(ordered_values)[0])
        if not math.isfinite(estimated_fuel_lph):
            raise ValueError("The model returned a non-finite prediction.")
    except Exception:
        result["status"] = "model_unavailable"
        return result

    result["status"] = "prediction_available"
    result["estimated_fuel_lph"] = estimated_fuel_lph
    result["missing_features"] = []
    return result


def operational_telemetry_inputs(event):
    """Return only model inputs proven by the persisted telemetry contract."""
    inputs = {
        "Vehicle_Speed_km_per_h": float(event.gnss_speed_kph),
    }
    if event.rpm is not None:
        inputs["Engine_RPM_RPM"] = float(event.rpm)
    return inputs


def input_readiness():
    return [
        {
            "feature": "Vehicle_Speed_km_per_h",
            "status": "available",
            "source": "TelemetryEvent.gnss_speed_kph",
            "note": "Persisted GNSS speed is available for every telemetry event.",
        },
        {
            "feature": "Engine_RPM_RPM",
            "status": "available",
            "source": "TelemetryEvent.rpm",
            "note": "Available only when the device reports RPM.",
        },
        {
            "feature": "Absolute_Load_pct",
            "status": "unverified",
            "source": None,
            "note": "Telemetry engine_load_pct is not mapped until semantic equivalence is proven.",
        },
        *[
            {
                "feature": feature,
                "status": "missing",
                "source": None,
                "note": "No matching persisted operational source is currently available.",
            }
            for feature in contract()["features"][3:]
        ],
    ]


def operational_readiness():
    event = TelemetryEvent.objects.select_related("device", "vehicle").first()
    inputs = {}
    timestamp = None
    telemetry = None
    if event is not None:
        inputs = operational_telemetry_inputs(event)
        timestamp = event.recorded_at
        telemetry = {
            "event_id": event.event_id,
            "vehicle_id": event.vehicle_id,
            "device_id": event.device.device_id,
            "vehicle_name": event.vehicle.display_name,
            "recorded_at": event.recorded_at,
        }
    return {
        "inputs": input_readiness(),
        "latest_telemetry": telemetry,
        "latest_operational_result": predict_fuel(inputs, input_timestamp=timestamp),
    }
