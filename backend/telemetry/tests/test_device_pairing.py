from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Vehicle
from telemetry.models import TelemetryDevice, TelemetryDeviceBinding, TelemetryEvent


class TelemetryDevicePairingApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.manager = get_user_model().objects.create_user(
            username="device-manager",
            password="Strong-test-password-42!",
            is_staff=True,
        )
        StaffProfile.objects.create(
            user=self.manager,
            role=StaffProfile.Role.FLEET_MANAGER,
        )
        self.client.force_authenticate(self.manager)
        self.vehicle = Vehicle.objects.create(
            device_id="LEGACY-001",
            plate_number="PAIR-001",
            display_name="Pairing Vehicle",
        )
        self.other_vehicle = Vehicle.objects.create(
            device_id="LEGACY-002",
            plate_number="PAIR-002",
            display_name="Other Vehicle",
        )

    def register(self, device_id):
        return TelemetryDevice.objects.create(device_id=device_id)

    def release_legacy_binding(self, vehicle):
        binding = TelemetryDeviceBinding.objects.get(
            vehicle=vehicle,
            unpaired_at__isnull=True,
        )
        binding.unpaired_at = timezone.now()
        binding.unpaired_by = self.manager
        binding.save(update_fields=["unpaired_at", "unpaired_by"])

    def payload(self, device_id, event_id):
        return {
            "schema_version": "1.0",
            "event_id": event_id,
            "sequence_number": 1,
            "device_id": device_id,
            "recorded_at": timezone.now().isoformat(),
            "latitude": 14.5186,
            "longitude": 121.0196,
            "gnss_speed_kph": 38.2,
            "rpm": None,
            "coolant_c": 88,
            "engine_load_pct": 34,
            "driving_event": "NORMAL",
        }

    def test_legacy_vehicle_mapping_is_bootstrapped_and_lookup_is_safe(self):
        response = self.client.get("/api/v1/telemetry-devices/LEGACY-001/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "device_id": "LEGACY-001",
                "registration_status": "REGISTERED",
                "is_paired": True,
                "current_vehicle": {
                    "vehicle_id": self.vehicle.pk,
                    "plate_number": "PAIR-001",
                    "display_name": "Pairing Vehicle",
                    "compatibility_device_id": "LEGACY-001",
                },
            },
        )
        self.assertNotContains(response, "password")
        self.assertEqual(
            self.client.get("/api/v1/telemetry-devices/UNKNOWN/").status_code,
            404,
        )

    def test_registered_unpaired_device_can_pair_and_resolve_telemetry(self):
        self.register("NEW-001")
        self.release_legacy_binding(self.vehicle)

        response = self.client.post(
            "/api/v1/telemetry-devices/NEW-001/pair/",
            {"vehicle_id": self.vehicle.pk},
            format="json",
        )
        telemetry = self.client.post(
            "/api/v1/telemetry/",
            self.payload("NEW-001", "new-device-event"),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(telemetry.status_code, 201)
        event = TelemetryEvent.objects.get(event_id="new-device-event")
        self.assertEqual(event.device.device_id, "NEW-001")
        self.assertEqual(event.vehicle, self.vehicle)

    def test_unknown_or_unpaired_device_telemetry_is_rejected(self):
        self.register("UNPAIRED-001")

        unknown = self.client.post(
            "/api/v1/telemetry/",
            self.payload("UNKNOWN", "unknown-event"),
            format="json",
        )
        unpaired = self.client.post(
            "/api/v1/telemetry/",
            self.payload("UNPAIRED-001", "unpaired-event"),
            format="json",
        )

        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(unpaired.status_code, 400)
        self.assertEqual(unpaired.json()["device_id"], ["Device is not paired to a vehicle."])
        self.assertFalse(TelemetryEvent.objects.exists())

    def test_device_and_vehicle_current_pairing_conflicts_are_rejected(self):
        self.register("NEW-002")
        self.register("NEW-003")
        self.release_legacy_binding(self.vehicle)
        self.release_legacy_binding(self.other_vehicle)
        first = self.client.post(
            "/api/v1/telemetry-devices/NEW-002/pair/",
            {"vehicle_id": self.vehicle.pk},
            format="json",
        )

        device_conflict = self.client.post(
            "/api/v1/telemetry-devices/NEW-002/pair/",
            {"vehicle_id": self.other_vehicle.pk},
            format="json",
        )
        vehicle_conflict = self.client.post(
            "/api/v1/telemetry-devices/NEW-003/pair/",
            {"vehicle_id": self.vehicle.pk},
            format="json",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(device_conflict.status_code, 409)
        self.assertEqual(vehicle_conflict.status_code, 409)

    def test_replacement_changes_future_source_without_reassigning_history(self):
        old_payload = self.payload("LEGACY-001", "historical-event")
        old_response = self.client.post("/api/v1/telemetry/", old_payload, format="json")
        old_event = TelemetryEvent.objects.get(event_id="historical-event")
        replacement = self.register("REPLACEMENT-001")

        response = self.client.post(
            f"/api/v1/telemetry-devices/{replacement.device_id}/pair/",
            {"vehicle_id": self.vehicle.pk, "replace_current": True},
            format="json",
        )
        new_response = self.client.post(
            "/api/v1/telemetry/",
            self.payload("REPLACEMENT-001", "replacement-event"),
            format="json",
        )
        old_again = deepcopy(old_payload)
        old_again["event_id"] = "old-device-after-replacement"
        rejected = self.client.post("/api/v1/telemetry/", old_again, format="json")

        self.assertEqual(old_response.status_code, 201)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(new_response.status_code, 201)
        self.assertEqual(rejected.status_code, 400)
        old_event.refresh_from_db()
        self.assertEqual(old_event.vehicle, self.vehicle)
        self.assertEqual(old_event.device.device_id, "LEGACY-001")
        new_event = TelemetryEvent.objects.get(event_id="replacement-event")
        self.assertEqual(new_event.vehicle, self.vehicle)
        self.assertEqual(new_event.device, replacement)
        self.assertEqual(
            TelemetryDeviceBinding.objects.filter(vehicle=self.vehicle).count(),
            2,
        )

    def test_unpair_preserves_binding_history(self):
        response = self.client.post(
            "/api/v1/telemetry-devices/LEGACY-001/unpair/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_paired"])
        binding = TelemetryDeviceBinding.objects.get(device__device_id="LEGACY-001")
        self.assertIsNotNone(binding.unpaired_at)
        self.assertEqual(binding.unpaired_by, self.manager)

    def test_driver_cannot_register_pair_or_unpair_devices(self):
        driver = get_user_model().objects.create_user(
            username="ordinary-driver",
            password="Strong-test-password-42!",
        )
        self.client.force_authenticate(driver)

        self.assertEqual(
            self.client.post(
                "/api/v1/telemetry-devices/",
                {"device_id": "FORBIDDEN-001"},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/telemetry-devices/LEGACY-001/pair/",
                {"vehicle_id": self.other_vehicle.pk, "replace_current": True},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/telemetry-devices/LEGACY-001/unpair/",
                {},
                format="json",
            ).status_code,
            403,
        )

    def test_dispatcher_can_view_device_status_but_cannot_mutate_pairing(self):
        dispatcher = get_user_model().objects.create_user(
            username="device-dispatcher",
            password="Strong-test-password-42!",
            is_staff=True,
        )
        StaffProfile.objects.create(
            user=dispatcher,
            role=StaffProfile.Role.DISPATCHER,
        )
        self.client.force_authenticate(dispatcher)

        detail = self.client.get("/api/v1/telemetry-devices/LEGACY-001/")
        pair = self.client.post(
            "/api/v1/telemetry-devices/LEGACY-001/pair/",
            {"vehicle_id": self.other_vehicle.pk, "replace_current": True},
            format="json",
        )
        unpair = self.client.post(
            "/api/v1/telemetry-devices/LEGACY-001/unpair/",
            {},
            format="json",
        )

        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.json()["is_paired"])
        self.assertEqual(pair.status_code, 403)
        self.assertEqual(unpair.status_code, 403)

    def test_database_race_conflict_is_returned_safely(self):
        self.register("RACE-001")
        self.release_legacy_binding(self.vehicle)

        with patch(
            "telemetry.pairing.TelemetryDeviceBinding.objects.create",
            side_effect=IntegrityError,
        ):
            response = self.client.post(
                "/api/v1/telemetry-devices/RACE-001/pair/",
                {"vehicle_id": self.vehicle.pk},
                format="json",
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(),
            {"detail": "Device or vehicle received a conflicting pairing."},
        )

    def test_manager_can_register_device_but_pairing_never_auto_registers_unknown(self):
        created = self.client.post(
            "/api/v1/telemetry-devices/",
            {"device_id": "REGISTERED-001"},
            format="json",
        )
        unknown_pair = self.client.post(
            "/api/v1/telemetry-devices/NEVER-SEEN/pair/",
            {"vehicle_id": self.vehicle.pk},
            format="json",
        )

        self.assertEqual(created.status_code, 201)
        self.assertFalse(created.json()["is_paired"])
        self.assertEqual(unknown_pair.status_code, 404)
        self.assertFalse(TelemetryDevice.objects.filter(device_id="NEVER-SEEN").exists())
