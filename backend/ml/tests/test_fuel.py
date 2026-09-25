from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Vehicle
from ml.fuel import (
    VALIDATED_TELEMETRY_SOURCE_MODE,
    contract,
    load_model,
    model_info,
    operational_readiness,
    operational_telemetry_inputs,
    predict_fuel,
)
from ml.models import FuelPrediction
from telemetry.models import TelemetryEvent


def complete_inputs():
    return {
        "Vehicle_Speed_km_per_h": 60,
        "Engine_RPM_RPM": 2000,
        "Absolute_Load_pct": 45,
        "OAT_DegC": 30,
        "Short_Term_Fuel_Trim_Bank_1_pct": 1.5,
        "Short_Term_Fuel_Trim_Bank_2_pct": 0.5,
        "Long_Term_Fuel_Trim_Bank_1_pct": -1,
        "Long_Term_Fuel_Trim_Bank_2_pct": 0,
        "Generalized_Weight": 1500,
    }


class FuelInferenceTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        load_model.cache_clear()
        super().tearDownClass()

    def test_selected_model_loads_and_matches_contract(self):
        model = load_model()

        self.assertEqual(model.__class__.__name__, "XGBRegressor")
        self.assertEqual(model.get_booster().feature_names, contract()["features"])
        self.assertEqual(model.n_estimators, 350)
        self.assertEqual(model_info()["availability"], "available")

    def test_complete_input_produces_numeric_estimate_in_exact_feature_order(self):
        values = complete_inputs()
        reversed_values = dict(reversed(list(values.items())))
        recorder = Mock()
        recorder.predict.return_value = [2.75]

        with patch("ml.fuel.load_model", return_value=recorder):
            result = predict_fuel(
                reversed_values,
                input_timestamp=datetime(2026, 8, 26, tzinfo=UTC),
            )

        recorder.predict.assert_called_once_with(
            [[float(values[name]) for name in contract()["features"]]]
        )
        self.assertEqual(result["status"], "prediction_available")
        self.assertEqual(result["estimated_fuel_lph"], 2.75)
        self.assertTrue(result["is_estimate"])

        actual_result = predict_fuel(values)
        self.assertEqual(actual_result["status"], "prediction_available")
        self.assertIsInstance(actual_result["estimated_fuel_lph"], float)

    def test_missing_inputs_block_without_loading_or_imputing(self):
        with patch("ml.fuel.load_model") as loader:
            result = predict_fuel({"Vehicle_Speed_km_per_h": 30})

        loader.assert_not_called()
        self.assertEqual(result["status"], "prediction_blocked")
        self.assertIsNone(result["estimated_fuel_lph"])
        self.assertNotIn("Vehicle_Speed_km_per_h", result["missing_features"])
        self.assertEqual(result["inputs"], {})

    def test_invalid_values_and_leakage_fields_are_rejected(self):
        for invalid_value in ("not-a-number", float("nan"), float("inf"), True):
            with self.subTest(value=invalid_value):
                inputs = complete_inputs()
                inputs["OAT_DegC"] = invalid_value
                result = predict_fuel(inputs)
                self.assertEqual(result["status"], "invalid_input")
                self.assertIn("OAT_DegC", result["invalid_features"])

        leakage = predict_fuel(
            {
                "Vehicle_Speed_km_per_h": 30,
                "Engine_RPM_RPM": 1500,
                "MAF_g_per_sec": 12,
            }
        )
        self.assertEqual(leakage["status"], "invalid_input")
        self.assertEqual(leakage["unexpected_features"], ["MAF_g_per_sec"])


class FuelAnalyticsApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="fuel-manager", password="test", is_staff=True
        )
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.FLEET_MANAGER)
        self.client.force_authenticate(self.user)
        self.vehicle = Vehicle.objects.create(
            device_id="FUEL-001",
            plate_number="FUEL-001",
            display_name="Fuel Analytics Van",
        )

    def create_telemetry(self, vehicle=None, *, event_id="fuel-readiness-1", rpm=1750):
        return TelemetryEvent.objects.create(
            schema_version="1.0",
            event_id=event_id,
            sequence_number=1,
            vehicle=vehicle or self.vehicle,
            recorded_at=timezone.now(),
            location=Point(121.02, 14.56, srid=4326),
            gnss_speed_kph=38.2,
            rpm=rpm,
            coolant_c=82,
            engine_load_pct=34,
            driving_event=TelemetryEvent.DrivingEvent.NORMAL,
        )

    def test_model_info_and_prediction_endpoints_require_staff(self):
        info = self.client.get("/api/v1/analytics/fuel/model-info/")
        self.assertEqual(info.status_code, 200)
        self.assertEqual(info.json()["metrics"]["mae_lph"], 1.0523)
        self.assertEqual(info.json()["model_role"], "Selected simpler deployable candidate")
        prediction = self.client.post(
            "/api/v1/analytics/fuel/predict/", complete_inputs(), format="json"
        )
        self.assertEqual(prediction.status_code, 200)
        self.assertEqual(prediction.json()["status"], "prediction_available")
        self.assertTrue(prediction.json()["is_estimate"])

        self.client.force_authenticate(user=None)
        for url in (
            "/api/v1/analytics/fuel/model-info/",
            "/api/v1/analytics/fuel/readiness/",
            "/api/v1/analytics/fuel/dashboard/",
            "/api/v1/analytics/fuel/predict/",
        ):
            with self.subTest(url=url):
                response = (
                    self.client.post(url, {}, format="json")
                    if url.endswith("predict/")
                    else self.client.get(url)
                )
                self.assertIn(response.status_code, (401, 403))

    def test_prediction_endpoint_blocks_missing_and_rejects_invalid_inputs(self):
        blocked = self.client.post(
            "/api/v1/analytics/fuel/predict/",
            {"Vehicle_Speed_km_per_h": 30},
            format="json",
        )
        self.assertEqual(blocked.status_code, 200)
        self.assertEqual(blocked.json()["status"], "prediction_blocked")
        self.assertIsNone(blocked.json()["estimated_fuel_lph"])

        invalid = self.client.post(
            "/api/v1/analytics/fuel/predict/",
            {**complete_inputs(), "log_MAF": 1},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()["status"], "invalid_input")

    def test_readiness_uses_real_telemetry_and_never_predicts_when_incomplete(self):
        event = self.create_telemetry()

        readiness = operational_readiness()
        self.assertEqual(readiness["latest_telemetry"]["event_id"], event.event_id)
        self.assertEqual(readiness["latest_operational_result"]["status"], "prediction_blocked")
        self.assertIsNone(readiness["latest_operational_result"]["estimated_fuel_lph"])
        self.assertIn(
            "Absolute_Load_pct",
            readiness["latest_operational_result"]["missing_features"],
        )
        engine_load = next(
            item for item in readiness["inputs"] if item["feature"] == "Absolute_Load_pct"
        )
        self.assertEqual(engine_load["status"], "unverified")

    def test_vehicle_inference_uses_only_authoritative_telemetry_and_blocks(self):
        event = self.create_telemetry()
        self.assertEqual(
            operational_telemetry_inputs(event),
            {
                "Vehicle_Speed_km_per_h": 38.2,
                "Engine_RPM_RPM": 1750.0,
            },
        )

        supplied = self.client.post(
            "/api/v1/analytics/fuel/predict/",
            {
                **complete_inputs(),
                "vehicle_id": self.vehicle.pk,
                "input_timestamp": event.recorded_at.isoformat(),
            },
            format="json",
        )
        self.assertEqual(supplied.status_code, 400)
        self.assertIn("derives model inputs", supplied.json()["inputs"])

        payload = {
            "vehicle_id": self.vehicle.pk,
            "input_timestamp": event.recorded_at.isoformat(),
        }
        first = self.client.post("/api/v1/analytics/fuel/predict/", payload, format="json")
        second = self.client.post("/api/v1/analytics/fuel/predict/", payload, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["status"], "prediction_blocked")
        self.assertEqual(first.json()["input_timestamp"], event.recorded_at.isoformat())
        self.assertIn("Absolute_Load_pct", first.json()["missing_features"])
        self.assertFalse(first.json()["history_persisted"])
        self.assertFalse(second.json()["history_persisted"])
        self.assertEqual(FuelPrediction.objects.count(), 0)

    def test_another_vehicles_telemetry_cannot_satisfy_vehicle_inference(self):
        other = Vehicle.objects.create(
            device_id="FUEL-OTHER",
            plate_number="FUEL-OTHER",
            display_name="Other Fuel Van",
        )
        event = self.create_telemetry(other, event_id="fuel-other-source")

        response = self.client.post(
            "/api/v1/analytics/fuel/predict/",
            {
                "vehicle_id": self.vehicle.pk,
                "input_timestamp": event.recorded_at.isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(FuelPrediction.objects.count(), 0)

    def test_blocked_or_unverified_source_prediction_is_not_persisted(self):
        event = self.create_telemetry()
        blocked = self.client.post(
            "/api/v1/analytics/fuel/predict/",
            {
                "vehicle_id": self.vehicle.pk,
                "input_timestamp": event.recorded_at.isoformat(),
            },
            format="json",
        )
        missing_source = self.client.post(
            "/api/v1/analytics/fuel/predict/",
            {
                **complete_inputs(),
                "vehicle_id": self.vehicle.pk,
                "input_timestamp": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            },
            format="json",
        )

        self.assertEqual(blocked.json()["status"], "prediction_blocked")
        self.assertFalse(blocked.json()["history_persisted"])
        self.assertEqual(missing_source.status_code, 400)
        self.assertEqual(FuelPrediction.objects.count(), 0)

    def test_dashboard_uses_only_real_successful_history_and_filters_trend(self):
        ready_event = self.create_telemetry()
        blocked_vehicle = Vehicle.objects.create(
            device_id="FUEL-002",
            plate_number="FUEL-002",
            display_name="Blocked Fuel Van",
        )
        self.create_telemetry(
            blocked_vehicle,
            event_id="fuel-readiness-2",
            rpm=None,
        )
        Vehicle.objects.create(
            device_id="FUEL-003",
            plate_number="FUEL-003",
            display_name="No Telemetry Van",
        )
        FuelPrediction.objects.create(
            vehicle=self.vehicle,
            input_timestamp=ready_event.recorded_at,
            estimated_fuel_lph=2.5,
            model_name=contract()["model_name"],
            model_version=contract()["model_version"],
            source_mode=VALIDATED_TELEMETRY_SOURCE_MODE,
            validated_inputs=complete_inputs(),
        )

        response = self.client.get("/api/v1/analytics/fuel/dashboard/?range=24h")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["summary"]["vehicle_count"], 3)
        self.assertEqual(data["summary"]["prediction_ready_count"], 1)
        self.assertEqual(data["summary"]["prediction_blocked_count"], 2)
        self.assertEqual(data["summary"]["average_estimated_fuel_lph"], 2.5)
        self.assertEqual(data["readiness_breakdown"]["ready"], 1)
        self.assertEqual(data["readiness_breakdown"]["blocked"], 1)
        self.assertEqual(data["readiness_breakdown"]["no_telemetry"], 1)
        self.assertEqual(len(data["trend"]), 1)
        self.assertEqual(len(data["vehicle_comparison"]), 1)
        ready_row = next(row for row in data["vehicles"] if row["vehicle_id"] == self.vehicle.pk)
        self.assertEqual(ready_row["input_readiness"]["available_count"], 9)
        blocked_row = next(
            row for row in data["vehicles"] if row["vehicle_id"] == blocked_vehicle.pk
        )
        self.assertIsNone(blocked_row["latest_estimated_fuel_lph"])
        self.assertEqual(blocked_row["prediction_status"], "prediction_blocked")

        self.create_telemetry(event_id="fuel-readiness-newer")
        stale = self.client.get("/api/v1/analytics/fuel/dashboard/?range=24h").json()
        stale_row = next(row for row in stale["vehicles"] if row["vehicle_id"] == self.vehicle.pk)
        self.assertEqual(stale_row["prediction_status"], "prediction_blocked")
        self.assertEqual(len(stale["vehicle_comparison"]), 0)

        filtered = self.client.get(
            f"/api/v1/analytics/fuel/dashboard/?range=7d&vehicle={blocked_vehicle.pk}"
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.json()["filters"]["range"], "7d")
        self.assertEqual(filtered.json()["trend"], [])

    def test_dashboard_excludes_unverified_api_history_without_deleting_it(self):
        event = self.create_telemetry()
        legacy = FuelPrediction.objects.create(
            vehicle=self.vehicle,
            input_timestamp=event.recorded_at,
            estimated_fuel_lph=8.5,
            model_name=contract()["model_name"],
            model_version=contract()["model_version"],
            source_mode="explicit_validated_api",
            validated_inputs=complete_inputs(),
        )

        data = self.client.get("/api/v1/analytics/fuel/dashboard/?range=30d").json()

        self.assertEqual(data["trend"], [])
        self.assertEqual(data["vehicle_comparison"], [])
        self.assertEqual(data["summary"]["prediction_ready_count"], 0)
        self.assertEqual(data["vehicles"][0]["prediction_status"], "prediction_blocked")
        self.assertEqual(data["vehicles"][0]["prediction_source_label"], "Unverified API Inputs")
        self.assertEqual(data["vehicles"][0]["latest_prediction_inputs"], [])
        self.assertTrue(FuelPrediction.objects.filter(pk=legacy.pk).exists())

    def test_dashboard_time_windows_and_vehicle_filter_use_persisted_history(self):
        now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
        for age, value in ((2, 1.0), (48, 2.0), (360, 3.0), (960, 4.0)):
            FuelPrediction.objects.create(
                vehicle=self.vehicle,
                input_timestamp=now - timedelta(hours=age),
                estimated_fuel_lph=value,
                model_name=contract()["model_name"],
                model_version=contract()["model_version"],
                source_mode=VALIDATED_TELEMETRY_SOURCE_MODE,
                validated_inputs=complete_inputs(),
            )
        other = Vehicle.objects.create(
            device_id="FUEL-FILTER",
            plate_number="FUEL-FILTER",
            display_name="Filter Fuel Van",
        )
        FuelPrediction.objects.create(
            vehicle=other,
            input_timestamp=now - timedelta(hours=1),
            estimated_fuel_lph=9.0,
            model_name=contract()["model_name"],
            model_version=contract()["model_version"],
            source_mode=VALIDATED_TELEMETRY_SOURCE_MODE,
            validated_inputs=complete_inputs(),
        )

        with patch("ml.dashboard.timezone.now", return_value=now):
            day = self.client.get("/api/v1/analytics/fuel/dashboard/?range=24h").json()
            week = self.client.get("/api/v1/analytics/fuel/dashboard/?range=7d").json()
            month = self.client.get("/api/v1/analytics/fuel/dashboard/?range=30d").json()
            filtered = self.client.get(
                f"/api/v1/analytics/fuel/dashboard/?range=30d&vehicle={self.vehicle.pk}"
            ).json()

        self.assertEqual(len(day["trend"]), 2)
        self.assertEqual(len(week["trend"]), 2)
        self.assertEqual(len(month["trend"]), 3)
        self.assertEqual(len(filtered["trend"]), 3)
        self.assertNotIn(9.0, [point["estimated_fuel_lph"] for point in filtered["trend"]])

    def test_dashboard_empty_history_and_invalid_filters(self):
        response = self.client.get("/api/v1/analytics/fuel/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["summary"]["average_estimated_fuel_lph"])
        self.assertEqual(response.json()["trend"], [])
        self.assertEqual(response.json()["vehicle_comparison"], [])
        self.assertEqual(
            self.client.get("/api/v1/analytics/fuel/dashboard/?range=year").status_code,
            400,
        )

    def test_dashboard_labels_demo_prediction_without_counting_operational_ready(self):
        demo = Vehicle.objects.create(
            device_id="DEMO-001",
            plate_number="DEMO-001",
            display_name="Sprint 1 Demo Vehicle",
        )
        event = self.create_telemetry(
            demo,
            event_id="fuel-demo-dashboard",
            rpm=1900,
        )
        inputs = {**complete_inputs(), "Vehicle_Speed_km_per_h": 38.2, "Engine_RPM_RPM": 1900}
        FuelPrediction.objects.create(
            vehicle=demo,
            input_timestamp=event.recorded_at,
            estimated_fuel_lph=3.25,
            model_name=contract()["model_name"],
            model_version=contract()["model_version"],
            source_mode="demo_seed",
            validated_inputs=inputs,
        )

        data = self.client.get("/api/v1/analytics/fuel/dashboard/?range=24h").json()

        self.assertTrue(data["demo_data_present"])
        self.assertIn("not operational", data["demo_data_note"])
        self.assertEqual(data["summary"]["prediction_ready_count"], 0)
        self.assertEqual(data["summary"]["demo_ready_count"], 1)
        self.assertIsNone(data["summary"]["average_estimated_fuel_lph"])
        self.assertEqual(data["summary"]["demo_average_estimated_fuel_lph"], 3.25)
        self.assertEqual(data["readiness_breakdown"]["demo_ready"], 1)
        row = next(item for item in data["vehicles"] if item["vehicle_id"] == demo.pk)
        self.assertEqual(row["prediction_status"], "demo_ready")
        self.assertEqual(row["prediction_source_mode"], "demo_seed")
        self.assertEqual(row["prediction_source_label"], "Demo/Test Inputs")
        self.assertTrue(row["is_demo_prediction"])
        self.assertEqual(len(row["latest_prediction_inputs"]), 9)
        sources = {item["feature"]: item["source"] for item in row["latest_prediction_inputs"]}
        self.assertEqual(sources["Vehicle_Speed_km_per_h"], "Actual persisted telemetry")
        self.assertEqual(sources["Engine_RPM_RPM"], "Actual persisted telemetry")
        self.assertEqual(sources["Absolute_Load_pct"], "Demo/Test Input")
        comparison = next(
            item for item in data["vehicle_comparison"] if item["vehicle_id"] == demo.pk
        )
        self.assertTrue(comparison["is_demo_prediction"])
        self.assertEqual(comparison["source_mode"], "demo_seed")

    def test_dashboard_vehicle_rows_are_paginated_without_changing_fleet_totals(self):
        for index in range(12):
            Vehicle.objects.create(
                device_id=f"PAGE-{index:03d}",
                plate_number=f"PAGE-{index:03d}",
                display_name=f"Paged Vehicle {index:02d}",
            )

        response = self.client.get("/api/v1/analytics/fuel/dashboard/?page=2&page_size=10")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["summary"]["vehicle_count"], 13)
        self.assertEqual(data["vehicle_pagination"]["total_count"], 13)
        self.assertEqual(data["vehicle_pagination"]["page"], 2)
        self.assertEqual(data["vehicle_pagination"]["start"], 11)
        self.assertEqual(data["vehicle_pagination"]["end"], 13)
        self.assertEqual(len(data["vehicles"]), 3)
        self.assertEqual(len(data["vehicle_options"]), 13)
        searched = self.client.get(
            "/api/v1/analytics/fuel/dashboard/?search=Paged%20Vehicle%2011&page_size=50"
        )
        self.assertEqual(searched.status_code, 200)
        searched_data = searched.json()
        self.assertEqual(searched_data["summary"]["vehicle_count"], 13)
        self.assertEqual(searched_data["vehicle_pagination"]["total_count"], 1)
        self.assertEqual(len(searched_data["vehicles"]), 1)
        self.assertEqual(searched_data["vehicles"][0]["device_id"], "PAGE-011")
        self.assertEqual(searched_data["vehicle_options"][0]["device_id"], "FUEL-001")
        cleared = self.client.get("/api/v1/analytics/fuel/dashboard/?search=&page_size=50")
        self.assertEqual(cleared.json()["vehicle_pagination"]["total_count"], 13)
        self.assertEqual(
            self.client.get("/api/v1/analytics/fuel/dashboard/?page_size=501").status_code,
            400,
        )
