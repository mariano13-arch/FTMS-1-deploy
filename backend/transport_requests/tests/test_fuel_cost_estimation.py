from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from fleet.models import FuelPriceRecord, Vehicle
from ml.fuel_rate_resolver import FuelRateResolution
from transport_requests.fuel_cost_estimation import estimate_trip_fuel_cost


def fuel_rate(
    basis="CURRENT_AI", rate=Decimal("4.2000"), *, samples=0, reason="RATE_AVAILABLE"
):
    return FuelRateResolution(
        basis=basis,
        fuel_rate_lph=rate,
        source_timestamp=timezone.now() - timedelta(minutes=5),
        history_sample_count=samples,
        model_name="FTMS XGBoost Fuel Consumption Estimator",
        model_version="experiment-3-tuned",
        reason=reason,
    )


class TripFuelCostEstimationTests(TestCase):
    def setUp(self):
        self.now = timezone.now()

    def vehicle(self, grade="PREMIUM_95", fuel_type="GASOLINE"):
        return Vehicle.objects.create(
            device_id=f"COST-{Vehicle.objects.count()}",
            plate_number=f"COST-{Vehicle.objects.count()}",
            display_name="Cost test",
            fuel_type=fuel_type,
            fuel_grade=grade,
        )

    def price(
        self, grade="PREMIUM_95", amount="71.2500", *, provider="ShellPH",
        fuel_type="GASOLINE", active=True, effective_at=None, source="MANUAL"
    ):
        record = FuelPriceRecord.objects.create(
            fuel_type=fuel_type,
            fuel_grade=grade,
            price_per_liter=amount,
            currency="PHP",
            effective_at=effective_at or self.now - timedelta(hours=1),
            provider=provider,
            source_mode=source,
            is_active=active,
        )
        record.refresh_from_db()
        return record

    def estimate(self, vehicle, duration, resolved=None):
        resolved = resolved or fuel_rate()
        with patch(
            "transport_requests.fuel_estimation.resolve_vehicle_fuel_rate",
            return_value=resolved,
        ):
            return estimate_trip_fuel_cost(vehicle, duration)

    def test_current_ai_and_exact_shell_price_produce_decimal_cost(self):
        vehicle = self.vehicle()
        price = self.price(amount="71.2350")
        result = self.estimate(vehicle, 2700)
        self.assertEqual(result.status, "AVAILABLE")
        self.assertEqual(result.fuel_rate_basis, "CURRENT_AI")
        self.assertEqual(result.fuel_rate_lph, Decimal("4.2000"))
        self.assertEqual(result.estimated_fuel_liters, Decimal("3.1500"))
        self.assertEqual(result.estimated_fuel_cost_php, Decimal("224.39"))
        self.assertEqual(result.price_per_liter, price.price_per_liter)
        self.assertEqual(result.price_provider, "ShellPH")
        self.assertEqual(result.price_source_mode, "MANUAL")
        self.assertEqual(result.price_effective_at, price.effective_at)

    def test_historical_rate_preserves_samples_rate_and_metadata(self):
        vehicle = self.vehicle()
        self.price(amount="70.0000")
        resolved = fuel_rate(
            basis="HISTORICAL_AI_BASELINE", rate=Decimal("6.0000"), samples=12
        )
        result = self.estimate(vehicle, 1800, resolved)
        self.assertEqual(result.status, "AVAILABLE")
        self.assertEqual(result.fuel_rate_basis, "HISTORICAL_AI_BASELINE")
        self.assertEqual(result.fuel_rate_lph, Decimal("6.0000"))
        self.assertEqual(result.estimated_fuel_liters, Decimal("3.0000"))
        self.assertEqual(result.estimated_fuel_cost_php, Decimal("210.00"))
        self.assertEqual(result.history_sample_count, 12)
        self.assertEqual(result.fuel_source_timestamp, resolved.source_timestamp)

    def test_fleet_reference_baseline_uses_unchanged_cost_formula(self):
        vehicle = self.vehicle()
        self.price(amount="70.0000")
        resolved = fuel_rate(
            basis="FLEET_REFERENCE_BASELINE", rate=Decimal("6.5000"), samples=0
        )
        result = self.estimate(vehicle, 1800, resolved)
        self.assertEqual(result.status, "AVAILABLE")
        self.assertEqual(result.fuel_rate_basis, "FLEET_REFERENCE_BASELINE")
        self.assertEqual(result.estimated_fuel_liters, Decimal("3.2500"))
        self.assertEqual(result.estimated_fuel_cost_php, Decimal("227.50"))

    def test_blank_grade_is_unavailable(self):
        result = self.estimate(self.vehicle(grade=""), 3600)
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertEqual(result.reason, "FUEL_GRADE_NOT_RECORDED")
        self.assertIsNone(result.estimated_fuel_cost_php)

    def test_no_exact_shell_price_rejects_wrong_grade_and_public_sources(self):
        vehicle = self.vehicle()
        self.price(grade="UNLEADED_91")
        self.price(provider="GasWatchPH", source="EXTERNAL_CACHED")
        self.price(provider="GlobalPetrolPrices", source="EXTERNAL_CACHED")
        result = self.estimate(vehicle, 3600)
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertEqual(result.reason, "NO_VALID_PREFERRED_PARTNER_PRICE")

    def test_inactive_and_future_shell_prices_are_ignored(self):
        vehicle = self.vehicle()
        self.price(active=False)
        self.price(effective_at=self.now + timedelta(days=1))
        result = self.estimate(vehicle, 3600)
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertEqual(result.reason, "NO_VALID_PREFERRED_PARTNER_PRICE")

    def test_newest_valid_exact_shell_price_is_used(self):
        vehicle = self.vehicle()
        self.price(amount="60", effective_at=self.now - timedelta(days=2))
        newest = self.price(amount="75", effective_at=self.now - timedelta(hours=1))
        result = self.estimate(vehicle, 3600)
        self.assertEqual(result.price_per_liter, newest.price_per_liter)

    def test_invalid_duration_preserves_upstream_reason(self):
        vehicle = self.vehicle()
        self.price()
        for duration in (None, -1):
            with self.subTest(duration=duration):
                result = self.estimate(vehicle, duration)
                self.assertEqual(result.status, "UNAVAILABLE")
                self.assertEqual(result.reason, "INVALID_TRAFFIC_AWARE_TRAVEL_TIME")

    def test_unavailable_fuel_rate_preserves_reason(self):
        vehicle = self.vehicle()
        self.price()
        unavailable = fuel_rate(
            basis="UNAVAILABLE", rate=None, reason="FUEL_RATE_UNAVAILABLE"
        )
        result = self.estimate(vehicle, 3600, unavailable)
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertEqual(result.reason, "FUEL_RATE_UNAVAILABLE")
        self.assertIsNone(result.estimated_fuel_cost_php)

    def test_service_contract_has_no_ranking_inputs(self):
        vehicle = self.vehicle()
        with self.assertRaises(TypeError):
            estimate_trip_fuel_cost(vehicle, 3600, candidate_rank=1)
