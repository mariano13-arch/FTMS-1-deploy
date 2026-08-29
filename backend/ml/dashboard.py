from datetime import timedelta

from django.db.models import Avg, OuterRef, Subquery
from django.db.models.functions import TruncDay, TruncHour
from django.utils import timezone

from fleet.models import Vehicle
from ml.demo_fuel import DEMO_SOURCE_MODE, NOT_OPERATIONAL_TELEMETRY
from ml.fuel import contract, model_info
from ml.models import FuelPrediction
from telemetry.models import TelemetryEvent

RANGES = {
    "24h": (timedelta(hours=24), TruncHour),
    "7d": (timedelta(days=7), TruncDay),
    "30d": (timedelta(days=30), TruncDay),
}

FEATURE_UNITS = {
    "Vehicle_Speed_km_per_h": "km/h",
    "Engine_RPM_RPM": "RPM",
    "Absolute_Load_pct": "%",
    "OAT_DegC": "°C",
    "Short_Term_Fuel_Trim_Bank_1_pct": "%",
    "Short_Term_Fuel_Trim_Bank_2_pct": "%",
    "Long_Term_Fuel_Trim_Bank_1_pct": "%",
    "Long_Term_Fuel_Trim_Bank_2_pct": "%",
    "Generalized_Weight": None,
}


def _prediction_input_details(inputs, source_mode):
    if not inputs:
        return []
    is_demo = source_mode == DEMO_SOURCE_MODE
    return [
        {
            "feature": feature,
            "value": float(inputs[feature]),
            "unit": FEATURE_UNITS[feature],
            "source": (
                "Demo/Test Input"
                if is_demo and feature in NOT_OPERATIONAL_TELEMETRY
                else "Actual persisted telemetry"
                if is_demo
                else "Validated API Input"
            ),
        }
        for feature in contract()["features"]
        if feature in inputs
    ]


def _vehicle_input_readiness(has_telemetry, rpm):
    features = contract()["features"]
    available = []
    missing = []
    unverified = ["Absolute_Load_pct"]
    if has_telemetry:
        available.append("Vehicle_Speed_km_per_h")
        if rpm is not None:
            available.append("Engine_RPM_RPM")
        else:
            missing.append("Engine_RPM_RPM")
    else:
        missing.extend(["Vehicle_Speed_km_per_h", "Engine_RPM_RPM"])
    missing.extend(features[3:])
    return {
        "available_count": len(available),
        "required_count": len(features),
        "available_features": available,
        "missing_features": missing,
        "unverified_features": unverified,
    }


def _vehicle_rows(model_availability):
    latest_telemetry = TelemetryEvent.objects.filter(vehicle_id=OuterRef("pk")).order_by(
        "-recorded_at", "-sequence_number", "-received_at", "-pk"
    )
    latest_prediction = FuelPrediction.objects.filter(vehicle_id=OuterRef("pk")).order_by(
        "-input_timestamp", "-predicted_at", "-pk"
    )
    vehicles = Vehicle.objects.filter(is_active=True).annotate(
        latest_telemetry_at=Subquery(latest_telemetry.values("recorded_at")[:1]),
        latest_telemetry_rpm=Subquery(latest_telemetry.values("rpm")[:1]),
        latest_prediction_id=Subquery(latest_prediction.values("pk")[:1]),
        latest_prediction_input_at=Subquery(
            latest_prediction.values("input_timestamp")[:1]
        ),
        latest_prediction_created_at=Subquery(
            latest_prediction.values("predicted_at")[:1]
        ),
        latest_estimated_fuel_lph=Subquery(
            latest_prediction.values("estimated_fuel_lph")[:1]
        ),
        latest_prediction_source_mode=Subquery(
            latest_prediction.values("source_mode")[:1]
        ),
        latest_prediction_inputs=Subquery(
            latest_prediction.values("validated_inputs")[:1]
        ),
    ).order_by("display_name", "plate_number", "pk")

    rows = []
    for vehicle in vehicles:
        has_telemetry = vehicle.latest_telemetry_at is not None
        is_demo_prediction = vehicle.latest_prediction_source_mode == DEMO_SOURCE_MODE
        prediction_matches_latest_telemetry = (
            vehicle.latest_prediction_id is not None
            and vehicle.latest_prediction_input_at == vehicle.latest_telemetry_at
        )
        if not has_telemetry:
            prediction_status = "no_telemetry"
        elif model_availability != "available":
            prediction_status = "model_unavailable"
        elif prediction_matches_latest_telemetry and is_demo_prediction:
            prediction_status = "demo_ready"
        elif prediction_matches_latest_telemetry:
            prediction_status = "prediction_available"
        else:
            prediction_status = "prediction_blocked"
        readiness = _vehicle_input_readiness(has_telemetry, vehicle.latest_telemetry_rpm)
        if prediction_status in {"prediction_available", "demo_ready"}:
            readiness = {
                "available_count": len(contract()["features"]),
                "required_count": len(contract()["features"]),
                "available_features": contract()["features"],
                "missing_features": [],
                "unverified_features": [],
            }
        rows.append(
            {
                "vehicle_id": vehicle.pk,
                "vehicle_name": vehicle.display_name,
                "plate_number": vehicle.plate_number,
                "device_id": vehicle.device_id,
                "telemetry_status": "available" if has_telemetry else "no_telemetry",
                "telemetry_timestamp": vehicle.latest_telemetry_at,
                "latest_estimated_fuel_lph": (
                    float(vehicle.latest_estimated_fuel_lph)
                    if vehicle.latest_estimated_fuel_lph is not None
                    else None
                ),
                "prediction_status": prediction_status,
                "last_prediction_at": vehicle.latest_prediction_created_at,
                "prediction_source_mode": vehicle.latest_prediction_source_mode,
                "prediction_source_label": (
                    "Demo/Test Inputs"
                    if is_demo_prediction
                    else "Validated API Inputs"
                    if vehicle.latest_prediction_id is not None
                    else None
                ),
                "latest_prediction_input_timestamp": vehicle.latest_prediction_input_at,
                "latest_prediction_inputs": _prediction_input_details(
                    vehicle.latest_prediction_inputs,
                    vehicle.latest_prediction_source_mode,
                ),
                "is_demo_prediction": is_demo_prediction,
                "input_readiness": readiness,
            }
        )
    return rows


def dashboard_data(*, range_key="24h", vehicle_id=None, page=1, page_size=10, search=""):
    metadata = model_info()
    rows = _vehicle_rows(metadata["availability"])
    now = timezone.now()
    window, truncator = RANGES[range_key]
    history = FuelPrediction.objects.filter(input_timestamp__gte=now - window)
    selected_vehicle = None
    if vehicle_id is not None:
        selected = next((row for row in rows if row["vehicle_id"] == vehicle_id), None)
        selected_vehicle = (
            {
                "vehicle_id": selected["vehicle_id"],
                "vehicle_name": selected["vehicle_name"],
                "plate_number": selected["plate_number"],
            }
            if selected
            else None
        )
        history = history.filter(vehicle_id=vehicle_id)
    trend = list(
        history.annotate(bucket=truncator("input_timestamp"))
        .values("bucket")
        .annotate(estimated_fuel_lph=Avg("estimated_fuel_lph"))
        .order_by("bucket")
    )

    ready_rows = [row for row in rows if row["prediction_status"] == "prediction_available"]
    demo_ready_rows = [row for row in rows if row["prediction_status"] == "demo_ready"]
    estimated_values = [
        row["latest_estimated_fuel_lph"]
        for row in ready_rows
        if row["latest_estimated_fuel_lph"] is not None
    ]
    demo_estimated_values = [
        row["latest_estimated_fuel_lph"]
        for row in demo_ready_rows
        if row["latest_estimated_fuel_lph"] is not None
    ]
    readiness_breakdown = {
        "ready": len(ready_rows),
        "demo_ready": len(demo_ready_rows),
        "blocked": sum(row["prediction_status"] == "prediction_blocked" for row in rows),
        "no_telemetry": sum(row["prediction_status"] == "no_telemetry" for row in rows),
        "model_unavailable": sum(
            row["prediction_status"] == "model_unavailable" for row in rows
        ),
    }
    comparison = [
        {
            "vehicle_id": row["vehicle_id"],
            "vehicle_name": row["vehicle_name"],
            "plate_number": row["plate_number"],
            "estimated_fuel_lph": row["latest_estimated_fuel_lph"],
            "predicted_at": row["last_prediction_at"],
            "source_mode": row["prediction_source_mode"],
            "source_label": row["prediction_source_label"],
            "is_demo_prediction": row["is_demo_prediction"],
        }
        for row in rows
        if row["latest_estimated_fuel_lph"] is not None
    ]
    comparison.sort(key=lambda item: item["estimated_fuel_lph"], reverse=True)
    demo_data_present = history.filter(source_mode=DEMO_SOURCE_MODE).exists() or any(
        row["is_demo_prediction"] for row in rows
    )
    normalized_search = search.strip().lower()
    table_rows = rows
    if normalized_search:
        table_rows = [
            row
            for row in rows
            if normalized_search in row["vehicle_name"].lower()
            or normalized_search in row["plate_number"].lower()
            or normalized_search in row["device_id"].lower()
        ]
    total_pages = max(1, (len(table_rows) + page_size - 1) // page_size)
    page = min(page, total_pages)
    start_index = (page - 1) * page_size
    page_rows = table_rows[start_index : start_index + page_size]
    return {
        "refreshed_at": now,
        "model_availability": metadata["availability"],
        "demo_data_present": demo_data_present,
        "demo_data_note": (
            "Demo prediction records are used for system verification and are not "
            "operational fuel measurements."
            if demo_data_present
            else None
        ),
        "filters": {
            "range": range_key,
            "vehicle_id": vehicle_id,
            "selected_vehicle": selected_vehicle,
            "trend_aggregation": "hourly average" if range_key == "24h" else "daily average",
        },
        "summary": {
            "vehicle_count": len(rows),
            "prediction_ready_count": len(ready_rows),
            "demo_ready_count": len(demo_ready_rows),
            "prediction_blocked_count": len(rows) - len(ready_rows) - len(demo_ready_rows),
            "average_estimated_fuel_lph": (
                sum(estimated_values) / len(estimated_values) if estimated_values else None
            ),
            "demo_average_estimated_fuel_lph": (
                sum(demo_estimated_values) / len(demo_estimated_values)
                if demo_estimated_values
                else None
            ),
        },
        "trend": [
            {
                "timestamp": item["bucket"],
                "estimated_fuel_lph": float(item["estimated_fuel_lph"]),
            }
            for item in trend
        ],
        "vehicle_comparison": comparison,
        "readiness_breakdown": readiness_breakdown,
        "vehicle_options": [
            {
                "vehicle_id": row["vehicle_id"],
                "vehicle_name": row["vehicle_name"],
                "plate_number": row["plate_number"],
                "device_id": row["device_id"],
            }
            for row in rows
        ],
        "vehicle_pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": len(table_rows),
            "total_pages": total_pages,
            "start": start_index + 1 if table_rows else 0,
            "end": min(start_index + page_size, len(table_rows)),
        },
        "vehicles": page_rows,
    }
