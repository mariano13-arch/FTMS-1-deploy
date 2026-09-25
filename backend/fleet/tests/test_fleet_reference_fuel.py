from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from fleet.management.commands.seed_fleet_reference_fuel import REFERENCE_RATES
from fleet.models import Vehicle, VehicleFuelReferenceBaseline
from ml.fuel_rate_resolver import resolve_vehicle_fuel_rate
from ml.models import FuelPrediction
from telemetry.models import TelemetryEvent


class FleetReferenceFuelSeedTests(TestCase):
    def vehicle(self, code, vehicle_type, fuel_type, fuel_grade=""):
        return Vehicle.objects.create(
            device_id=code,
            plate_number=code,
            display_name=code,
            vehicle_type=vehicle_type,
            fuel_type=fuel_type,
            fuel_grade=fuel_grade,
        )

    def test_seed_populates_defaults_preserves_facts_and_creates_no_fake_evidence(self):
        gasoline = self.vehicle("REF-G", "SEDAN", "GASOLINE")
        diesel = self.vehicle("REF-D", "VAN", "DIESEL")
        premium_95 = self.vehicle("REF-95", "SUV", "GASOLINE", "PREMIUM_95")
        premium_97 = self.vehicle("REF-97", "SEDAN", "GASOLINE", "PREMIUM_97")
        premium_diesel = self.vehicle(
            "REF-PD", "SERVICE_TRUCK", "DIESEL", "PREMIUM_DIESEL"
        )
        blank = self.vehicle("REF-BLANK", "VAN", "")

        call_command("seed_fleet_reference_fuel", stdout=StringIO())

        for vehicle in (
            gasoline, diesel, premium_95, premium_97, premium_diesel, blank
        ):
            vehicle.refresh_from_db()
        self.assertEqual(gasoline.fuel_grade, "UNLEADED_91")
        self.assertEqual(diesel.fuel_grade, "REGULAR_DIESEL")
        self.assertEqual(premium_95.fuel_grade, "PREMIUM_95")
        self.assertEqual(premium_97.fuel_grade, "PREMIUM_97")
        self.assertEqual(premium_diesel.fuel_grade, "PREMIUM_DIESEL")
        self.assertEqual(blank.fuel_grade, "")
        self.assertFalse(
            VehicleFuelReferenceBaseline.objects.filter(vehicle=blank).exists()
        )
        self.assertEqual(FuelPrediction.objects.count(), 0)
        self.assertEqual(TelemetryEvent.objects.count(), 0)

    def test_seed_is_idempotent_and_reference_values_are_deterministic(self):
        vehicles = [
            self.vehicle(
                f"REF-{index}", vehicle_type, fuel_type
            )
            for index, (vehicle_type, fuel_type) in enumerate(REFERENCE_RATES, start=1)
        ]
        call_command("seed_fleet_reference_fuel", stdout=StringIO())
        first = dict(
            VehicleFuelReferenceBaseline.objects.values_list(
                "vehicle_id", "reference_fuel_rate_lph"
            )
        )
        call_command("seed_fleet_reference_fuel", stdout=StringIO())
        second = dict(
            VehicleFuelReferenceBaseline.objects.values_list(
                "vehicle_id", "reference_fuel_rate_lph"
            )
        )
        self.assertEqual(first, second)
        self.assertEqual(len(second), len(vehicles))
        for vehicle in vehicles:
            baseline = vehicle.fuel_reference_baseline
            self.assertEqual(
                baseline.reference_fuel_rate_lph,
                REFERENCE_RATES[(vehicle.vehicle_type, vehicle.fuel_type)],
            )
            self.assertEqual(baseline.provenance, "CAPSTONE_REFERENCE")
            self.assertTrue(baseline.is_active)

    def test_gasoline_van_gets_capstone_reference_without_fake_evidence(self):
        vehicle = self.vehicle("REF-GAS-VAN", "VAN", "GASOLINE")

        call_command("seed_fleet_reference_fuel", stdout=StringIO())
        call_command("seed_fleet_reference_fuel", stdout=StringIO())

        vehicle.refresh_from_db()
        baseline = VehicleFuelReferenceBaseline.objects.get(vehicle=vehicle)
        self.assertEqual(vehicle.fuel_grade, "UNLEADED_91")
        self.assertEqual(baseline.reference_fuel_rate_lph, Decimal("8.0000"))
        self.assertEqual(baseline.provenance, "CAPSTONE_REFERENCE")
        self.assertTrue(baseline.is_active)
        resolution = resolve_vehicle_fuel_rate(vehicle)
        self.assertEqual(resolution.basis, "FLEET_REFERENCE_BASELINE")
        self.assertEqual(resolution.fuel_rate_lph, Decimal("8.0000"))
        self.assertEqual(resolution.provenance, "CAPSTONE_REFERENCE")
        self.assertIsNone(resolution.source_timestamp)
        self.assertEqual(resolution.history_sample_count, 0)
        self.assertEqual(
            VehicleFuelReferenceBaseline.objects.filter(vehicle=vehicle).count(), 1
        )
        self.assertEqual(FuelPrediction.objects.count(), 0)
        self.assertEqual(TelemetryEvent.objects.count(), 0)

    def test_exact_policy_rates(self):
        self.assertEqual(
            REFERENCE_RATES,
            {
                ("SEDAN", "GASOLINE"): Decimal("6.5000"),
                ("SUV", "GASOLINE"): Decimal("8.5000"),
                ("VAN", "GASOLINE"): Decimal("8.0000"),
                ("VAN", "DIESEL"): Decimal("7.0000"),
                ("SHUTTLE_BUS", "DIESEL"): Decimal("12.0000"),
                ("SERVICE_TRUCK", "DIESEL"): Decimal("10.0000"),
            },
        )
