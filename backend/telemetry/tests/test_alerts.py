from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point, Polygon
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Vehicle, VehicleInspection, VehicleMaintenanceRecord
from telemetry.models import Geofence, GeofenceEvent, TelemetryEvent


@override_settings(DISPATCH_TELEMETRY_MAX_AGE_SECONDS=300)
class ActiveAttentionApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="alerts-manager", is_staff=True)
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.FLEET_MANAGER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.now = timezone.now()

    def vehicle(self, code):
        return Vehicle.objects.create(device_id=code, plate_number=code, display_name=f"Vehicle {code}")

    def telemetry(self, vehicle, recorded_at, event_id, driving_event="NORMAL"):
        return TelemetryEvent.objects.create(
            schema_version="1.0", event_id=event_id, sequence_number=1,
            vehicle=vehicle, recorded_at=recorded_at,
            location=Point(121.02, 14.56, srid=4326), gnss_speed_kph=25,
            driving_event=driving_event,
        )

    def inspection(self, vehicle, result, date=None):
        return VehicleInspection.objects.create(
            vehicle=vehicle, inspection_date=date or timezone.localdate(),
            inspection_type=VehicleInspection.InspectionType.PRE_TRIP, result=result,
            exterior_condition="OK", interior_condition="OK", tires_condition="OK",
            lights_condition="OK", brakes_condition="OK", fluids_condition="OK",
            safety_equipment_condition="OK", inspected_by=self.user,
        )

    def test_derives_only_current_authoritative_attention_and_truthful_summary(self):
        stale = self.vehicle("STALE-001")
        missing = self.vehicle("MISSING-001")
        fresh = self.vehicle("FRESH-001")
        needs = self.vehicle("NEEDS-001")
        self.telemetry(stale, self.now - timedelta(minutes=10), "stale-event")
        self.telemetry(fresh, self.now, "fresh-safety", "SHARP_TURN")
        self.telemetry(needs, self.now, "fresh-needs")
        self.inspection(stale, VehicleInspection.Result.FAILED)
        self.inspection(fresh, VehicleInspection.Result.NEEDS_ATTENTION, timezone.localdate() - timedelta(days=1))
        self.inspection(fresh, VehicleInspection.Result.PASSED)
        self.inspection(needs, VehicleInspection.Result.NEEDS_ATTENTION)
        VehicleMaintenanceRecord.objects.create(vehicle=stale, title="Open work", created_by=self.user, status="OPEN")
        VehicleMaintenanceRecord.objects.create(vehicle=needs, title="Scheduled work", created_by=self.user, status="SCHEDULED", scheduled_at=self.now + timedelta(days=1))
        VehicleMaintenanceRecord.objects.create(vehicle=needs, title="Current work", created_by=self.user, status="IN_PROGRESS", started_at=self.now)
        VehicleMaintenanceRecord.objects.create(vehicle=fresh, title="Done", created_by=self.user, status="COMPLETED", completed_at=self.now)
        VehicleMaintenanceRecord.objects.create(vehicle=fresh, title="Cancelled", created_by=self.user, status="CANCELLED")
        geofence = Geofence.objects.create(
            name="Restricted", category="RESTRICTED", shape_type="POLYGON",
            boundary=Polygon(((121, 14.5), (121.1, 14.5), (121.1, 14.6), (121, 14.6), (121, 14.5)), srid=4326),
            center=Point(121.05, 14.55, srid=4326), created_by=self.user,
        )
        safety_event = TelemetryEvent.objects.get(event_id="fresh-safety")
        GeofenceEvent.objects.create(geofence=geofence, vehicle=fresh, telemetry_event=safety_event, event_type="ENTER", occurred_at=self.now, location=safety_event.location)

        response = self.client.get("/api/v1/alerts/active-attention/")

        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.json()["results"]}
        stale_item = next(
            item for item in response.json()["results"]
            if item["id"] == f"telemetry:{stale.pk}:stale"
        )
        self.assertEqual(stale_item["condition"], "STALE_TELEMETRY")
        self.assertIn(f"telemetry:{missing.pk}:no_telemetry", ids)
        self.assertIn("inspection:%s" % stale.inspections.get().pk, ids)
        self.assertIn("inspection:%s" % needs.inspections.get().pk, ids)
        self.assertNotIn("inspection:%s" % fresh.inspections.first().pk, ids)
        self.assertEqual(sum(item["source"] == "MAINTENANCE" for item in response.json()["results"]), 3)
        self.assertEqual(response.json()["summary"], {
            "active_attention": 7,
            "safety_events_today": 1,
            "restricted_entries_today": 1,
            "vehicle_device_attention": 2,
        })
        for item in response.json()["results"]:
            self.assertNotIn("severity", item)
            self.assertNotIn("acknowledged", item)
            self.assertNotIn("resolved", item)

    def test_filters_and_paginates_without_duplicate_source_conditions(self):
        vehicle = self.vehicle("PAGE-001")
        for number in range(16):
            VehicleMaintenanceRecord.objects.create(
                vehicle=vehicle, title=f"Work {number}", created_by=self.user, status="OPEN"
            )
        response = self.client.get(
            "/api/v1/alerts/active-attention/",
            {"source": "MAINTENANCE", "search": "PAGE-001", "page_size": 15},
        )
        self.assertEqual(response.json()["count"], 16)
        self.assertEqual(len(response.json()["results"]), 15)
        self.assertEqual(len({item["id"] for item in response.json()["results"]}), 15)
        self.assertIsNotNone(response.json()["next"])

    def test_requires_staff_and_rejects_unknown_filters(self):
        self.assertEqual(self.client.get("/api/v1/alerts/active-attention/?unexpected=true").status_code, 400)
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get("/api/v1/alerts/active-attention/").status_code, (401, 403))
