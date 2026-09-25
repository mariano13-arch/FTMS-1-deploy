from django.core.management.base import BaseCommand

from fleet.external_fuel_prices import PROVIDER, SOURCE_URL, refresh_philippines_fuel_prices
from fleet.gaswatch_prices import GASWATCH_PROVIDER, GASWATCH_URL, refresh_gaswatch_ph


class Command(BaseCommand):
    help = "Refresh cached weekly Philippines gasoline and diesel prices."

    def handle(self, *args, **options):
        gaswatch = refresh_gaswatch_ph()
        self.stdout.write(f"Provider: {GASWATCH_PROVIDER}")
        self.stdout.write(f"Source: {GASWATCH_URL}")
        if gaswatch.response:
            self.stdout.write(
                f"Classification: {gaswatch.response.classification}; "
                f"location={gaswatch.response.safe_location}; "
                f"content-type={gaswatch.response.content_type or 'unknown'}; "
                f"bytes={gaswatch.response.body_length}"
            )
        if gaswatch.station_metadata or gaswatch.geographic_metadata:
            self.stdout.write(
                f"Coverage: {gaswatch.geographic_metadata or 'unavailable'}; "
                f"stations={gaswatch.station_metadata or 'unavailable'}"
            )
        for fuel_grade, result in gaswatch.products.items():
            if result.status == "FAILED":
                self.stdout.write(
                    f"GasWatch {fuel_grade}: UNAVAILABLE - {result.reason}"
                )
            else:
                observation = result.observation
                self.stdout.write(
                    f"GasWatch {fuel_grade}: {result.status} "
                    f"PHP {observation.price_per_liter}/L "
                    f"effective {observation.effective_at.date()} record={result.record_id}"
                )

        report = refresh_philippines_fuel_prices()
        self.stdout.write(f"Provider: {PROVIDER}")
        self.stdout.write(f"Source: {SOURCE_URL}")
        self.stdout.write(f"Classification: {report.classification}")
        for response in report.responses:
            missing = ",".join(response.missing_labels) or "none"
            self.stdout.write(
                f"Response: HTTP {response.status}; location={response.safe_location}; "
                f"content-type={response.content_type or 'unknown'}; bytes={response.body_length}; "
                f"classification={response.classification}; missing-labels={missing}; "
                f"title={response.title or 'unavailable'}"
            )
        for fuel_type, result in report.products.items():
            if result.status == "FAILED":
                self.stderr.write(f"{fuel_type}: FAILED - {result.reason}")
                continue
            observation = result.observation
            self.stdout.write(
                f"{fuel_type}: {result.status} PHP {observation.price_per_liter}/L "
                f"effective {observation.effective_at.date()} record={result.record_id}"
            )
