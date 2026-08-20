from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from fleet.models import Driver, Vehicle
from telemetry.models import TelemetryEvent
from transport_requests import routing
from transport_requests.models import DispatchAssignment, TransportRequest


@override_settings(DISPATCH_TELEMETRY_MAX_AGE_SECONDS=300)
class DriverTripOperationalApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.operator = get_user_model().objects.create_user(
            username="operations-operator", is_staff=True
        )
        self.driver_user = get_user_model().objects.create_user(
            username="operations-driver", password="Strong-test-password-42!"
        )
        self.driver = Driver.objects.create(
            driver_code="DRV-OPS-001",
            first_name="Maria",
            last_name="Reyes",
            linked_user=self.driver_user,
        )
        self.other_user = get_user_model().objects.create_user(
            username="operations-other", password="Strong-test-password-42!"
        )
        self.other_driver = Driver.objects.create(
            driver_code="DRV-OPS-002",
            first_name="Jose",
            last_name="Santos",
            linked_user=self.other_user,
        )
        self.vehicle = Vehicle.objects.create(
            device_id="OPS-VEH-001",
            plate_number="OPS-123",
            display_name="Operations Van",
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=8,
        )
        self.trip = TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference="OPS-TRIP",
            request_type=TransportRequest.RequestType.GUEST_TRANSFER,
            request_category=TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            requester_name="Front Desk",
            requester_contact="internal-contact-not-driver-approved",
            pickup_name="FTMS Hotel",
            pickup_address="Makati City",
            pickup_latitude="14.565200",
            pickup_longitude="121.028600",
            destination_name="Airport",
            destination_address="Pasay City",
            destination_latitude="14.508600",
            destination_longitude="121.019800",
            scheduled_pickup_at=timezone.now() + timedelta(hours=2),
            estimated_duration_minutes=60,
            required_vehicle_type=Vehicle.VehicleType.VAN,
            passenger_count=4,
            status=TransportRequest.Status.APPROVED,
            assigned_vehicle=self.vehicle,
            created_by=self.operator,
        )
        self.assignment = DispatchAssignment.objects.create(
            transport_request=self.trip,
            vehicle=self.vehicle,
            driver=self.driver,
            selection_mode=DispatchAssignment.SelectionMode.MANUAL,
            override_reason="Controlled operations test",
            confirmed_by=self.operator,
        )
        self.route_url = f"/api/v1/driver-trips/{self.trip.pk}/route/"
        self.position_url = f"/api/v1/driver-trips/{self.trip.pk}/vehicle-position/"

    def route_result(self):
        return {
            "request_id": str(self.trip.pk),
            "traffic_mode": "live",
            "distance_meters": 12400,
            "duration_seconds": 1860,
            "traffic_delay_seconds": 360,
            "departure_time": "2026-08-18T10:00:00+08:00",
            "arrival_time": "2026-08-18T10:31:00+08:00",
            "geometry": {
                "type": "LineString",
                "coordinates": [[121.0286, 14.5652], [121.0198, 14.5086]],
            },
            "provider_internal": "must-not-leak",
        }

    def create_event(self, *, recorded_at):
        return TelemetryEvent.objects.create(
            schema_version="1.0",
            event_id=f"ops-{TelemetryEvent.objects.count()}",
            sequence_number=TelemetryEvent.objects.count() + 1,
            vehicle=self.vehicle,
            recorded_at=recorded_at,
            location=Point(121.021, 14.55, srid=4326),
            gnss_speed_kph=Decimal("22.50"),
            driving_event=TelemetryEvent.DrivingEvent.NORMAL,
        )

    @patch("transport_requests.driver_views.routing.get_route")
    def test_own_route_uses_authorized_request_and_safe_fields(self, get_route_mock):
        get_route_mock.return_value = self.route_result()
        self.client.force_login(self.driver_user)

        response = self.client.get(f"{self.route_url}?origin=0,0&destination=1,1")

        self.assertEqual(response.status_code, 200)
        get_route_mock.assert_called_once_with(self.trip)
        route = response.json()["route"]
        self.assertEqual(route["geometry"]["type"], "LineString")
        self.assertEqual(route["distance_meters"], 12400)
        self.assertEqual(route["duration_seconds"], 1860)
        self.assertEqual(route["traffic_delay_seconds"], 360)
        self.assertNotIn("request_id", route)
        self.assertNotIn("provider_internal", route)

    def test_route_and_position_require_auth_and_assignment_ownership(self):
        self.assertEqual(self.client.get(self.route_url).status_code, 401)
        self.assertEqual(self.client.get(self.position_url).status_code, 401)

        self.client.force_login(self.other_user)
        self.assertEqual(self.client.get(self.route_url).status_code, 404)
        self.assertEqual(self.client.get(self.position_url).status_code, 404)

    @patch(
        "transport_requests.driver_views.routing.get_route",
        side_effect=routing.RouteServiceError,
    )
    def test_route_provider_failure_is_controlled_without_fallback(self, _get_route_mock):
        self.client.force_login(self.driver_user)

        response = self.client.get(self.route_url)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"detail": "Route currently unavailable."})
        self.assertNotIn("geometry", response.json())

    def test_missing_vehicle_telemetry_is_clean(self):
        self.client.force_login(self.driver_user)

        response = self.client.get(self.position_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"vehicle_position": None})

    def test_vehicle_position_preserves_timestamp_and_existing_freshness_rule(self):
        now = datetime(2026, 8, 18, 4, 0, tzinfo=UTC)
        event = self.create_event(recorded_at=now - timedelta(seconds=301))
        self.client.force_login(self.driver_user)

        with patch("transport_requests.driver_views.timezone.now", return_value=now):
            response = self.client.get(self.position_url)

        self.assertEqual(response.status_code, 200)
        position = response.json()["vehicle_position"]
        self.assertEqual(
            set(position), {"latitude", "longitude", "recorded_at", "is_stale"}
        )
        self.assertEqual(
            datetime.fromisoformat(position["recorded_at"].replace("Z", "+00:00")),
            event.recorded_at,
        )
        self.assertTrue(position["is_stale"])
        self.assertAlmostEqual(position["latitude"], 14.55)
        self.assertAlmostEqual(position["longitude"], 121.021)
        for private_field in (
            "device_id",
            "event_id",
            "sequence_number",
            "rpm",
            "requester_contact",
        ):
            self.assertNotIn(private_field, position)

    def test_fresh_vehicle_position_is_not_marked_stale(self):
        now = timezone.now()
        self.create_event(recorded_at=now - timedelta(seconds=30))
        self.client.force_login(self.driver_user)

        with patch("transport_requests.driver_views.timezone.now", return_value=now):
            response = self.client.get(self.position_url)

        self.assertFalse(response.json()["vehicle_position"]["is_stale"])
