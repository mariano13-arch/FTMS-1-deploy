from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase

from fleet.models import Vehicle


class VehicleTests(TestCase):
    def test_device_id_is_unique(self):
        Vehicle.objects.create(
            device_id="ONE", plate_number="PLATE-1", display_name="First"
        )
        with self.assertRaises(IntegrityError):
            Vehicle.objects.create(
                device_id="ONE", plate_number="PLATE-2", display_name="Second"
            )

    def test_plate_number_is_unique(self):
        Vehicle.objects.create(
            device_id="ONE", plate_number="PLATE-1", display_name="First"
        )
        with self.assertRaises(IntegrityError):
            Vehicle.objects.create(
                device_id="TWO", plate_number="PLATE-1", display_name="Second"
            )

    def test_seed_demo_vehicle_is_idempotent(self):
        output = StringIO()
        call_command("seed_demo_vehicle", stdout=output)
        call_command("seed_demo_vehicle", stdout=output)

        self.assertEqual(Vehicle.objects.filter(device_id="LILYGO-001").count(), 1)
        vehicle = Vehicle.objects.get(device_id="LILYGO-001")
        self.assertEqual(vehicle.plate_number, "DEMO-001")
        self.assertEqual(vehicle.display_name, "Sprint 1 Demo Vehicle")
        self.assertTrue(vehicle.is_active)
