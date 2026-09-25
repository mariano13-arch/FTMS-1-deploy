from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from ml.fuel_rate_resolver import FuelRateResolution
from transport_requests.fuel_estimation import estimate_trip_fuel


MODEL_NAME = "FTMS XGBoost Fuel Consumption Estimator"
MODEL_VERSION = "experiment-3-tuned"


def resolution(
    basis="CURRENT_AI",
    rate=Decimal("4.2000"),
    *,
    source_timestamp=None,
    sample_count=0,
    reason="TEST_RESOLUTION",
):
    return FuelRateResolution(
        basis=basis,
        fuel_rate_lph=rate,
        source_timestamp=source_timestamp,
        history_sample_count=sample_count,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        reason=reason,
    )


class TripFuelEstimationTests(SimpleTestCase):
    def estimate(self, resolved, duration):
        with patch(
            "transport_requests.fuel_estimation.resolve_vehicle_fuel_rate",
            return_value=resolved,
        ) as resolver:
            vehicle = Mock()
            result = estimate_trip_fuel(vehicle, duration)
        resolver.assert_called_once_with(vehicle)
        return result

    def test_current_ai_uses_seconds_as_hours_and_preserves_metadata(self):
        timestamp = datetime(2026, 9, 24, 1, 2, 3, tzinfo=UTC)
        result = self.estimate(
            resolution(source_timestamp=timestamp),
            2700,
        )

        self.assertEqual(result.basis, "CURRENT_AI")
        self.assertEqual(result.fuel_rate_lph, Decimal("4.2000"))
        self.assertEqual(result.travel_time_seconds, Decimal("2700"))
        self.assertEqual(result.estimated_fuel_liters, Decimal("3.1500"))
        self.assertEqual(result.source_timestamp, timestamp)
        self.assertEqual(result.model_name, MODEL_NAME)
        self.assertEqual(result.model_version, MODEL_VERSION)

    def test_historical_baseline_calculates_liters_and_passes_sample_count(self):
        result = self.estimate(
            resolution(
                basis="HISTORICAL_AI_BASELINE",
                rate=Decimal("6.0000"),
                sample_count=12,
            ),
            1800,
        )

        self.assertEqual(result.basis, "HISTORICAL_AI_BASELINE")
        self.assertEqual(result.fuel_rate_lph, Decimal("6.0000"))
        self.assertEqual(result.estimated_fuel_liters, Decimal("3.0000"))
        self.assertEqual(result.history_sample_count, 12)

    def test_fleet_reference_baseline_uses_same_formula_without_fake_history(self):
        result = self.estimate(
            resolution(
                basis="FLEET_REFERENCE_BASELINE",
                rate=Decimal("7.0000"),
                sample_count=0,
            ),
            1800,
        )
        self.assertEqual(result.basis, "FLEET_REFERENCE_BASELINE")
        self.assertEqual(result.estimated_fuel_liters, Decimal("3.5000"))
        self.assertEqual(result.history_sample_count, 0)
        self.assertIsNone(result.source_timestamp)

    def test_unavailable_rate_never_substitutes_a_value(self):
        result = self.estimate(
            resolution(
                basis="UNAVAILABLE",
                rate=None,
                reason="INSUFFICIENT_ELIGIBLE_SAME_VEHICLE_HISTORY",
            ),
            900,
        )

        self.assertEqual(result.basis, "UNAVAILABLE")
        self.assertIsNone(result.fuel_rate_lph)
        self.assertIsNone(result.estimated_fuel_liters)
        self.assertEqual(
            result.reason, "INSUFFICIENT_ELIGIBLE_SAME_VEHICLE_HISTORY"
        )

    def test_zero_seconds_produces_zero_liters(self):
        result = self.estimate(resolution(), 0)
        self.assertEqual(result.estimated_fuel_liters, Decimal("0.0000"))

    def test_invalid_durations_are_rejected(self):
        for value in (None, -1, True, "60", float("nan"), float("inf"), Decimal("NaN")):
            with self.subTest(value=value):
                result = self.estimate(resolution(), value)
                self.assertEqual(result.basis, "UNAVAILABLE")
                self.assertIsNone(result.travel_time_seconds)
                self.assertIsNone(result.estimated_fuel_liters)
                self.assertEqual(result.reason, "INVALID_TRAFFIC_AWARE_TRAVEL_TIME")

    def test_liters_are_returned_at_four_decimal_places_without_changing_rate(self):
        rate = Decimal("7.123456")
        result = self.estimate(resolution(rate=rate), 1)

        self.assertEqual(result.fuel_rate_lph, rate)
        self.assertEqual(result.estimated_fuel_liters, Decimal("0.0020"))

    def test_distance_and_traffic_delay_are_not_service_inputs(self):
        with self.assertRaises(TypeError):
            estimate_trip_fuel(Mock(), 3600, distance_meters=1000)
        with self.assertRaises(TypeError):
            estimate_trip_fuel(Mock(), 3600, traffic_delay_seconds=600)
