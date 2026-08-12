from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from fleet.models import Vehicle, VehicleDocument, VehicleInspection


class SeedVehicleRegistryTests(TestCase):
    seed_ids = [
        *(f"DEV-PAX-{index:03d}" for index in range(1, 11)),
        *(f"DEV-LOG-{index:03d}" for index in range(1, 11)),
    ]

    def run_seed(self):
        output = StringIO()
        call_command("seed_vehicle_registry", stdout=output)
        return output.getvalue()

    def test_creates_exactly_twenty_deterministic_safe_registry_records(self):
        unrelated = Vehicle.objects.create(
            device_id="MANUAL-001",
            plate_number="MANUAL-001",
            display_name="Existing Manual Vehicle",
        )

        output = self.run_seed()
        seeded = Vehicle.objects.filter(device_id__in=self.seed_ids)

        self.assertEqual(seeded.count(), 20)
        self.assertEqual(seeded.filter(device_id__startswith="DEV-PAX-").count(), 10)
        self.assertEqual(seeded.filter(device_id__startswith="DEV-LOG-").count(), 10)
        self.assertEqual(seeded.filter(is_active=True).count(), 18)
        self.assertEqual(seeded.filter(is_active=False).count(), 2)
        self.assertEqual(seeded.values("device_id").distinct().count(), 20)
        self.assertEqual(seeded.values("plate_number").distinct().count(), 20)
        self.assertFalse(seeded.filter(payload_capacity_kg__lt=0).exists())
        self.assertFalse(seeded.filter(gvwr_kg__lt=0).exists())
        self.assertEqual(VehicleInspection.objects.count(), 0)
        self.assertEqual(VehicleDocument.objects.count(), 0)
        self.assertTrue(Vehicle.objects.filter(pk=unrelated.pk).exists())
        self.assertIn("20 created, 0 existing", output)

    def test_rerun_is_idempotent_and_preserves_manual_edits(self):
        self.run_seed()
        edited = Vehicle.objects.get(device_id="DEV-PAX-001")
        edited.display_name = "Manually Edited Demo Vehicle"
        edited.save(update_fields=["display_name", "updated_at"])

        output = self.run_seed()

        self.assertEqual(Vehicle.objects.filter(device_id__in=self.seed_ids).count(), 20)
        edited.refresh_from_db()
        self.assertEqual(edited.display_name, "Manually Edited Demo Vehicle")
        self.assertIn("0 created, 20 existing", output)
