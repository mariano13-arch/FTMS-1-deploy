from datetime import date
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from fleet.management.commands.seed_vehicle_registry import fleet_records
from fleet.models import Vehicle, VehicleInspection, VehicleMaintenanceRecord
from telemetry.models import TelemetryDevice, TelemetryDeviceBinding, TelemetryEvent
from transport_requests.models import DispatchAssignment, DispatchPlan


@override_settings(DEBUG=True)
class SeedVehicleRegistryTests(TestCase):
    def setUp(self):
        self.operator = get_user_model().objects.create_user(username="fleet-seed-operator")
        self.protected = Vehicle.objects.create(
            device_id="LILYGO-001",
            plate_number="DEMO-001",
            display_name="Sprint 1 Demo Vehicle",
            is_active=True,
        )
        self.protected_pk = self.protected.pk
        self.protected_binding_ids = list(
            TelemetryDeviceBinding.objects.filter(vehicle=self.protected).values_list(
                "pk", flat=True
            )
        )

    def run_command(self, *args):
        output = StringIO()
        call_command("seed_vehicle_registry", *args, stdout=output)
        return output.getvalue()

    def seeded(self):
        return Vehicle.objects.filter(device_id__regex=r"^FT-(GT|ST)-[0-9]{3}$")

    def test_dry_run_is_read_only_and_requires_explicit_replacement_for_cleanup(self):
        legacy = Vehicle.objects.create(
            device_id="DEV-PAX-001", plate_number="OLD-001", display_name="Old fleet"
        )
        device_ids = list(
            TelemetryDeviceBinding.objects.filter(vehicle=legacy).values_list(
                "device_id", flat=True
            )
        )
        TelemetryDeviceBinding.objects.filter(vehicle=legacy).delete()
        TelemetryDevice.objects.filter(pk__in=device_ids).delete()
        before = Vehicle.objects.count()
        output = self.run_command("--dry-run", "--replace-development-fleet")
        self.assertEqual(Vehicle.objects.count(), before)
        self.assertIn("Would delete unreferenced legacy vehicles: 1", output)
        self.assertIn("Would reconcile: 100 Guest Transport and 100 Supply", output)
        self.assertIn("Protected: Sprint 1 Demo Vehicle / LILYGO-001", output)

    def test_professional_fleet_counts_names_types_and_plate_distribution(self):
        self.run_command("--replace-development-fleet")
        seeded = self.seeded()
        guests = seeded.filter(device_id__startswith="FT-GT-")
        supplies = seeded.filter(device_id__startswith="FT-ST-")
        self.assertEqual(guests.count(), 100)
        self.assertEqual(supplies.count(), 100)
        self.assertEqual(Vehicle.objects.count(), 201)
        self.assertEqual(seeded.values("plate_number").distinct().count(), 200)
        forbidden = ("DEMO", "TEST", "SAMPLE", "DUMMY")
        self.assertFalse(
            any(word in vehicle.display_name.upper() for vehicle in seeded for word in forbidden)
        )
        self.assertTrue(guests.filter(vehicle_type=Vehicle.VehicleType.SHUTTLE_BUS).exists())
        self.assertTrue(supplies.filter(vehicle_type=Vehicle.VehicleType.SERVICE_TRUCK).exists())
        for queryset in (guests, supplies):
            counts = {digit: 0 for digit in range(10)}
            for plate in queryset.values_list("plate_number", flat=True):
                counts[int(plate[-1])] += 1
            self.assertEqual(counts, {digit: 10 for digit in range(10)})

    def test_all_professional_master_data_is_complete_unique_and_logical(self):
        self.run_command("--replace-development-fleet")
        seeded = list(self.seeded().order_by("device_id"))
        required = (
            "ownership_type",
            "supplier_name",
            "purchase_order_number",
            "acquisition_date",
            "purchase_price",
            "warranty_expiry_date",
            "registration_expiry_date",
            "insurance_expiry_date",
            "manufacturer",
            "model",
            "model_year",
            "plate_number",
            "passenger_capacity",
            "gvwr_kg",
            "vin",
            "engine_number",
            "chassis_number",
            "color",
            "fuel_type",
            "transmission_type",
        )
        self.assertEqual(len(seeded), 200)
        self.assertTrue(
            all(all(getattr(vehicle, field) for field in required) for vehicle in seeded)
        )
        self.assertTrue(
            all(vehicle.ownership_type == Vehicle.OwnershipType.COMPANY_OWNED for vehicle in seeded)
        )
        self.assertTrue(all(vehicle.purchase_currency == "PHP" for vehicle in seeded))
        self.assertEqual(len({vehicle.purchase_order_number for vehicle in seeded}), 200)
        self.assertEqual(len({vehicle.vin for vehicle in seeded}), 200)
        self.assertEqual(len({vehicle.engine_number for vehicle in seeded}), 200)
        self.assertEqual(len({vehicle.chassis_number for vehicle in seeded}), 200)
        forbidden = ("DEMO", "TEST", "SAMPLE", "DUMMY")
        generated_text = (
            " ".join(
                str(getattr(vehicle, field))
                for field in (
                    "display_name",
                    "supplier_name",
                    "purchase_order_number",
                    "vin",
                    "engine_number",
                    "chassis_number",
                )
            ).upper()
            for vehicle in seeded
        )
        self.assertFalse(any(word in text for text in generated_text for word in forbidden))
        today = date(2026, 9, 23)
        for vehicle in seeded:
            self.assertGreaterEqual(vehicle.acquisition_date.year, vehicle.model_year)
            self.assertLessEqual(vehicle.acquisition_date, today)
            self.assertGreater(vehicle.warranty_expiry_date, vehicle.acquisition_date)
            self.assertGreater(vehicle.registration_expiry_date, today)
            self.assertGreater(vehicle.insurance_expiry_date, vehicle.acquisition_date)
            if vehicle.device_id.startswith("FT-ST-"):
                self.assertIsNotNone(vehicle.payload_capacity_kg)

    def test_master_values_are_deterministic_across_repeat_runs(self):
        self.run_command("--replace-development-fleet")
        fields = (
            "device_id",
            "supplier_name",
            "purchase_order_number",
            "acquisition_date",
            "purchase_price",
            "warranty_expiry_date",
            "registration_expiry_date",
            "insurance_expiry_date",
            "vin",
            "engine_number",
            "chassis_number",
            "color",
        )
        first = list(self.seeded().order_by("device_id").values_list(*fields))
        self.run_command("--replace-development-fleet")
        self.assertEqual(
            list(self.seeded().order_by("device_id").values_list(*fields)),
            first,
        )

    def test_preserves_demo_primary_key_and_relationships_and_is_idempotent(self):
        protected_master = {
            field: getattr(self.protected, field)
            for field in (
                "display_name",
                "plate_number",
                "supplier_name",
                "purchase_order_number",
                "acquisition_date",
                "purchase_price",
                "warranty_expiry_date",
                "registration_expiry_date",
                "insurance_expiry_date",
            )
        }
        self.run_command("--replace-development-fleet")
        first_ids = list(self.seeded().order_by("device_id").values_list("pk", flat=True))
        self.run_command("--replace-development-fleet")
        self.assertEqual(
            list(self.seeded().order_by("device_id").values_list("pk", flat=True)),
            first_ids,
        )
        protected = Vehicle.objects.get(device_id="LILYGO-001")
        self.assertEqual(protected.pk, self.protected_pk)
        self.assertEqual(protected.display_name, "Sprint 1 Demo Vehicle")
        self.assertEqual(
            {field: getattr(protected, field) for field in protected_master},
            protected_master,
        )
        self.assertEqual(
            list(
                TelemetryDeviceBinding.objects.filter(vehicle=protected).values_list(
                    "pk", flat=True
                )
            ),
            self.protected_binding_ids,
        )
        self.assertEqual(self.seeded().count(), 200)

    def test_referenced_legacy_is_deactivated_and_unreferenced_legacy_is_deleted(self):
        referenced = Vehicle.objects.create(
            device_id="DEV-PAX-001", plate_number="OLD-001", display_name="Old referenced"
        )
        VehicleInspection.objects.create(
            vehicle=referenced,
            inspection_date=timezone.localdate(),
            inspection_type=VehicleInspection.InspectionType.PRE_TRIP,
            result=VehicleInspection.Result.PASSED,
            exterior_condition=VehicleInspection.Condition.OK,
            interior_condition=VehicleInspection.Condition.OK,
            tires_condition=VehicleInspection.Condition.OK,
            lights_condition=VehicleInspection.Condition.OK,
            brakes_condition=VehicleInspection.Condition.OK,
            fluids_condition=VehicleInspection.Condition.OK,
            safety_equipment_condition=VehicleInspection.Condition.OK,
            inspected_by=self.operator,
        )
        unreferenced = Vehicle.objects.create(
            device_id="DEV-LOG-001", plate_number="OLD-002", display_name="Old unreferenced"
        )
        unreferenced_device_ids = list(
            TelemetryDeviceBinding.objects.filter(vehicle=unreferenced).values_list(
                "device_id", flat=True
            )
        )
        TelemetryDeviceBinding.objects.filter(vehicle=unreferenced).delete()
        TelemetryDevice.objects.filter(pk__in=unreferenced_device_ids).delete()
        self.run_command("--replace-development-fleet")
        referenced.refresh_from_db()
        self.assertFalse(referenced.is_active)
        self.assertTrue(VehicleInspection.objects.filter(vehicle=referenced).exists())
        self.assertFalse(Vehicle.objects.filter(pk=unreferenced.pk).exists())

    def test_seed_creates_master_data_only(self):
        before = {
            "bindings": TelemetryDeviceBinding.objects.count(),
            "telemetry": TelemetryEvent.objects.count(),
            "inspections": VehicleInspection.objects.count(),
            "maintenance": VehicleMaintenanceRecord.objects.count(),
            "assignments": DispatchAssignment.objects.count(),
            "plans": DispatchPlan.objects.count(),
        }
        self.run_command("--replace-development-fleet")
        after = {
            "bindings": TelemetryDeviceBinding.objects.count(),
            "telemetry": TelemetryEvent.objects.count(),
            "inspections": VehicleInspection.objects.count(),
            "maintenance": VehicleMaintenanceRecord.objects.count(),
            "assignments": DispatchAssignment.objects.count(),
            "plans": DispatchPlan.objects.count(),
        }
        self.assertEqual(after, before)
        self.assertFalse(TelemetryEvent.objects.filter(vehicle__in=self.seeded()).exists())

    def test_default_reconcile_does_not_clean_legacy_vehicle(self):
        legacy = Vehicle.objects.create(
            device_id="DEV-LOG-001", plate_number="OLD-001", display_name="Old fleet"
        )
        output = self.run_command()
        self.assertTrue(Vehicle.objects.filter(pk=legacy.pk).exists())
        self.assertIn("--replace-development-fleet", output)

    def test_record_factory_is_deterministic(self):
        self.assertEqual(fleet_records(), fleet_records())
        self.assertEqual(len(fleet_records()), 200)
