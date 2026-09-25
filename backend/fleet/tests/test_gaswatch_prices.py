from datetime import datetime, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from fleet.external_fuel_prices import persist_external_fuel_prices
from fleet.fuel_prices import resolve_vehicle_fuel_price
from fleet.gaswatch_prices import (
    GASWATCH_DIESEL_PROVIDER,
    GASWATCH_GASOLINE_PROVIDER,
    _classify_gaswatch_response,
    parse_gaswatch_ph_prices,
)
from fleet.models import FuelPriceRecord, Vehicle


def gaswatch_html(*references, effective="September 21, 2026", extra=""):
    metrics = "".join(
        f"<section>Avg. {label} PHP {price} per Liter</section>"
        for label, price in references
    )
    return f"""<html><head><title>GasWatch PH</title></head><body>
    <h1>Metro Manila Diesel and Unleaded reference prices</h1>
    <p>Updated {effective}</p>{metrics}{extra}
    <footer>1,240 stations tracked across Metro Manila</footer></body></html>"""


def response(html):
    return _classify_gaswatch_response(
        html, status=200, final_url="https://gaswatchph.com/",
        content_type="text/html; charset=utf-8",
    )


class GasWatchParserTests(TestCase):
    def setUp(self):
        self.retrieved_at = timezone.make_aware(datetime(2026, 9, 24, 9))

    def parse(self, *references, **kwargs):
        html = gaswatch_html(*references, **kwargs)
        return parse_gaswatch_ph_prices(response(html), retrieved_at=self.retrieved_at)

    def test_explicit_overall_references_map_to_exact_canonical_grades(self):
        cases = (
            ("Diesel", "REGULAR_DIESEL", "DIESEL"),
            ("Premium Diesel", "PREMIUM_DIESEL", "DIESEL"),
            ("Unleaded 91", "UNLEADED_91", "GASOLINE"),
            ("Premium 95", "PREMIUM_95", "GASOLINE"),
            ("Prem 97", "PREMIUM_97", "GASOLINE"),
        )
        for label, grade, fuel_type in cases:
            with self.subTest(grade=grade):
                observation = self.parse((label, "72.50"))[grade].observation
                self.assertEqual(observation.fuel_grade, grade)
                self.assertEqual(observation.fuel_type, fuel_type)
                self.assertEqual(observation.price_per_liter, Decimal("72.50"))

    def test_plain_explicit_avg_unleaded_maps_to_unleaded_91(self):
        observation = self.parse(("Unleaded", "67.80"))["UNLEADED_91"].observation
        self.assertEqual(observation.fuel_grade, "UNLEADED_91")
        self.assertEqual(observation.provider, GASWATCH_GASOLINE_PROVIDER)

    def test_public_metro_manila_average_sentence_maps_diesel_and_ron_91(self):
        extra = (
            "As of September 21, 2026, the Metro Manila average diesel price is "
            "₱104.91/L and unleaded is ₱92.59/L. The cheapest unleaded (RON 91) "
            "is shown separately."
        )
        results = self.parse(extra=extra)
        self.assertEqual(
            results["REGULAR_DIESEL"].observation.price_per_liter,
            Decimal("104.91"),
        )
        self.assertEqual(
            results["UNLEADED_91"].observation.price_per_liter,
            Decimal("92.59"),
        )

    def test_granular_premium_tables_do_not_create_reference_prices(self):
        extra = """
        <table><tr><th>Brand average</th><th>Prem Diesel</th><th>Prem 95</th></tr>
        <tr><td>Alpha</td><td>80.00</td><td>85.00</td></tr></table>
        <table><tr><th>Station</th><th>Prem 97</th></tr>
        <tr><td>Station One</td><td>90.00</td></tr></table>"""
        results = self.parse(("Diesel", "64.25"), extra=extra)
        self.assertIsNotNone(results["REGULAR_DIESEL"].observation)
        for grade in ("PREMIUM_DIESEL", "PREMIUM_95", "PREMIUM_97"):
            self.assertEqual(results[grade].status, "FAILED")

    def test_egas_and_kerosene_are_ignored(self):
        results = self.parse(("E-Gas", "70.00"), ("Kerosene", "75.00"))
        self.assertTrue(all(result.observation is None for result in results.values()))

    def test_partial_grade_success_is_independent(self):
        results = self.parse(("Diesel", "64.25"), ("Premium 95", "85.00"))
        self.assertIsNotNone(results["REGULAR_DIESEL"].observation)
        self.assertIsNotNone(results["PREMIUM_95"].observation)
        self.assertEqual(results["UNLEADED_91"].status, "FAILED")

    def test_effective_date_is_required_and_cannot_be_future(self):
        missing = self.parse(("Diesel", "64.25"), effective="this week")
        future = self.parse(("Diesel", "64.25"), effective="September 25, 2026")
        self.assertTrue(all(result.status == "FAILED" for result in missing.values()))
        self.assertTrue(all(result.status == "FAILED" for result in future.values()))

    def test_malformed_nonfinite_and_nonpositive_prices_are_rejected(self):
        for value in ("bad", "NaN", "Infinity", "0", "-1"):
            with self.subTest(value=value):
                result = self.parse(("Diesel", value))["REGULAR_DIESEL"]
                self.assertEqual(result.status, "FAILED")


class GasWatchPersistenceTests(TestCase):
    def setUp(self):
        retrieved = timezone.make_aware(datetime(2026, 9, 24, 9))
        html = gaswatch_html(("Diesel", "64.25"), ("Unleaded 91", "67.80"))
        self.parsed = parse_gaswatch_ph_prices(response(html), retrieved_at=retrieved)

    def test_exact_grades_persist_and_duplicate_refresh_is_idempotent(self):
        first = persist_external_fuel_prices(self.parsed)
        second = persist_external_fuel_prices(self.parsed)
        self.assertEqual(first["REGULAR_DIESEL"].status, "CREATED")
        self.assertEqual(second["REGULAR_DIESEL"].status, "EXISTING")
        self.assertEqual(FuelPriceRecord.objects.count(), 2)
        diesel = FuelPriceRecord.objects.get(fuel_grade="REGULAR_DIESEL")
        self.assertEqual(diesel.provider, GASWATCH_DIESEL_PROVIDER)
        self.assertEqual(diesel.fuel_type, "DIESEL")


class GasWatchResolverSelectionTests(TestCase):
    def test_shell_partner_manual_works_when_gaswatch_grade_is_unavailable(self):
        vehicle = Vehicle.objects.create(
            device_id="GW-P95", plate_number="GW-P95", display_name="Premium 95",
            fuel_type="GASOLINE", fuel_grade="PREMIUM_95",
        )
        FuelPriceRecord.objects.create(
            fuel_type="GASOLINE", fuel_grade="", price_per_liter="60",
            currency="PHP", effective_at=timezone.now() - timedelta(days=1),
            provider="GlobalPetrolPrices", source_mode="EXTERNAL_CACHED",
        )
        FuelPriceRecord.objects.create(
            fuel_type="GASOLINE", fuel_grade="PREMIUM_95", price_per_liter="75",
            currency="PHP", effective_at=timezone.now() - timedelta(hours=1),
            provider="ShellPH", source_mode="MANUAL",
        )
        result = resolve_vehicle_fuel_price(vehicle)
        self.assertEqual(result.basis, "MANUAL")
        self.assertEqual(result.price_per_liter, Decimal("75.0000"))
