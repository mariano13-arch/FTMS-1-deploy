from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Vehicle
from telemetry.models import TelemetryDevice, VehicleEmergencySOS


class VehicleEmergencySOSTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.vehicle = Vehicle.objects.create(
            device_id="LILYGO-002", plate_number="SOS-001", display_name="SOS Vehicle"
        )
        self.device = TelemetryDevice.objects.get(device_id="LILYGO-002")
        self.other_device = TelemetryDevice.objects.create(device_id="OTHER-DEVICE")

    def post(self, action, device_id="LILYGO-002"):
        return self.client.post("/api/v1/sos/", {"device_id": device_id, "action": action}, format="json")

    def staff_client(self):
        user = get_user_model().objects.create_user(
            username="sos-dispatch", password="Strong-test-password-42!", is_staff=True
        )
        StaffProfile.objects.create(user=user, role=StaffProfile.Role.DISPATCHER)
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_activate_without_coordinates_persists_bound_vehicle_and_no_guessed_driver(self):
        response = self.post("ACTIVATE")
        self.assertEqual(response.status_code, 201)
        event = VehicleEmergencySOS.objects.get()
        self.assertEqual(event.vehicle, self.vehicle)
        self.assertIsNone(event.driver)
        self.assertEqual(event.status, "ACTIVE")
        self.assertEqual(event.source, "PHYSICAL_BUTTON")

    def test_duplicate_activate_is_idempotent_and_other_device_is_unaffected(self):
        first = self.post("ACTIVATE")
        second = self.post("ACTIVATE")
        self.assertFalse(first.json()["duplicate"])
        self.assertTrue(second.json()["duplicate"])
        self.assertEqual(VehicleEmergencySOS.objects.count(), 1)
        self.assertFalse(VehicleEmergencySOS.objects.filter(device=self.other_device).exists())

    def test_clear_is_idempotent_and_history_is_preserved(self):
        self.post("ACTIVATE")
        cleared = self.post("CLEAR")
        duplicate = self.post("CLEAR")
        event = VehicleEmergencySOS.objects.get()
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(event.status, "CLEARED")
        self.assertIsNotNone(event.cleared_at)
        self.assertTrue(duplicate.json()["duplicate"])
        history = self.staff_client().get("/api/v1/sos/?device_id=LILYGO-002").json()["results"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "CLEARED")

    def test_active_sos_appears_in_fleet_current_state_and_clear_removes_it(self):
        self.post("ACTIVATE")
        client = self.staff_client()
        active = client.get("/api/v1/fleet-live/vehicles/").json()["vehicles"]
        item = next(row for row in active if row["vehicle_id"] == self.vehicle.pk)
        self.assertEqual(item["emergency_sos"]["status"], "ACTIVE")
        self.assertEqual(item["emergency_sos"]["source"], "PHYSICAL_BUTTON")
        self.post("CLEAR")
        cleared = client.get("/api/v1/fleet-live/vehicles/").json()["vehicles"]
        item = next(row for row in cleared if row["vehicle_id"] == self.vehicle.pk)
        self.assertIsNone(item["emergency_sos"])
