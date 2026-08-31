import json
import math
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from ml.maintenance import contracts, load_model, predict, readiness


def median_inputs():
    return {
        name: spec["development_data_range"]["median"]
        for name, spec in contracts()[1]["features"].items()
    }


class MaintenanceContractTests(SimpleTestCase):
    @classmethod
    def tearDownClass(cls):
        load_model.cache_clear()
        super().tearDownClass()

    def test_native_booster_and_model_contract(self):
        booster = load_model()
        self.assertEqual(booster.__class__.__name__, "Booster")
        self.assertEqual(booster.feature_names, ["MAP", "TPS", "RPM", "Speed"])
        self.assertEqual(booster.num_features(), 4)
        config = json.loads(booster.save_config())
        self.assertEqual(config["learner"]["objective"]["name"], "binary:logistic")
        meta, feature, response = contracts()
        self.assertEqual(feature["feature_order"], ["MAP", "TPS", "RPM", "Speed"])
        self.assertEqual(meta["decision_threshold"], feature["decision_threshold"])
        self.assertEqual(feature["decision_threshold"], response["decision_threshold"])

    def test_readiness_is_not_live_obd_ready(self):
        state = readiness()
        self.assertEqual(state["deployment_state"], "research_candidate")
        self.assertFalse(state["direct_obd_feed_allowed"])
        self.assertFalse(state["production_ready"])
        self.assertFalse(state["unit_scaling_verified"])
        self.assertFalse(state["vehicle_compatibility_verified"])

    def test_direct_obd_is_blocked(self):
        for source in ("direct_obd", "validated_adapter"):
            result = predict(median_inputs(), source)
            self.assertEqual(result["status"], "prediction_blocked")

    def test_research_replay_returns_finite_score_and_preserves_output_contract(self):
        result = predict(median_inputs(), "research_replay")
        self.assertEqual(result["status"], "prediction_available")
        self.assertTrue(math.isfinite(result["model_risk_score"]))
        self.assertEqual(result["score_semantics"], "uncalibrated_model_score")
        self.assertTrue(result["mechanic_confirmation_required"])
        self.assertFalse(result["specific_component_diagnosis"])
        self.assertFalse(result["remaining_useful_life_estimation"])

    def test_classification_uses_threshold_inclusive_at_052(self):
        for score, expected in ((0.52, "Maintenance risk"), (0.519999, "Healthy")):
            model = Mock()
            model.predict.return_value = [score]
            with patch("ml.maintenance.load_model", return_value=model):
                result = predict(median_inputs(), "research_replay")
            self.assertEqual(result["classification"], expected)
            self.assertEqual(result["model_risk_score"], score)

    def test_invalid_and_abstained_inputs(self):
        base = median_inputs()
        self.assertEqual(
            predict({**base, "extra": 1}, "research_replay")["status"],
            "invalid_input",
        )
        for value in (True, "not-a-number", float("nan"), float("inf"), 0.452):
            with self.subTest(value=value):
                self.assertEqual(
                    predict({**base, "MAP": value}, "research_replay")["status"],
                    "invalid_input",
                )
        missing_speed = {key: value for key, value in base.items() if key != "Speed"}
        self.assertEqual(
            predict(missing_speed, "research_replay")["status"],
            "prediction_blocked",
        )
        self.assertEqual(
            predict({**base, "MAP": 0.95}, "research_replay")["status"],
            "abstained",
        )


class MaintenanceApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        user = get_user_model().objects.create_user(username="maintenance-staff", is_staff=True)
        StaffProfile.objects.create(user=user, role=StaffProfile.Role.FLEET_MANAGER)
        self.client.force_authenticate(user)

    def test_staff_can_read_model_info_and_readiness(self):
        info = self.client.get("/api/v1/analytics/maintenance/model-info/")
        self.assertEqual(info.status_code, 200)
        self.assertEqual(info.json()["features"], ["MAP", "TPS", "RPM", "Speed"])
        response = self.client.get("/api/v1/analytics/maintenance/readiness/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deployment_state"], "research_candidate")
        self.assertFalse(response.json()["production_ready"])

    def test_predict_api_cannot_bypass_source_restrictions(self):
        for source, expected in (
            ("direct_obd", "prediction_blocked"),
            ("validated_adapter", "prediction_blocked"),
            ("research_replay", "prediction_available"),
        ):
            response = self.client.post(
                "/api/v1/analytics/maintenance/predict/",
                {"inputs": median_inputs(), "source_mode": source},
                format="json",
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], expected)
