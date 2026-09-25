from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Vehicle
from telemetry.models import TelemetryDevice, TelemetryDeviceBinding, TelemetryEvent


class DeviceTelemetryReportTests(TestCase):
    endpoint = "/api/v1/reports/device-telemetry/"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="device-reporter", is_staff=True, first_name="Fleet", last_name="Manager"
        )
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.FLEET_MANAGER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.vehicle = Vehicle.objects.create(
            device_id="VEH-RPT-1", plate_number="RPT-1", display_name="=Report Van"
        )
        self.paired = TelemetryDevice.objects.get(device_id="VEH-RPT-1")
        self.binding = TelemetryDeviceBinding.objects.get(
            device=self.paired, unpaired_at__isnull=True
        )
        self.moment = datetime(2026, 9, 20, 4, tzinfo=dt_timezone.utc)
        self.binding.paired_at = self.moment
        self.binding.paired_by = self.user
        self.binding.save(update_fields=["paired_at", "paired_by"])
        self.unpaired = TelemetryDevice.objects.create(device_id="UNPAIRED-1")
        self.retired = TelemetryDevice.objects.create(
            device_id="RETIRED-1",
            registration_status=TelemetryDevice.RegistrationStatus.RETIRED,
        )

    def telemetry(self, suffix, *, device=None, source="GNSS", obd="PHYSICAL_OBD", **values):
        device = device or self.paired
        defaults = {
            "schema_version": "1.2",
            "event_id": f"device-report-{suffix}",
            "sequence_number": int(suffix),
            "device": device,
            "vehicle": self.vehicle,
            "recorded_at": self.moment,
            "location": Point(121.01, 14.51, srid=4326),
            "position_source": source,
            "gnss_speed_kph": 20 if source == "GNSS" else None,
            "rpm": 1800 if obd else None,
            "coolant_c": 88 if obd else None,
            "engine_load_pct": 40 if obd else None,
            "obd_source": obd,
            "driving_event": TelemetryEvent.DrivingEvent.NORMAL,
        }
        defaults.update(values)
        return TelemetryEvent.objects.create(**defaults)

    def get(self, **params):
        return self.client.get(
            self.endpoint,
            {"date_from": "2026-09-20", "date_to": "2026-09-20", **params},
        )

    def test_current_kpis_and_truthful_availability_without_freshness_claims(self):
        self.telemetry("1")
        data = self.get().json()
        self.assertEqual(
            data["summary"],
            {
                "registered_devices": 2,
                "paired_devices": 1,
                "unpaired_devices": 1,
                "retired_devices": 1,
                "no_telemetry": 1,
            },
        )
        self.assertIsNone(data["meta"]["freshness_rule"])
        self.assertEqual(
            {row["value"]: row["count"] for row in data["breakdowns"]["availability"]},
            {"RECEIVED": 1, "NO_TELEMETRY": 1},
        )
        encoded = str(data).lower()
        self.assertNotIn("online", encoded)
        self.assertNotIn("offline", encoded)
        self.assertNotIn("stale", encoded)

    def test_latest_event_controls_provenance_and_trend_uses_recorded_at(self):
        self.telemetry("1")
        latest = self.telemetry(
            "2",
            source=TelemetryEvent.PositionSource.SIMULATED_TEST,
            obd=TelemetryEvent.ObdSource.SIMULATED_TEST,
            recorded_at=self.moment + timedelta(hours=1),
            gnss_speed_kph=None,
        )
        self.telemetry("3", recorded_at=self.moment - timedelta(days=2))
        data = self.get().json()
        row = next(row for row in data["devices"]["results"] if row["id"] == self.paired.pk)
        self.assertEqual(row["latest_telemetry"]["id"], latest.pk)
        self.assertEqual(row["latest_telemetry"]["position_source_label"], "Simulated Test")
        self.assertEqual(row["latest_telemetry"]["obd_source_label"], "Simulated Test")
        self.assertEqual(data["trend"], [{"date": "2026-09-20", "count": 2}])
        no_data = next(row for row in data["devices"]["results"] if row["id"] == self.unpaired.pk)
        self.assertIsNone(no_data["latest_telemetry"])
        self.assertEqual(no_data["telemetry_state_label"], "No Telemetry")

    def test_device_and_binding_filters_pagination_and_private_details(self):
        self.telemetry("1")
        data = self.get(
            registry_status="REGISTERED",
            binding_state="PAIRED",
            telemetry_state="RECEIVED",
            position_source="GNSS",
            obd_source="PHYSICAL_OBD",
            vehicle=self.vehicle.pk,
            device_search="Report Van",
            binding_device=self.paired.pk,
            binding_vehicle=self.vehicle.pk,
            binding_history_state="ACTIVE",
            binding_search="VEH-RPT",
        ).json()
        self.assertEqual(data["devices"]["count"], 1)
        self.assertEqual(data["bindings"]["count"], 1)
        self.assertEqual(data["devices"]["page_size"], 15)
        self.assertEqual(data["bindings"]["page_size"], 15)
        row = data["bindings"]["results"][0]
        self.assertEqual(row["binding_state"], "ACTIVE")
        self.assertEqual(row["paired_by"], "Fleet Manager")
        self.assertTrue({"email", "password", "secret", "pair", "unpair"}.isdisjoint(row))
        self.assertEqual(self.get(page_size=101).status_code, 400)

    def test_csv_is_complete_filtered_safe_and_has_no_raw_telemetry_or_location(self):
        self.telemetry("1")
        params = {"date_from": "2026-09-20", "date_to": "2026-09-20"}
        devices = self.client.get(
            "/api/v1/reports/device-telemetry/devices/csv/",
            {**params, "registry_status": "REGISTERED"},
        )
        bindings = self.client.get(
            "/api/v1/reports/device-telemetry/bindings/csv/",
            {**params, "binding_history_state": "ACTIVE"},
        )
        device_body = b"".join(devices.streaming_content).decode()
        binding_body = b"".join(bindings.streaming_content).decode()
        self.assertIn("UNPAIRED-1", device_body)
        self.assertIn("'=Report Van", device_body + binding_body)
        self.assertNotIn("latitude", device_body.lower())
        self.assertNotIn("longitude", device_body.lower())
        self.assertEqual(
            self.client.get("/api/v1/reports/device-telemetry/telemetry/csv/", params).status_code,
            400,
        )
