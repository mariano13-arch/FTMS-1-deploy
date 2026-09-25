from datetime import datetime
from datetime import timezone as dt_timezone
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import FuelPriceRecord, Vehicle, VehicleFuelReferenceBaseline
from ml.models import FuelPrediction


class FuelReferenceReportTests(TestCase):
    endpoint = "/api/v1/reports/fuel-reference/"

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="fuel-reporter", is_staff=True)
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.FLEET_MANAGER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.vehicle = Vehicle.objects.create(
            device_id="FUEL-RPT-1",
            plate_number="FUEL-1",
            display_name="=Fuel Van",
            vehicle_type=Vehicle.VehicleType.VAN,
            fuel_type=Vehicle.FuelType.GASOLINE,
            fuel_grade=Vehicle.FuelGrade.UNLEADED_91,
        )
        self.when = datetime(2026, 9, 20, 4, tzinfo=dt_timezone.utc)

    def get(self, **params):
        return self.client.get(
            self.endpoint, {"date_from": "2026-09-20", "date_to": "2026-09-20", **params}
        )

    def test_prediction_baseline_and_price_keep_distinct_provenance(self):
        FuelPrediction.objects.create(
            vehicle=self.vehicle,
            input_timestamp=self.when,
            estimated_fuel_lph="8.3000",
            model_name="Fuel Model",
            model_version="v1",
            source_mode="validated_vehicle_telemetry",
            validated_inputs={"speed": 30},
        )
        VehicleFuelReferenceBaseline.objects.create(
            vehicle=self.vehicle,
            reference_fuel_rate_lph="8.0000",
            provenance=VehicleFuelReferenceBaseline.Provenance.CAPSTONE_REFERENCE,
            basis_version="fleet-v1",
        )
        FuelPriceRecord.objects.create(
            fuel_type=FuelPriceRecord.FuelType.GASOLINE,
            fuel_grade=Vehicle.FuelGrade.UNLEADED_91,
            price_per_liter=Decimal("61.2500"),
            currency="PHP",
            effective_at=self.when,
            provider="ShellPH",
            source_mode=FuelPriceRecord.SourceMode.MANUAL,
        )
        data = self.get().json()
        self.assertEqual(data["summary"]["eligible_predictions"], 1)
        self.assertEqual(
            data["predictions"]["results"][0]["provenance_label"],
            "Predicted · Operational telemetry",
        )
        self.assertEqual(data["baselines"]["results"][0]["provenance"], "CAPSTONE_REFERENCE")
        self.assertIn(
            "Fleet Reference Baseline", data["baselines"]["results"][0]["provenance_label"]
        )
        price = data["prices"]["results"][0]
        self.assertEqual((price["provider"], price["source_mode"]), ("ShellPH", "MANUAL"))
        self.assertTrue(
            {
                "actual_fuel_used",
                "actual_expense",
                "fuel_savings",
                "prediction_accuracy",
            }.isdisjoint(data)
        )

    def test_non_operational_prediction_does_not_inflate_eligible_kpi(self):
        FuelPrediction.objects.create(
            vehicle=self.vehicle,
            input_timestamp=self.when,
            estimated_fuel_lph="7.0000",
            model_name="Fuel Model",
            model_version="demo",
            source_mode="demo_seed",
            validated_inputs={},
        )
        data = self.get(prediction_source="demo_seed").json()
        self.assertEqual(data["summary"]["eligible_predictions"], 0)
        self.assertFalse(data["predictions"]["results"][0]["operational_source"])
        self.assertIn("Non-operational", data["predictions"]["results"][0]["provenance_label"])

    def test_csv_is_formula_safe_and_staff_access_is_preserved(self):
        VehicleFuelReferenceBaseline.objects.create(
            vehicle=self.vehicle,
            reference_fuel_rate_lph="8.0000",
            provenance=VehicleFuelReferenceBaseline.Provenance.CAPSTONE_REFERENCE,
            basis_version="=POLICY",
        )
        response = self.client.get(
            "/api/v1/reports/fuel-reference/baselines/csv/",
            {"date_from": "2026-09-20", "date_to": "2026-09-20"},
        )
        body = b"".join(response.streaming_content).decode()
        self.assertIn("'=Fuel Van", body)
        self.assertIn("'=POLICY", body)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.endpoint).status_code, 401)
