from datetime import datetime, timedelta
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Driver, Vehicle
from telemetry import demo
from telemetry.models import TelemetryEvent
from transport_requests.models import DispatchAssignment, TransportRequest


class FleetLiveApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="dispatcher", password="Strong-test-password-42!", is_staff=True
        )
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.DISPATCHER)
        self.client.force_authenticate(self.user)
        self.live = Vehicle.objects.create(
            device_id="LIVE-001", plate_number="LIVE-001", display_name="Live Shuttle"
        )
        self.missing = Vehicle.objects.create(
            device_id="MISSING-001", plate_number="MISS-001", display_name="No Telemetry Van"
        )
        self.offline = Vehicle.objects.create(
            device_id="OFFLINE-001",
            plate_number="OFF-001",
            display_name="Inactive Sedan",
            is_active=False,
        )

    def test_demo_states_use_only_the_four_supported_fleet_labels(self):
        expected = {
            "DEMO-001": "stale",
            "DEMO-002": "no_telemetry",
            "DEMO-004": "offline",
            "DEMO-006": "live",
        }

        self.assertEqual(
            {device_id: demo.state(SimpleNamespace(device_id=device_id)) for device_id in expected},
            expected,
        )

    def telemetry(
        self,
        vehicle,
        recorded_at,
        *,
        event_id=None,
        sequence_number=1,
        longitude=121.02,
        latitude=14.56,
        driving_event=TelemetryEvent.DrivingEvent.NORMAL,
    ):
        return TelemetryEvent.objects.create(
            schema_version="1.0", event_id=event_id or f"event-{vehicle.device_id}",
            sequence_number=sequence_number, vehicle=vehicle, recorded_at=recorded_at,
            location=Point(longitude, latitude, srid=4326),
            gnss_speed_kph=22, rpm=1200, coolant_c=82, engine_load_pct=30,
            driving_event=driving_event,
        )

    def test_lists_only_authoritative_positions_with_honest_states(self):
        now = timezone.now()
        self.telemetry(self.live, now)
        self.telemetry(self.offline, now)

        response = self.client.get("/api/v1/fleet-live/vehicles/")

        self.assertEqual(response.status_code, 200)
        vehicles = {item["device_id"]: item for item in response.json()["vehicles"]}
        self.assertEqual(vehicles["LIVE-001"]["telemetry_state"], "live")
        self.assertEqual(vehicles["LIVE-001"]["telemetry"]["latitude"], 14.56)
        self.assertEqual(vehicles["MISSING-001"]["telemetry_state"], "no_telemetry")
        self.assertIsNone(vehicles["MISSING-001"]["telemetry"])
        self.assertEqual(vehicles["OFFLINE-001"]["telemetry_state"], "offline")
        self.assertEqual(
            response.json()["capabilities"],
            {
                "telemetry_trail": True,
                "safety_events": True,
                "geofence": True,
                "demo_telemetry": True,
            },
        )
        self.assertEqual(
            response.json()["demo_telemetry"],
            {"enabled": False, "active": False, "simulated_vehicle_count": 0},
        )
        self.assertEqual(vehicles["LIVE-001"]["telemetry"]["telemetry_source"], "real")
        self.assertFalse(vehicles["LIVE-001"]["telemetry"]["is_demo_telemetry"])

    @override_settings(
        FTMS_DEMO_TELEMETRY_ENABLED=True,
        FTMS_DEMO_TELEMETRY_CENTER_LATITUDE="14.5652",
        FTMS_DEMO_TELEMETRY_CENTER_LONGITUDE="121.0286",
        FTMS_DEMO_TELEMETRY_RADIUS_METERS="1200",
    )
    def test_demo_overlay_is_explicit_non_persistent_and_never_replaces_real_data(self):
        now = timezone.now()
        real = self.telemetry(self.live, now)

        response = self.client.get("/api/v1/fleet-live/vehicles/")

        self.assertEqual(response.status_code, 200)
        vehicles = {item["device_id"]: item for item in response.json()["vehicles"]}
        self.assertEqual(
            response.json()["demo_telemetry"],
            {"enabled": True, "active": True, "simulated_vehicle_count": 2},
        )
        self.assertEqual(vehicles["LIVE-001"]["telemetry_state"], "live")
        self.assertEqual(vehicles["LIVE-001"]["telemetry"]["telemetry_source"], "real")
        self.assertEqual(vehicles["LIVE-001"]["telemetry"]["latitude"], real.location.y)
        self.assertEqual(vehicles["MISSING-001"]["telemetry_state"], "live")
        self.assertEqual(vehicles["MISSING-001"]["telemetry"]["telemetry_source"], "demo")
        self.assertTrue(vehicles["MISSING-001"]["telemetry"]["is_demo_telemetry"])
        self.assertLessEqual(
            datetime.fromisoformat(
                vehicles["MISSING-001"]["telemetry"]["recorded_at"].replace("Z", "+00:00")
            ),
            timezone.now(),
        )
        self.assertEqual(vehicles["OFFLINE-001"]["telemetry_state"], "offline")
        self.assertEqual(vehicles["OFFLINE-001"]["telemetry"]["telemetry_source"], "demo")
        self.assertEqual(vehicles["OFFLINE-001"]["telemetry"]["speed_kph"], 0)
        self.assertFalse(TelemetryEvent.objects.filter(vehicle=self.missing).exists())

    @override_settings(
        FTMS_DEMO_TELEMETRY_ENABLED=True,
        FTMS_DEMO_TELEMETRY_CENTER_LATITUDE="",
        FTMS_DEMO_TELEMETRY_CENTER_LONGITUDE="",
    )
    def test_misconfigured_demo_mode_does_not_generate_locations(self):
        response = self.client.get("/api/v1/fleet-live/vehicles/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["demo_telemetry"]["enabled"])
        self.assertFalse(response.json()["demo_telemetry"]["active"])
        self.assertIn("configuration_error", response.json()["demo_telemetry"])
        vehicle = next(
            item for item in response.json()["vehicles"] if item["device_id"] == "MISSING-001"
        )
        self.assertEqual(vehicle["telemetry_state"], "no_telemetry")
        self.assertIsNone(vehicle["telemetry"])

    def test_stale_position_and_existing_assignment_context_are_exposed(self):
        self.telemetry(self.live, timezone.now() - timedelta(hours=1))
        driver = Driver.objects.create(driver_code="DRV-001", first_name="Ana", last_name="Santos")
        item = TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference="HMS-LIVE-1",
            request_type=TransportRequest.RequestType.GUEST_TRANSFER,
            request_category=TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            requester_name="Front Desk", pickup_name="Hotel", pickup_address="Makati",
            pickup_latitude="14.560000", pickup_longitude="121.020000",
            destination_name="Airport", destination_address="Pasay",
            destination_latitude="14.508600", destination_longitude="121.019800",
            scheduled_pickup_at=timezone.now() + timedelta(hours=1), passenger_count=2,
            status=TransportRequest.Status.READY_FOR_DISPATCH, assigned_vehicle=self.live,
            created_by=self.user, approved_by=self.user, approved_at=timezone.now(),
        )
        DispatchAssignment.objects.create(
            transport_request=item, vehicle=self.live, driver=driver,
            selection_mode=DispatchAssignment.SelectionMode.OPTIMIZED, confirmed_by=self.user,
            execution_status=DispatchAssignment.ExecutionStatus.EN_ROUTE_TO_PICKUP,
        )

        vehicle = self.client.get("/api/v1/fleet-live/vehicles/").json()["vehicles"][0]

        self.assertEqual(vehicle["telemetry_state"], "stale")
        self.assertEqual(vehicle["active_assignment"]["request_number"], item.request_number)
        self.assertEqual(vehicle["active_assignment"]["driver_name"], "Ana Santos")
        self.assertEqual(vehicle["active_assignment"]["execution_status"], "EN_ROUTE_TO_PICKUP")

    def test_endpoint_requires_staff_authentication(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get("/api/v1/fleet-live/vehicles/").status_code, 401)

    def test_returns_recent_real_trail_in_chronological_order(self):
        now = timezone.now()
        self.telemetry(
            self.live, now - timedelta(minutes=2), event_id="trail-1",
            sequence_number=1, longitude=121.01, latitude=14.51,
        )
        self.telemetry(
            self.live, now - timedelta(minutes=1), event_id="trail-2",
            sequence_number=2, longitude=121.02, latitude=14.52,
        )

        response = self.client.get(f"/api/v1/fleet-live/vehicles/{self.live.pk}/trail/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["device_id"], "LIVE-001")
        self.assertEqual(
            [point["event_id"] for point in response.json()["points"]],
            ["trail-1", "trail-2"],
        )
        self.assertEqual(response.json()["points"][1]["latitude"], 14.52)

    def test_returns_only_supported_real_safety_events_as_map_pins(self):
        now = timezone.now()
        self.telemetry(
            self.live, now, event_id="brake-1",
            driving_event=TelemetryEvent.DrivingEvent.HARSH_BRAKING,
        )
        self.telemetry(
            self.missing, now, event_id="acceleration-1",
            driving_event=TelemetryEvent.DrivingEvent.HARSH_ACCELERATION,
        )
        self.telemetry(
            self.offline,
            now,
            event_id="normal-1",
            driving_event=TelemetryEvent.DrivingEvent.NORMAL,
        )

        response = self.client.get("/api/v1/fleet-live/safety-events/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["events"]), 2)
        self.assertEqual(
            {event["event_id"] for event in response.json()["events"]},
            {"brake-1", "acceleration-1"},
        )
        self.assertNotIn("normal-1", {event["event_id"] for event in response.json()["events"]})

    def test_trail_and_safety_event_endpoints_require_staff_authentication(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.get(f"/api/v1/fleet-live/vehicles/{self.live.pk}/trail/").status_code,
            401,
        )
        self.assertEqual(self.client.get("/api/v1/fleet-live/safety-events/").status_code, 401)
