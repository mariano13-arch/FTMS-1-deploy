from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from fleet.models import Vehicle

PROTECTED_DEVICE_ID = "LILYGO-001"
PROTECTED_DISPLAY_NAME = "Sprint 1 Demo Vehicle"
OWNED_PREFIXES = ("FT-GT-", "FT-ST-", "DEV-PAX-", "DEV-LOG-", "DEMO-V")
GUEST_COUNT = 100
SUPPLY_COUNT = 100
POSITION_PREFIX = "FT-FLEET-POSITION-"
OXFORD_LATITUDE, OXFORD_LONGITUDE = 14.565200, 121.028600

GUEST_PROFILES = (
    (Vehicle.VehicleType.SEDAN, "Toyota", "Corolla Altis", 4, Decimal("1800.00")),
    (Vehicle.VehicleType.SUV, "Toyota", "Fortuner", 7, Decimal("2800.00")),
    (Vehicle.VehicleType.VAN, "Toyota", "Hiace Commuter", 15, Decimal("3500.00")),
    (Vehicle.VehicleType.SHUTTLE_BUS, "Hino", "Liesse II", 30, Decimal("7000.00")),
)
SUPPLY_PROFILES = (
    (Vehicle.VehicleType.VAN, "Toyota", "Hiace Cargo", Decimal("1000.00"), Decimal("3500.00")),
    (
        Vehicle.VehicleType.SERVICE_TRUCK,
        "Isuzu",
        "N-Series",
        Decimal("3000.00"),
        Decimal("6000.00"),
    ),
)
SUPPLIERS = (
    "Oxford Mobility Solutions Inc.",
    "Metro Commercial Vehicle Supply Corp.",
    "Premier Fleet Procurement Services",
    "Capital Automotive Fleet Solutions",
)
COLORS = ("Pearl White", "Graphite Gray", "Midnight Black", "Silver Metallic")
PRICE_BY_TYPE = {
    Vehicle.VehicleType.SEDAN: Decimal("1350000.00"),
    Vehicle.VehicleType.SUV: Decimal("2100000.00"),
    Vehicle.VehicleType.VAN: Decimal("1950000.00"),
    Vehicle.VehicleType.SHUTTLE_BUS: Decimal("3150000.00"),
    Vehicle.VehicleType.SERVICE_TRUCK: Decimal("2400000.00"),
}


def professional_master_data(group, number, vehicle_type, model_year):
    """Return deterministic synthetic acquisition data for development-only fleet records."""
    acquisition = date(model_year, ((number - 1) % 9) + 1, ((number - 1) % 20) + 1)
    warranty = acquisition.replace(year=acquisition.year + 3)
    registration = date(2027, ((number - 1) % 12) + 1, ((number - 1) % 20) + 5)
    insurance = date(2027, ((number + 5) % 12) + 1, ((number + 3) % 20) + 5)
    serial = f"{group}{model_year}{number:06d}"
    return {
        "ownership_type": Vehicle.OwnershipType.COMPANY_OWNED,
        "supplier_name": SUPPLIERS[(number - 1) % len(SUPPLIERS)],
        "purchase_order_number": f"OXF-{group}-FLT-{model_year}-{number:04d}",
        "acquisition_date": acquisition,
        "purchase_price": PRICE_BY_TYPE[vehicle_type]
        + Decimal((number - 1) % 10) * Decimal("25000.00"),
        "purchase_currency": "PHP",
        "warranty_expiry_date": warranty,
        "registration_expiry_date": registration,
        "insurance_expiry_date": insurance,
        "vin": f"OXF{serial}",
        "engine_number": f"ENG-{serial}",
        "chassis_number": f"CHS-{serial}",
        "color": COLORS[(number - 1) % len(COLORS)],
        "fuel_type": (
            Vehicle.FuelType.GASOLINE
            if vehicle_type in {Vehicle.VehicleType.SEDAN, Vehicle.VehicleType.SUV}
            else Vehicle.FuelType.DIESEL
        ),
        "transmission_type": (
            Vehicle.TransmissionType.AUTOMATIC if group == "GT" else Vehicle.TransmissionType.MANUAL
        ),
    }


def fleet_records():
    records = []
    for number in range(1, GUEST_COUNT + 1):
        vehicle_type, manufacturer, model, capacity, gvwr = GUEST_PROFILES[
            (number - 1) % len(GUEST_PROFILES)
        ]
        model_year = 2022 + ((number - 1) % 5)
        records.append(
            {
                "device_id": f"FT-GT-{number:03d}",
                "plate_number": f"GT-{number:03d}",
                "display_name": f"Oxford Guest Vehicle {number:03d}",
                "vehicle_type": vehicle_type,
                "manufacturer": manufacturer,
                "model": model,
                "model_year": model_year,
                "passenger_capacity": capacity,
                "payload_capacity_kg": None,
                "gvwr_kg": gvwr,
                **professional_master_data("GT", number, vehicle_type, model_year),
            }
        )
    for number in range(1, SUPPLY_COUNT + 1):
        vehicle_type, manufacturer, model, payload, gvwr = SUPPLY_PROFILES[
            (number - 1) % len(SUPPLY_PROFILES)
        ]
        model_year = 2022 + ((number - 1) % 5)
        records.append(
            {
                "device_id": f"FT-ST-{number:03d}",
                "plate_number": f"ST-{number:03d}",
                "display_name": f"Oxford Supply Vehicle {number:03d}",
                "vehicle_type": vehicle_type,
                "manufacturer": manufacturer,
                "model": model,
                "model_year": model_year,
                "passenger_capacity": 3,
                "payload_capacity_kg": payload,
                "gvwr_kg": gvwr,
                **professional_master_data("ST", number, vehicle_type, model_year),
            }
        )
    return records


def owned_vehicles():
    query = Vehicle.objects.none()
    for prefix in OWNED_PREFIXES:
        query = query | Vehicle.objects.filter(device_id__startswith=prefix)
    return query.exclude(device_id=PROTECTED_DEVICE_ID).distinct()


def legacy_vehicles():
    current_ids = {record["device_id"] for record in fleet_records()}
    return owned_vehicles().exclude(device_id__in=current_ids).order_by("device_id")


def reference_classes(vehicle):
    references = []
    for relation in Vehicle._meta.related_objects:
        lookup = {relation.field.name: vehicle}
        if relation.related_model._base_manager.filter(**lookup).exists():
            references.append(relation.get_accessor_name())
    return references


class Command(BaseCommand):
    help = "Seed deterministic professional vehicle master data for local development."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--replace-development-fleet", action="store_true")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Fleet development seeding is restricted to DEBUG environments.")
        protected = Vehicle.objects.filter(
            device_id=PROTECTED_DEVICE_ID,
            display_name=PROTECTED_DISPLAY_NAME,
        ).first()
        if protected is None:
            raise CommandError("Protected Sprint 1 Demo Vehicle was not found by stable identity.")
        legacy = list(legacy_vehicles())
        referenced = {}
        for vehicle in legacy:
            classes = reference_classes(vehicle)
            if classes:
                referenced[vehicle.device_id] = classes
        safe_delete_count = len(legacy) - len(referenced)
        if options["dry_run"]:
            self._report(protected, legacy, referenced, safe_delete_count, options)
            return
        with transaction.atomic():
            deleted = deactivated = 0
            if options["replace_development_fleet"]:
                deleted, deactivated = self._cleanup(legacy)
            created, updated = self._seed()
        self.stdout.write(
            self.style.SUCCESS(
                "Professional fleet seed complete: "
                f"created={created}, updated={updated}, deleted_legacy={deleted}, "
                f"deactivated_referenced_legacy={deactivated}."
            )
        )
        if legacy and not options["replace_development_fleet"]:
            self.stdout.write(
                self.style.WARNING(
                    "Legacy development vehicles were not changed. Review --dry-run, then use "
                    "--replace-development-fleet to clean them up safely."
                )
            )

    def _report(self, protected, legacy, referenced, safe_delete_count, options):
        self.stdout.write(f"Current vehicles: {Vehicle.objects.count()}")
        self.stdout.write(
            f"Protected: {protected.display_name} / {protected.device_id} / pk={protected.pk}"
        )
        self.stdout.write("Would reconcile: 100 Guest Transport and 100 Supply Transport vehicles")
        self.stdout.write(f"Legacy development vehicles found: {len(legacy)}")
        if options["replace_development_fleet"]:
            self.stdout.write(f"Would delete unreferenced legacy vehicles: {safe_delete_count}")
            self.stdout.write(f"Would deactivate referenced legacy vehicles: {len(referenced)}")
        else:
            self.stdout.write("Would preserve all legacy vehicles (replacement flag not supplied)")
        for device_id, classes in referenced.items():
            self.stdout.write(f"Referenced legacy preserved: {device_id} ({', '.join(classes)})")
        self.stdout.write(
            "Would create no telemetry, locations, bindings, inspections, maintenance, or trips"
        )

    def _cleanup(self, legacy):
        deleted = deactivated = 0
        for vehicle in legacy:
            if reference_classes(vehicle):
                if vehicle.is_active:
                    vehicle.is_active = False
                    vehicle.save(update_fields=["is_active", "updated_at"])
                deactivated += 1
                continue
            try:
                vehicle.delete()
                deleted += 1
            except ProtectedError:
                vehicle.is_active = False
                vehicle.save(update_fields=["is_active", "updated_at"])
                deactivated += 1
        return deleted, deactivated

    def _seed(self):
        records = fleet_records()
        existing = {
            vehicle.device_id: vehicle
            for vehicle in Vehicle.objects.filter(
                device_id__in=[record["device_id"] for record in records]
            )
        }
        create = []
        update = []
        mutable_fields = [
            "plate_number",
            "display_name",
            "vehicle_type",
            "manufacturer",
            "model",
            "model_year",
            "passenger_capacity",
            "payload_capacity_kg",
            "gvwr_kg",
            "ownership_type",
            "supplier_name",
            "purchase_order_number",
            "acquisition_date",
            "purchase_price",
            "purchase_currency",
            "warranty_expiry_date",
            "registration_expiry_date",
            "insurance_expiry_date",
            "vin",
            "engine_number",
            "chassis_number",
            "color",
            "fuel_type",
            "transmission_type",
            "is_active",
            "updated_at",
        ]
        now = timezone.now()
        for record in records:
            values = {
                **record,
                "ownership_type": Vehicle.OwnershipType.COMPANY_OWNED,
                "is_active": True,
            }
            vehicle = existing.get(record["device_id"])
            if vehicle is None:
                create.append(Vehicle(**values))
                continue
            for field, value in values.items():
                setattr(vehicle, field, value)
            vehicle.updated_at = now
            update.append(vehicle)
        Vehicle.objects.bulk_create(create)
        if update:
            Vehicle.objects.bulk_update(update, mutable_fields)
        return len(create), len(update)
