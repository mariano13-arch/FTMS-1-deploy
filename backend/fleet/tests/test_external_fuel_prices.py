from datetime import datetime, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from fleet.external_fuel_prices import (
    PROVIDER,
    FuelPriceFetchError,
    FuelPriceRefreshReport,
    ProductResult,
    _classify_response,
    fetch_philippines_fuel_prices,
    parse_philippines_fuel_prices,
    parse_product_page,
    persist_external_fuel_prices,
    refresh_philippines_fuel_prices,
    select_newest_observation,
)
from fleet.fuel_prices import resolve_vehicle_fuel_price
from fleet.models import FuelPriceRecord, Vehicle


def source_html(
    gasoline="61.25",
    diesel="58.40",
    gasoline_date="15-Sep-2026",
    diesel_date="15-Sep-2026",
    gasoline_currency="PHP",
    diesel_currency="PHP",
):
    return f"""
    <html><body>
      <section><h2>Philippines Gasoline prices, {gasoline_date}</h2>
        <table><tr><th>Currency</th><th>Price per liter</th></tr>
        <tr><td>USD</td><td>1.07</td></tr>
        <tr><td>{gasoline_currency}</td><td>{gasoline}</td></tr></table>
      </section>
      <section><h2>Philippines Diesel prices, {diesel_date}</h2>
        <p>USD 0.99</p><p>{diesel_currency} {diesel}</p>
      </section>
      <section><h2>Philippines LPG prices, 15-Sep-2026</h2><p>PHP 999.99</p></section>
      <section><h2>Philippines Kerosene prices, 15-Sep-2026</h2><p>PHP 888.88</p></section>
    </body></html>
    """


class ExternalFuelPriceParserTests(TestCase):
    def setUp(self):
        self.retrieved_at = timezone.make_aware(datetime(2026, 9, 20, 9))

    def parse(self, html=None):
        return parse_philippines_fuel_prices(
            html or source_html(), retrieved_at=self.retrieved_at
        )

    def test_parses_labeled_php_prices_effective_dates_and_mapping(self):
        results = self.parse()
        self.assertEqual(results["GASOLINE"].observation.price_per_liter, Decimal("61.25"))
        self.assertEqual(results["DIESEL"].observation.price_per_liter, Decimal("58.40"))
        self.assertEqual(
            results["GASOLINE"].observation.effective_at.date().isoformat(), "2026-09-15"
        )
        self.assertEqual(
            results["DIESEL"].observation.effective_at.date().isoformat(), "2026-09-15"
        )

    def test_ignores_usd_lpg_and_kerosene_values(self):
        results = self.parse()
        values = {result.observation.price_per_liter for result in results.values()}
        self.assertEqual(values, {Decimal("61.25"), Decimal("58.40")})

    def test_country_prefix_is_not_required_when_product_labels_are_explicit(self):
        html = source_html().replace("Philippines Gasoline", "Gasoline").replace(
            "Philippines Diesel", "Diesel"
        )
        results = self.parse(html)
        self.assertEqual(results["GASOLINE"].observation.price_per_liter, Decimal("61.25"))
        self.assertEqual(results["DIESEL"].observation.price_per_liter, Decimal("58.40"))

    def test_malformed_and_missing_php_prices_are_rejected_independently(self):
        malformed = self.parse(source_html(gasoline="not-a-price"))
        self.assertEqual(malformed["GASOLINE"].status, "FAILED")
        self.assertNotEqual(malformed["DIESEL"].status, "FAILED")
        missing = self.parse(source_html(diesel_currency="EUR"))
        self.assertEqual(missing["DIESEL"].status, "FAILED")

    def test_nonpositive_and_nonfinite_prices_are_rejected(self):
        for price in ("0", "-1", "NaN", "Infinity"):
            with self.subTest(price=price):
                self.assertEqual(
                    self.parse(source_html(gasoline=price))["GASOLINE"].status,
                    "FAILED",
                )

    def test_missing_invalid_and_future_dates_are_rejected(self):
        for value in ("unknown", "not-a-date", "21-Sep-2026"):
            with self.subTest(value=value):
                self.assertEqual(
                    self.parse(source_html(diesel_date=value))["DIESEL"].status,
                    "FAILED",
                )

    def test_changed_unlabeled_html_fails_safely(self):
        results = self.parse("<html><body>61.25 58.40 PHP USD</body></html>")
        self.assertTrue(all(item.status == "FAILED" for item in results.values()))

    def test_nested_summary_table_and_whitespace_variation(self):
        html = """
        <table><caption><span>Fuels, price per liter</span></caption>
          <thead><tr><th>Date</th><th>PHP</th><th>USD</th></tr></thead>
          <tbody>
            <tr><th><span>Gasoline</span> prices, <time>15 Sep 2026</time></th>
                <td><strong>PHP</strong> <span>61.25</span></td><td>USD 1.07</td></tr>
            <tr><th> Diesel   prices, <time>15 Sep 2026</time></th>
                <td> PHP\n58.40 </td><td>USD 0.99</td></tr>
          </tbody>
        </table>
        """
        results = self.parse(html)
        self.assertEqual(results["GASOLINE"].observation.price_per_liter, Decimal("61.25"))
        self.assertEqual(results["DIESEL"].observation.price_per_liter, Decimal("58.40"))


class ExternalFuelPriceResponseTests(TestCase):
    def classify(self, html, *, product=None, content_type="text/html; charset=utf-8"):
        return _classify_response(
            html,
            status=200,
            final_url="https://www.globalpetrolprices.com/Philippines/",
            content_type=content_type,
            product=product,
        )

    def product_response(
        self, fuel_type, price="61.25", date="15-Sep-2026", body=None
    ):
        body = body or f"""
            <h1>Philippines {fuel_type.title()} prices</h1>
            <table>
              <tr><th>Current price</th><td>Weekly national price</td></tr>
              <tr><th>Price (PHP/Liter)</th><td><strong>{price}</strong></td></tr>
            </table>
        """
        html = (
            f"<html><title>Philippines {fuel_type.title()} prices, {date}</title><body>"
            f"{body}</body></html>"
        )
        return self.classify(html, product=fuel_type)

    def test_normal_summary_response_metadata_is_classified(self):
        response = self.classify(source_html())
        self.assertEqual(response.classification, "NORMAL_PRICE_PAGE")
        self.assertEqual(response.status, 200)
        self.assertGreater(response.body_length, 0)

    def test_challenge_and_access_denied_pages_are_detected(self):
        for marker in ("Checking your browser", "Access denied", "Verify you are human"):
            with self.subTest(marker=marker):
                response = self.classify(f"<html><title>Wait</title>{marker}</html>")
                self.assertEqual(response.classification, "INTERSTITIAL_OR_CHALLENGE")

    def test_missing_expected_labels_is_unexpected_html(self):
        response = self.classify("<html><title>Philippines</title><p>Welcome</p></html>")
        self.assertEqual(response.classification, "UNEXPECTED_HTML")
        self.assertIn("PHP", response.missing_labels)

    def test_product_fallbacks_require_identity_php_and_date(self):
        retrieved_at = timezone.make_aware(datetime(2026, 9, 20, 9))
        gasoline = parse_product_page(
            self.product_response("GASOLINE"), "GASOLINE", retrieved_at=retrieved_at
        )
        diesel = parse_product_page(
            self.product_response("DIESEL", "58.40"),
            "DIESEL",
            retrieved_at=retrieved_at,
        )
        self.assertEqual(gasoline.observation.price_per_liter, Decimal("61.25"))
        self.assertEqual(diesel.observation.price_per_liter, Decimal("58.40"))

    def test_currency_table_selects_php_liter_not_usd_or_php_gallon(self):
        body = """
            <h1>Philippines Gasoline prices</h1>
            <table>
              <tr><th>Currency</th><th>Liter</th><th>Gallon</th></tr>
              <tr><th>PHP</th><td>61.25</td><td>231.85</td></tr>
              <tr><th>USD</th><td>1.07</td><td>4.05</td></tr>
            </table>
        """
        response = self.product_response("GASOLINE", body=body)
        result = parse_product_page(
            response,
            "GASOLINE",
            retrieved_at=timezone.make_aware(datetime(2026, 9, 20, 9)),
        )
        self.assertEqual(result.observation.price_per_liter, Decimal("61.25"))

    def test_historical_statistics_do_not_override_current_price(self):
        body = """
            <h1>Philippines Diesel prices</h1>
            <table>
              <tr><th>Current price</th><td>Weekly national price</td></tr>
              <tr><th>Price (PHP/Liter)</th><td>58.40</td></tr>
            </table>
            <table>
              <tr><th>Historical average</th><td>52.10</td></tr>
              <tr><th>One month ago</th><td>57.20</td></tr>
              <tr><th>Minimum</th><td>40.00</td></tr>
              <tr><th>Maximum</th><td>75.00</td></tr>
            </table>
        """
        result = parse_product_page(
            self.product_response("DIESEL", body=body),
            "DIESEL",
            retrieved_at=timezone.make_aware(datetime(2026, 9, 20, 9)),
        )
        self.assertEqual(result.observation.price_per_liter, Decimal("58.40"))

    def test_narrative_current_price_fallback_is_tightly_scoped(self):
        body = """
            <h1>Philippines Gasoline prices</h1>
            <p>The historical average was PHP 50.00 per liter.</p>
            <p>The current price in the Philippines is PHP 61.25 per liter.</p>
            <p>One month ago it was PHP 60.00 per liter.</p>
        """
        result = parse_product_page(
            self.product_response("GASOLINE", body=body),
            "GASOLINE",
            retrieved_at=timezone.make_aware(datetime(2026, 9, 20, 9)),
        )
        self.assertEqual(result.observation.price_per_liter, Decimal("61.25"))

    def test_flat_current_price_card_requires_php_and_liter_label(self):
        body = """
            <h1>Philippines Gasoline prices</h1>
            <div class="current-price-card">
              <span>Current price</span><strong>PHP 61.25</strong>
              <small>Price (PHP/Liter)</small>
            </div>
            <div>Price (PHP/Gallon) 231.85</div>
            <div>USD/Liter 1.07</div>
        """
        result = parse_product_page(
            self.product_response("GASOLINE", body=body),
            "GASOLINE",
            retrieved_at=timezone.make_aware(datetime(2026, 9, 20, 9)),
        )
        self.assertEqual(result.observation.price_per_liter, Decimal("61.25"))

    def test_conflicting_narrative_values_fail_safely(self):
        body = """
            <h1>Philippines Gasoline prices</h1>
            <p>Current price is PHP 61.25 per liter.</p>
            <p>Current price is PHP 62.00 per liter.</p>
        """
        result = parse_product_page(
            self.product_response("GASOLINE", body=body),
            "GASOLINE",
            retrieved_at=timezone.make_aware(datetime(2026, 9, 20, 9)),
        )
        self.assertEqual(result.status, "FAILED")
        self.assertIn("Ambiguous conflicting", result.reason)

    def test_malformed_current_php_value_is_rejected(self):
        result = parse_product_page(
            self.product_response("DIESEL", price="not-a-price"),
            "DIESEL",
            retrieved_at=timezone.make_aware(datetime(2026, 9, 20, 9)),
        )
        self.assertEqual(result.status, "FAILED")

    def test_repeated_product_observation_is_idempotent(self):
        retrieved_at = timezone.make_aware(datetime(2026, 9, 20, 9))
        result = parse_product_page(
            self.product_response("GASOLINE"),
            "GASOLINE",
            retrieved_at=retrieved_at,
        )
        failed = ProductResult("DIESEL", "FAILED", "Not part of this refresh.")
        first = persist_external_fuel_prices({"GASOLINE": result, "DIESEL": failed})
        second = persist_external_fuel_prices({"GASOLINE": result, "DIESEL": failed})
        self.assertEqual(first["GASOLINE"].status, "CREATED")
        self.assertEqual(second["GASOLINE"].status, "EXISTING")
        self.assertEqual(FuelPriceRecord.objects.filter(fuel_type="GASOLINE").count(), 1)

    def test_product_fallback_future_date_is_rejected(self):
        retrieved_at = timezone.make_aware(datetime(2026, 9, 20, 9))
        result = parse_product_page(
            self.product_response("DIESEL", date="21-Sep-2026"),
            "DIESEL",
            retrieved_at=retrieved_at,
        )
        self.assertEqual(result.status, "FAILED")

    def test_newest_factual_observation_wins_with_explicit_discrepancy(self):
        retrieved_at = timezone.make_aware(datetime(2026, 9, 20, 9))
        summary = parse_philippines_fuel_prices(
            source_html(gasoline_date="16-Sep-2026"), retrieved_at=retrieved_at
        )["GASOLINE"]
        older_fallback = parse_product_page(
            self.product_response("GASOLINE", date="15-Sep-2026"),
            "GASOLINE",
            retrieved_at=retrieved_at,
        )
        selected = select_newest_observation(summary, older_fallback)
        self.assertEqual(selected.observation.effective_at.date().isoformat(), "2026-09-16")
        self.assertIn("DATE_DISCREPANCY", selected.reason)

        newer_fallback = parse_product_page(
            self.product_response("GASOLINE", "62.00", "17-Sep-2026"),
            "GASOLINE",
            retrieved_at=retrieved_at,
        )
        selected = select_newest_observation(summary, newer_fallback)
        self.assertEqual(selected.observation.price_per_liter, Decimal("62.00"))
        self.assertIn("PRODUCT_FALLBACK", selected.reason)

    def test_same_date_conflicting_values_fail_explicitly(self):
        retrieved_at = timezone.make_aware(datetime(2026, 9, 20, 9))
        summary = parse_philippines_fuel_prices(
            source_html(), retrieved_at=retrieved_at
        )["GASOLINE"]
        fallback = parse_product_page(
            self.product_response("GASOLINE", "62.00"),
            "GASOLINE",
            retrieved_at=retrieved_at,
        )
        selected = select_newest_observation(summary, fallback)
        self.assertEqual(selected.status, "FAILED")
        self.assertIn("SOURCE_DATE_CONFLICT", selected.reason)


class ExternalFuelPricePersistenceTests(TestCase):
    def setUp(self):
        self.retrieved_at = timezone.make_aware(datetime(2026, 9, 20, 9))

    def parsed(self, html=None):
        return parse_philippines_fuel_prices(
            html or source_html(), retrieved_at=self.retrieved_at
        )

    def test_success_persists_external_provenance_and_actual_retrieval_time(self):
        results = persist_external_fuel_prices(self.parsed())
        record = FuelPriceRecord.objects.get(pk=results["GASOLINE"].record_id)
        self.assertEqual(record.source_mode, FuelPriceRecord.SourceMode.EXTERNAL_CACHED)
        self.assertEqual(record.provider, PROVIDER)
        self.assertEqual(record.currency, "PHP")
        self.assertEqual(record.retrieved_at, self.retrieved_at)

    def test_repeated_equivalent_refresh_is_idempotent(self):
        persist_external_fuel_prices(self.parsed())
        second = persist_external_fuel_prices(self.parsed())
        self.assertEqual(FuelPriceRecord.objects.count(), 2)
        self.assertEqual(second["GASOLINE"].status, "EXISTING")

    def test_new_week_is_retained_as_history(self):
        persist_external_fuel_prices(self.parsed())
        newer = source_html(
            gasoline="62.10",
            diesel="59.00",
            gasoline_date="16-Sep-2026",
            diesel_date="16-Sep-2026",
        )
        persist_external_fuel_prices(self.parsed(newer))
        self.assertEqual(FuelPriceRecord.objects.filter(fuel_type="GASOLINE").count(), 2)
        self.assertEqual(FuelPriceRecord.objects.filter(fuel_type="DIESEL").count(), 2)

    def test_partial_success_preserves_existing_diesel_cache(self):
        old = FuelPriceRecord.objects.create(
            fuel_type="DIESEL", price_per_liter="57.00", currency="PHP",
            effective_at=self.retrieved_at - timedelta(days=14), provider=PROVIDER,
            source_mode=FuelPriceRecord.SourceMode.EXTERNAL_CACHED,
        )
        results = persist_external_fuel_prices(self.parsed(source_html(diesel="bad")))
        self.assertEqual(results["GASOLINE"].status, "CREATED")
        self.assertEqual(results["DIESEL"].status, "FAILED")
        self.assertEqual(FuelPriceRecord.objects.get(pk=old.pk).price_per_liter, Decimal("57.0000"))

    def test_manual_record_is_never_modified_and_blank_grade_is_unavailable(self):
        manual = FuelPriceRecord.objects.create(
            fuel_type="DIESEL", price_per_liter="55", currency="PHP",
            effective_at=self.retrieved_at - timedelta(days=20), provider="Fleet administrator",
            source_mode=FuelPriceRecord.SourceMode.MANUAL,
        )
        persist_external_fuel_prices(self.parsed())
        manual.refresh_from_db()
        self.assertEqual(manual.price_per_liter, Decimal("55.0000"))
        vehicle = Vehicle.objects.create(
            device_id="PRICE-D1",
            display_name="Diesel",
            plate_number="PRICE-D1",
            fuel_type="DIESEL",
        )
        with patch("fleet.fuel_prices.timezone.now", return_value=self.retrieved_at):
            result = resolve_vehicle_fuel_price(vehicle)
        self.assertEqual(result.basis, "UNAVAILABLE")
        self.assertEqual(result.reason, "FUEL_GRADE_NOT_RECORDED")


class ExternalFuelPriceFailureTests(TestCase):
    def setUp(self):
        self.cached = FuelPriceRecord.objects.create(
            fuel_type="DIESEL", price_per_liter="57", currency="PHP",
            effective_at=timezone.now() - timedelta(days=7), provider=PROVIDER,
            source_mode=FuelPriceRecord.SourceMode.EXTERNAL_CACHED,
        )

    def assert_cache_preserved(self):
        self.cached.refresh_from_db()
        self.assertEqual(FuelPriceRecord.objects.count(), 1)
        self.assertEqual(self.cached.price_per_liter, Decimal("57.0000"))

    @patch("fleet.external_fuel_prices.urlopen", side_effect=TimeoutError)
    def test_network_timeout_preserves_cache(self, _urlopen):
        report = refresh_philippines_fuel_prices()
        self.assertIsNotNone(report.fetch_error)
        self.assert_cache_preserved()

    @patch("fleet.external_fuel_prices.urlopen")
    def test_http_failure_preserves_cache(self, urlopen_mock):
        urlopen_mock.side_effect = HTTPError("url", 503, "Unavailable", {}, None)
        report = refresh_philippines_fuel_prices()
        self.assertIn("503", report.fetch_error)
        self.assert_cache_preserved()

    @patch("fleet.external_fuel_prices.urlopen", side_effect=URLError("offline"))
    def test_fetch_wraps_network_errors_without_html(self, _urlopen):
        with self.assertRaises(FuelPriceFetchError):
            fetch_philippines_fuel_prices()

    @patch("fleet.management.commands.refresh_fuel_prices.refresh_philippines_fuel_prices")
    def test_management_command_prints_concise_failure(self, refresh_mock):
        refresh_mock.return_value = FuelPriceRefreshReport(
            products={
                fuel_type: ProductResult(fuel_type, "FAILED", "Source unavailable.")
                for fuel_type in ("GASOLINE", "DIESEL")
            },
            fetch_error="Source unavailable.",
        )
        output, errors = StringIO(), StringIO()
        call_command("refresh_fuel_prices", stdout=output, stderr=errors)
        self.assertIn("Provider: GlobalPetrolPrices", output.getvalue())
        self.assertIn("FAILED", errors.getvalue())
