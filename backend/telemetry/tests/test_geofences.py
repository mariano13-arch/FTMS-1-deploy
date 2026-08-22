from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Vehicle
from telemetry.models import Geofence, GeofenceEvent, TelemetryEvent


class GeofenceApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="manager", password="test", is_staff=True
        )
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.FLEET_MANAGER)
        self.client.force_authenticate(self.user)
        self.vehicle = Vehicle.objects.create(
            device_id="GEO-001",
            plate_number="GEO-001",
            display_name="Geofence Van",
        )
        self.url = "/api/v1/fleet-live/geofences/"
        self.payload = {
            "name": "Oxford Operations Zone",
            "description": "Hotel loading and dispatch area",
            "category": "HOTEL",
            "shape_type": "POLYGON",
            "vertices": [
                {"latitude": 14.55, "longitude": 121.01},
                {"latitude": 14.55, "longitude": 121.03},
                {"latitude": 14.57, "longitude": 121.03},
                {"latitude": 14.57, "longitude": 121.01},
            ],
            "center": {"latitude": 14.56, "longitude": 121.02},
            "radius_meters": None,
            "color": "#008F8C",
            "show_on_map": True,
            "is_active": True,
        }

    def telemetry(self, event_id, sequence, latitude, longitude, recorded_at):
        return TelemetryEvent.objects.create(
            schema_version="1.0",
            event_id=event_id,
            sequence_number=sequence,
            vehicle=self.vehicle,
            recorded_at=recorded_at,
            location=Point(longitude, latitude, srid=4326),
            gnss_speed_kph=20,
            driving_event=TelemetryEvent.DrivingEvent.NORMAL,
        )

    def telemetry_payload(self, event_id, sequence, latitude, longitude, recorded_at):
        return {
            "schema_version": "1.0",
            "event_id": event_id,
            "sequence_number": sequence,
            "device_id": self.vehicle.device_id,
            "recorded_at": recorded_at.isoformat(),
            "latitude": latitude,
            "longitude": longitude,
            "gnss_speed_kph": 20,
            "rpm": None,
            "coolant_c": None,
            "engine_load_pct": None,
            "driving_event": "NORMAL",
        }

    def test_create_lists_and_returns_custom_boundary_details(self):
        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["name"], "Oxford Operations Zone")
        self.assertEqual(response.json()["shape_type"], "POLYGON")
        self.assertEqual(len(response.json()["vertices"]), 4)
        self.assertEqual(response.json()["events"], [])
        geofence = Geofence.objects.get()
        self.assertEqual(geofence.created_by, self.user)
        self.assertTrue(geofence.boundary.covers(Point(121.02, 14.56, srid=4326)))
        listing = self.client.get(self.url)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["results"][0]["event_count"], 0)

    def test_creation_backfills_entry_and_exit_history_from_real_telemetry(self):
        now = timezone.now()
        self.telemetry("outside-1", 1, 14.56, 121.05, now - timedelta(minutes=3))
        self.telemetry("inside-1", 2, 14.56, 121.02, now - timedelta(minutes=2))
        self.telemetry("outside-2", 3, 14.56, 121.05, now - timedelta(minutes=1))

        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            [event["event_type"] for event in response.json()["events"]],
            ["EXIT", "ENTER"],
        )
        self.assertEqual(response.json()["events"][0]["vehicle_name"], "Geofence Van")
        self.assertEqual(response.json()["current_vehicle_count"], 0)

    def test_new_telemetry_creates_idempotent_enter_and_exit_events(self):
        geofence_id = self.client.post(self.url, self.payload, format="json").json()["id"]
        now = timezone.now()
        outside = self.telemetry_payload("live-outside", 1, 14.56, 121.05, now)
        inside = self.telemetry_payload(
            "live-inside", 2, 14.56, 121.02, now + timedelta(seconds=10)
        )
        exited = self.telemetry_payload("live-exit", 3, 14.56, 121.05, now + timedelta(seconds=20))

        self.client.post("/api/v1/telemetry/", outside, format="json")
        self.client.post("/api/v1/telemetry/", inside, format="json")
        self.client.post("/api/v1/telemetry/", inside, format="json")
        self.client.post("/api/v1/telemetry/", exited, format="json")

        self.assertEqual(GeofenceEvent.objects.count(), 2)
        detail = self.client.get(f"{self.url}{geofence_id}/")
        self.assertEqual(
            [event["event_type"] for event in detail.json()["events"]],
            ["EXIT", "ENTER"],
        )

    def test_update_rebuilds_activity_and_invalid_boundaries_are_rejected(self):
        geofence_id = self.client.post(self.url, self.payload, format="json").json()["id"]
        updated = {
            **self.payload,
            "name": "Restricted loading zone",
            "category": "RESTRICTED",
            "color": "#CF4B4B",
        }
        response = self.client.patch(f"{self.url}{geofence_id}/", updated, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Restricted loading zone")
        invalid = {**self.payload, "vertices": self.payload["vertices"][:2]}
        self.assertEqual(self.client.post(self.url, invalid, format="json").status_code, 400)

    def test_geofences_require_staff_access(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get(self.url).status_code, (401, 403))
