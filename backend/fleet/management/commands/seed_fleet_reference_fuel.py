from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from fleet.models import Vehicle, VehicleFuelReferenceBaseline

BASIS_VERSION = "CAPSTONE_FLEET_REFERENCE_V1"
REFERENCE_RATES = {
    (Vehicle.VehicleType.SEDAN, Vehicle.FuelType.GASOLINE): Decimal("6.5000"),
    (Vehicle.VehicleType.SUV, Vehicle.FuelType.GASOLINE): Decimal("8.5000"),
    (Vehicle.VehicleType.VAN, Vehicle.FuelType.GASOLINE): Decimal("8.0000"),
    (Vehicle.VehicleType.VAN, Vehicle.FuelType.DIESEL): Decimal("7.0000"),
    (Vehicle.VehicleType.SHUTTLE_BUS, Vehicle.FuelType.DIESEL): Decimal("12.0000"),
    (Vehicle.VehicleType.SERVICE_TRUCK, Vehicle.FuelType.DIESEL): Decimal("10.0000"),
}
DEFAULT_GRADES = {
    Vehicle.FuelType.GASOLINE: Vehicle.FuelGrade.UNLEADED_91,
    Vehicle.FuelType.DIESEL: Vehicle.FuelGrade.REGULAR_DIESEL,
}


class Command(BaseCommand):
    help = "Seed deterministic professional fleet reference fuel baselines."

    @transaction.atomic
    def handle(self, *args, **options):
        grade_updates = {fuel_type: 0 for fuel_type in DEFAULT_GRADES}
        created = 0
        updated = 0
        unsupported = 0

        for vehicle in Vehicle.objects.select_for_update().order_by("pk"):
            default_grade = DEFAULT_GRADES.get(vehicle.fuel_type)
            if default_grade and not vehicle.fuel_grade:
                vehicle.fuel_grade = default_grade
                vehicle.save(update_fields=["fuel_grade", "updated_at"])
                grade_updates[vehicle.fuel_type] += 1

            reference_rate = REFERENCE_RATES.get(
                (vehicle.vehicle_type, vehicle.fuel_type)
            )
            if reference_rate is None:
                unsupported += 1
                continue
            _, was_created = VehicleFuelReferenceBaseline.objects.update_or_create(
                vehicle=vehicle,
                defaults={
                    "reference_fuel_rate_lph": reference_rate,
                    "provenance": (
                        VehicleFuelReferenceBaseline.Provenance.CAPSTONE_REFERENCE
                    ),
                    "basis_version": BASIS_VERSION,
                    "is_active": True,
                },
            )
            created += int(was_created)
            updated += int(not was_created)

        self.stdout.write(
            self.style.SUCCESS(
                "Fleet reference fuel seed complete: "
                f"gasoline grades={grade_updates[Vehicle.FuelType.GASOLINE]}; "
                f"diesel grades={grade_updates[Vehicle.FuelType.DIESEL]}; "
                f"baselines created={created}; updated={updated}; "
                f"unsupported vehicles={unsupported}."
            )
        )
