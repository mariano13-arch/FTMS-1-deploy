from datetime import timedelta
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.test import TestCase
from django.utils import timezone

from fleet.models import Vehicle, VehicleFuelReferenceBaseline
from ml.fuel import VALIDATED_TELEMETRY_SOURCE_MODE, contract
from ml.fuel_rate_resolver import resolve_vehicle_fuel_rate
from ml.models import FuelPrediction
from telemetry.models import TelemetryDevice, TelemetryEvent


def complete_inputs():
    return {feature: index + 1.0 for index, feature in enumerate(contract()["features"])}


class FuelRateResolverTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.vehicle = Vehicle.objects.create(
            device_id="RATE-001", plate_number="RATE-001", display_name="Rate Vehicle"
        )
        self.other_vehicle = Vehicle.objects.create(
            device_id="RATE-002", plate_number="RATE-002", display_name="Other Vehicle"
        )
        self.devices = {}

    def telemetry(self, timestamp, *, vehicle=None, simulated=False):
        vehicle = vehicle or self.vehicle
        device = self.devices.get(vehicle.pk)
        if device is None:
            device = TelemetryDevice.objects.create(device_id=f"TEL-{vehicle.device_id}")
            self.devices[vehicle.pk] = device
        sequence = TelemetryEvent.objects.filter(vehicle=vehicle).count() + 1
        return TelemetryEvent.objects.create(
            schema_version="1.0",
            event_id=f"rate-{vehicle.pk}-{sequence}",
            sequence_number=sequence,
            device=device,
            vehicle=vehicle,
            recorded_at=timestamp,
            location=Point(121.0, 14.5),
            position_source=(
                TelemetryEvent.PositionSource.SIMULATED_TEST
                if simulated
                else TelemetryEvent.PositionSource.GNSS
            ),
            gnss_speed_kph=None if simulated else Decimal("40.00"),
            rpm=1800,
            obd_source=(
                TelemetryEvent.ObdSource.SIMULATED_TEST
                if simulated
                else TelemetryEvent.ObdSource.PHYSICAL_OBD
            ),
        )

    def prediction(
        self,
        timestamp,
        rate,
        *,
        vehicle=None,
        source=VALIDATED_TELEMETRY_SOURCE_MODE,
        model_version=None,
        inputs=None,
        simulated=False,
    ):
        vehicle = vehicle or self.vehicle
        self.telemetry(timestamp, vehicle=vehicle, simulated=simulated)
        metadata = contract()
        return FuelPrediction.objects.create(
            vehicle=vehicle,
            input_timestamp=timestamp,
            estimated_fuel_lph=rate,
            model_name=metadata["model_name"],
            model_version=model_version or metadata["model_version"],
            source_mode=source,
            validated_inputs=complete_inputs() if inputs is None else inputs,
        )

    def historical_predictions(self, rates):
        for index, rate in enumerate(rates, start=1):
            self.prediction(self.now - timedelta(minutes=5 + index), rate)

    def test_fresh_genuine_prediction_is_current_and_preserves_rate(self):
        prediction = self.prediction(
            self.now - timedelta(minutes=2), Decimal("3.4567")
        )

        result = resolve_vehicle_fuel_rate(self.vehicle, now=self.now)

        self.assertEqual(result.basis, "CURRENT_AI")
        self.assertEqual(result.fuel_rate_lph, prediction.estimated_fuel_lph)
        self.assertEqual(result.source_timestamp, prediction.input_timestamp)
        self.assertEqual(result.history_sample_count, 0)

    def test_prediction_older_than_five_minutes_is_not_current(self):
        self.prediction(self.now - timedelta(minutes=6), Decimal("2.0"))

        result = resolve_vehicle_fuel_rate(self.vehicle, now=self.now)

        self.assertEqual(result.basis, "UNAVAILABLE")

    def test_five_historical_predictions_use_correct_median(self):
        self.historical_predictions(
            [Decimal("8"), Decimal("2"), Decimal("5"), Decimal("3"), Decimal("7")]
        )

        result = resolve_vehicle_fuel_rate(self.vehicle, now=self.now)

        self.assertEqual(result.basis, "HISTORICAL_AI_BASELINE")
        self.assertEqual(result.fuel_rate_lph, Decimal("5"))
        self.assertEqual(result.history_sample_count, 5)

    def test_only_latest_twenty_eligible_predictions_are_used(self):
        self.historical_predictions(
            [Decimal(value) for value in range(1, 21)]
            + [Decimal("1000") for _ in range(5)]
        )

        result = resolve_vehicle_fuel_rate(self.vehicle, now=self.now)

        self.assertEqual(result.basis, "HISTORICAL_AI_BASELINE")
        self.assertEqual(result.fuel_rate_lph, Decimal("10.5"))
        self.assertEqual(result.history_sample_count, 20)

    def test_fewer_than_five_historical_predictions_are_unavailable(self):
        self.historical_predictions([Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")])
        self.assertEqual(
            resolve_vehicle_fuel_rate(self.vehicle, now=self.now).basis,
            "UNAVAILABLE",
        )

    def test_demo_future_incomplete_negative_and_other_version_are_excluded(self):
        invalid_cases = [
            {"source": "demo_seed"},
            {"timestamp": self.now + timedelta(minutes=1)},
            {"inputs": {"Vehicle_Speed_km_per_h": 30}},
            {"rate": Decimal("-1")},
            {"model_version": "other-version"},
        ]
        for index, overrides in enumerate(invalid_cases, start=1):
            timestamp = overrides.pop("timestamp", self.now - timedelta(minutes=10 + index))
            rate = overrides.pop("rate", Decimal(index))
            self.prediction(timestamp, rate, **overrides)

        result = resolve_vehicle_fuel_rate(self.vehicle, now=self.now)

        self.assertEqual(result.basis, "UNAVAILABLE")

    def test_other_vehicle_predictions_are_excluded(self):
        for index in range(5):
            self.prediction(
                self.now - timedelta(minutes=10 + index),
                Decimal(index + 1),
                vehicle=self.other_vehicle,
            )
        self.assertEqual(
            resolve_vehicle_fuel_rate(self.vehicle, now=self.now).basis,
            "UNAVAILABLE",
        )

    def test_simulated_telemetry_provenance_is_excluded(self):
        for index in range(5):
            self.prediction(
                self.now - timedelta(minutes=10 + index),
                Decimal(index + 1),
                simulated=True,
            )
        self.assertEqual(
            resolve_vehicle_fuel_rate(self.vehicle, now=self.now).basis,
            "UNAVAILABLE",
        )

    def test_current_requires_prediction_to_match_latest_vehicle_telemetry(self):
        self.prediction(self.now - timedelta(minutes=2), Decimal("3.25"))
        self.telemetry(self.now - timedelta(minutes=1))

        result = resolve_vehicle_fuel_rate(self.vehicle, now=self.now)

        self.assertEqual(result.basis, "UNAVAILABLE")

    def reference(self, rate="7.2500"):
        return VehicleFuelReferenceBaseline.objects.create(
            vehicle=self.vehicle,
            reference_fuel_rate_lph=rate,
            provenance="CAPSTONE_REFERENCE",
            basis_version="CAPSTONE_FLEET_REFERENCE_V1",
        )

    def test_reference_is_used_only_without_operational_evidence(self):
        self.reference()
        result = resolve_vehicle_fuel_rate(self.vehicle, now=self.now)
        self.assertEqual(result.basis, "FLEET_REFERENCE_BASELINE")
        self.assertEqual(result.fuel_rate_lph, Decimal("7.2500"))
        self.assertEqual(result.provenance, "CAPSTONE_REFERENCE")
        self.assertIsNone(result.source_timestamp)
        self.assertEqual(result.history_sample_count, 0)

    def test_current_ai_overrides_reference(self):
        self.reference()
        self.prediction(self.now - timedelta(minutes=2), Decimal("3.4567"))
        result = resolve_vehicle_fuel_rate(self.vehicle, now=self.now)
        self.assertEqual(result.basis, "CURRENT_AI")
        self.assertNotEqual(result.provenance, "CAPSTONE_REFERENCE")

    def test_historical_baseline_overrides_reference(self):
        self.reference()
        self.historical_predictions(
            [Decimal("8"), Decimal("2"), Decimal("5"), Decimal("3"), Decimal("7")]
        )
        result = resolve_vehicle_fuel_rate(self.vehicle, now=self.now)
        self.assertEqual(result.basis, "HISTORICAL_AI_BASELINE")
        self.assertNotEqual(result.provenance, "CAPSTONE_REFERENCE")
