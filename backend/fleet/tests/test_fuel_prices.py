from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from fleet.fuel_prices import PREFERRED_FUEL_PROVIDER, resolve_vehicle_fuel_price
from fleet.models import FuelPriceRecord, Vehicle
from fleet.partner_fuel_prices import record_preferred_partner_price


class PreferredPartnerFuelPriceTests(TestCase):
    def setUp(self):
        self.now = timezone.now()

    def vehicle(self, code, fuel_type, fuel_grade=""):
        return Vehicle.objects.create(
            device_id=code, plate_number=code, display_name=code,
            fuel_type=fuel_type, fuel_grade=fuel_grade,
        )

    def price(self, fuel_type, fuel_grade, amount, *, provider=PREFERRED_FUEL_PROVIDER,
              source="MANUAL", effective_at=None, active=True):
        record = FuelPriceRecord.objects.create(
            fuel_type=fuel_type, fuel_grade=fuel_grade, price_per_liter=amount,
            currency="PHP", effective_at=effective_at or self.now - timedelta(hours=1),
            provider=provider, source_mode=source, is_active=active,
        )
        record.refresh_from_db()
        return record

    def test_each_shell_grade_resolves_only_for_its_exact_grade(self):
        cases = (
            ("G91", "GASOLINE", "UNLEADED_91"),
            ("G95", "GASOLINE", "PREMIUM_95"),
            ("G97", "GASOLINE", "PREMIUM_97"),
            ("DR", "DIESEL", "REGULAR_DIESEL"),
            ("DP", "DIESEL", "PREMIUM_DIESEL"),
        )
        for index, (code, fuel_type, fuel_grade) in enumerate(cases, start=1):
            with self.subTest(fuel_grade=fuel_grade):
                vehicle = self.vehicle(code, fuel_type, fuel_grade)
                expected = self.price(fuel_type, fuel_grade, Decimal(60 + index))
                result = resolve_vehicle_fuel_price(vehicle)
                self.assertEqual(result.basis, "MANUAL")
                self.assertEqual(result.price_per_liter, expected.price_per_liter)
                self.assertEqual(result.fuel_grade, fuel_grade)
                self.assertEqual(result.provider, PREFERRED_FUEL_PROVIDER)

    def test_wrong_grade_and_fuel_type_are_never_substituted(self):
        vehicle = self.vehicle("NO-CROSS", "GASOLINE", "PREMIUM_95")
        self.price("GASOLINE", "UNLEADED_91", "65")
        self.price("DIESEL", "REGULAR_DIESEL", "58")
        result = resolve_vehicle_fuel_price(vehicle)
        self.assertEqual(result.basis, "UNAVAILABLE")
        self.assertEqual(result.reason, "NO_VALID_PREFERRED_PARTNER_PRICE")

    def test_blank_vehicle_grade_is_explicitly_unavailable(self):
        vehicle = self.vehicle("NO-GRADE", "DIESEL")
        self.price("DIESEL", "", "60")
        result = resolve_vehicle_fuel_price(vehicle)
        self.assertEqual(result.basis, "UNAVAILABLE")
        self.assertEqual(result.reason, "FUEL_GRADE_NOT_RECORDED")

    def test_latest_effective_shell_price_wins(self):
        vehicle = self.vehicle("LATEST", "GASOLINE", "PREMIUM_97")
        self.price(
            "GASOLINE", "PREMIUM_97", "70",
            effective_at=self.now - timedelta(days=2),
        )
        latest = self.price(
            "GASOLINE", "PREMIUM_97", "72",
            effective_at=self.now - timedelta(hours=1),
        )
        self.assertEqual(
            resolve_vehicle_fuel_price(vehicle).price_per_liter,
            latest.price_per_liter,
        )

    def test_inactive_and_future_shell_prices_are_ignored(self):
        vehicle = self.vehicle("INVALID", "DIESEL", "PREMIUM_DIESEL")
        self.price("DIESEL", "PREMIUM_DIESEL", "50", active=False)
        self.price("DIESEL", "PREMIUM_DIESEL", "51", effective_at=self.now + timedelta(days=1))
        self.assertEqual(resolve_vehicle_fuel_price(vehicle).basis, "UNAVAILABLE")

    def test_no_shell_price_is_unavailable_even_with_public_records(self):
        vehicle = self.vehicle("PUBLIC", "DIESEL", "REGULAR_DIESEL")
        gaswatch = self.price(
            "DIESEL", "REGULAR_DIESEL", "64", provider="GasWatchPH",
            source="EXTERNAL_CACHED",
        )
        global_price = self.price(
            "DIESEL", "REGULAR_DIESEL", "60", provider="GlobalPetrolPrices",
            source="EXTERNAL_CACHED",
        )
        result = resolve_vehicle_fuel_price(vehicle)
        self.assertEqual(result.basis, "UNAVAILABLE")
        self.assertTrue(FuelPriceRecord.objects.filter(pk=gaswatch.pk).exists())
        self.assertTrue(FuelPriceRecord.objects.filter(pk=global_price.pk).exists())

    def test_external_shell_price_precedes_manual_shell_fallback(self):
        vehicle = self.vehicle("API-FUTURE", "GASOLINE", "UNLEADED_91")
        external = self.price(
            "GASOLINE", "UNLEADED_91", "68", source="EXTERNAL_CACHED",
            effective_at=self.now - timedelta(days=1),
        )
        self.price("GASOLINE", "UNLEADED_91", "69", effective_at=self.now)
        result = resolve_vehicle_fuel_price(vehicle)
        self.assertEqual(result.basis, "EXTERNAL_CACHED")
        self.assertEqual(result.price_per_liter, external.price_per_liter)

    def test_entry_service_derives_type_validates_and_identifies_shell(self):
        record = record_preferred_partner_price(
            fuel_grade="PREMIUM_95", price_per_liter=Decimal("71.25"),
            effective_at=self.now,
        )
        self.assertEqual(record.fuel_type, "GASOLINE")
        self.assertEqual(record.provider, PREFERRED_FUEL_PROVIDER)
        self.assertEqual(record.source_mode, "MANUAL")
        with self.assertRaises(ValidationError):
            record_preferred_partner_price(
                fuel_grade="", price_per_liter=Decimal("70"), effective_at=self.now,
            )

    def test_operator_command_records_supplied_fact_without_default_price(self):
        call_command(
            "record_partner_fuel_price", "REGULAR_DIESEL", "73.25",
            self.now.isoformat(), verbosity=0,
        )
        record = FuelPriceRecord.objects.get(provider=PREFERRED_FUEL_PROVIDER)
        self.assertEqual(record.price_per_liter, Decimal("73.2500"))
        self.assertEqual(record.fuel_grade, "REGULAR_DIESEL")

    def test_model_rejects_incompatible_grade_and_invalid_prices(self):
        incompatible = FuelPriceRecord(
            fuel_type="DIESEL", fuel_grade="PREMIUM_95", price_per_liter="60",
            effective_at=self.now, provider=PREFERRED_FUEL_PROVIDER, source_mode="MANUAL",
        )
        with self.assertRaises(ValidationError):
            incompatible.full_clean()
        for value in (Decimal("0"), Decimal("-1"), Decimal("NaN"), True, "bad"):
            record = FuelPriceRecord(
                fuel_type="DIESEL", fuel_grade="REGULAR_DIESEL",
                price_per_liter=value, effective_at=self.now,
                provider=PREFERRED_FUEL_PROVIDER, source_mode="MANUAL",
            )
            with self.assertRaises(ValidationError):
                record.full_clean()
