"""Contract-safe inference for the research maintenance-risk model."""
import json
import math
from functools import lru_cache
from pathlib import Path

BASE = Path(__file__).resolve().parent / "models" / "maintenance"
META = BASE / "engine_fault_xgboost_obd_candidate_v2_metadata.json"
FEATURES = BASE / "engine_fault_obd_feature_contract_v2.json"
RESPONSE = BASE / "engine_fault_inference_response_contract_v2.json"
MODEL = BASE / "engine_fault_xgboost_obd_candidate_v2.json"


@lru_cache(maxsize=1)
def contracts():
    return tuple(json.loads(p.read_text(encoding="utf-8")) for p in (META, FEATURES, RESPONSE))


@lru_cache(maxsize=1)
def load_model():
    import xgboost

    meta, feature, response = contracts()
    booster = xgboost.Booster()
    booster.load_model(str(MODEL))
    required = feature["feature_order"]
    if list(booster.feature_names or []) != required or booster.num_features() != 4:
        raise RuntimeError("Maintenance model feature contract mismatch")
    config = json.loads(booster.save_config())
    objective = config["learner"]["objective"]["name"]
    if objective != "binary:logistic" or meta["features"] != required:
        raise RuntimeError("Maintenance model objective contract mismatch")
    if (
        meta["decision_threshold"]
        != feature["decision_threshold"]
        != response["decision_threshold"]
    ):
        raise RuntimeError("Maintenance threshold contract mismatch")
    return booster


def _base(status, source):
    meta, feature, response = contracts()
    return {
        "status": status,
        "model_name": response["model_name"],
        "model_version": meta["version"],
        "contract_version": response["schema_version"],
        "deployment_state": response["deployment_state"],
        "source_mode": source,
        "model_risk_score": None,
        "classification": None,
        "decision_threshold": response["decision_threshold"],
        "score_semantics": response["score_semantics"],
        "inputs": {},
        "missing_features": [],
        "invalid_features": [],
        "unexpected_features": [],
        "abstained_features": [],
        "mechanic_confirmation_required": True,
        "specific_component_diagnosis": False,
        "remaining_useful_life_estimation": False,
        "dispatchable_alert_allowed": source == "research_replay" and False,
    }


def predict(inputs, source_mode):
    _, feature, response = contracts()
    required = feature["feature_order"]
    result = _base("prediction_blocked", source_mode)
    if source_mode not in response["source_modes"]:
        result["status"] = "invalid_input"
        result["invalid_features"] = ["source_mode"]
        return result
    if source_mode != "research_replay":
        return result
    if not isinstance(inputs, dict):
        result["status"] = "invalid_input"
        result["invalid_features"] = ["inputs"]
        return result
    extra = sorted(set(inputs) - set(required))
    if extra:
        result["status"] = "invalid_input"
        result["unexpected_features"] = extra
        return result
    result["missing_features"] = [f for f in required if f not in inputs]
    if result["missing_features"]:
        return result
    ranges = feature["features"]
    values = {}
    for name in required:
        value = inputs[name]
        if isinstance(value, bool):
            result["invalid_features"].append(name)
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            result["invalid_features"].append(name)
            continue
        if not math.isfinite(value):
            result["invalid_features"].append(name)
            continue
        bounds = ranges[name]["development_data_range"]
        if value < bounds["min"] or value > bounds["max"]:
            result["invalid_features"].append(name)
            continue
        if value < bounds["p0_1"] or value > bounds["p99_9"]:
            result["abstained_features"].append(name)
        values[name] = value
    result["inputs"] = values
    if result["invalid_features"]:
        result["status"] = "invalid_input"
        return result
    if result["abstained_features"]:
        result["status"] = "abstained"
        return result
    import xgboost

    matrix = xgboost.DMatrix(
        [[values[feature_name] for feature_name in required]],
        feature_names=required,
    )
    score = float(load_model().predict(matrix)[0])
    if not math.isfinite(score):
        raise RuntimeError("Non-finite maintenance score")
    result["status"] = "prediction_available"
    result["model_risk_score"] = score
    result["classification"] = (
        "Maintenance risk" if score >= result["decision_threshold"] else "Healthy"
    )
    return result


def model_info():
    meta, feature, response = contracts()
    load_model()
    return {
        "model_name": response["model_name"],
        "model_version": meta["version"],
        "contract_version": response["schema_version"],
        "features": feature["feature_order"],
        "decision_threshold": response["decision_threshold"],
        "deployment_state": response["deployment_state"],
        "production_ready": False,
        "score_semantics": response["score_semantics"],
    }


def readiness():
    _, feature, response = contracts()
    return {
        "deployment_state": "research_candidate",
        "production_ready": False,
        "direct_obd_feed_allowed": False,
        "unit_scaling_verified": False,
        "vehicle_compatibility_verified": False,
        "blocking_reason": feature["integration_status"]["blocking_reason"],
        "required_features": feature["feature_order"],
        "source_modes": response["source_modes"],
    }
