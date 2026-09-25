from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from fleet.models import Vehicle
from fleet.partner_fuel_prices import record_preferred_partner_price


class Command(BaseCommand):
    help = "Record an authorized factual Shell partner/reference fuel price."

    def add_arguments(self, parser):
        parser.add_argument("fuel_grade", choices=Vehicle.FuelGrade.values)
        parser.add_argument("price_per_liter")
        parser.add_argument("effective_at", help="ISO-8601 effective date/time")

    def handle(self, *args, **options):
        try:
            price = Decimal(options["price_per_liter"])
            effective_at = datetime.fromisoformat(options["effective_at"])
            record = record_preferred_partner_price(
                fuel_grade=options["fuel_grade"],
                price_per_liter=price,
                effective_at=effective_at,
            )
        except (InvalidOperation, ValueError, ValidationError) as exc:
            raise CommandError(f"Partner price was not recorded: {exc}") from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Recorded ShellPH {record.fuel_grade} PHP "
                f"{record.price_per_liter}/L effective {record.effective_at.isoformat()} "
                f"record={record.pk}"
            )
        )
