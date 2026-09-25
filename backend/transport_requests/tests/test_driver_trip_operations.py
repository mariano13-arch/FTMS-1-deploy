from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import call, patch

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from fleet.models import Driver, Vehicle
from telemetry.models import TelemetryEvent
from transport_requests import routing
from transport_requests.models import DispatchAssignment, TransportRequest


@override_settings(
    DISPATCH_TELEMETRY_MAX_AGE_SECONDS=300,
    DISPATCH_SIMULATED_TELEMETRY_MAX_AGE_SECONDS=86400,
)
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
            status=TransportRequest.Status.READY_FOR_DISPATCH,
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
            accepted_at=timezone.now(),
            accepted_by=self.driver_user,
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

    @patch("transport_requests.driver_views.routing.get_route_between")
    def test_own_route_uses_assigned_vehicle_position_to_pickup(self, get_route_mock):
        get_route_mock.return_value = self.route_result()
        event = self.create_event(recorded_at=timezone.now())
        self.client.force_login(self.driver_user)

        response = self.client.get(f"{self.route_url}?origin=0,0&destination=1,1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            get_route_mock.call_args_list,
            [
                call(
                    str(self.trip.pk),
                    [121.0286, 14.5652],
                    [121.0198, 14.5086],
                ),
                call(
                    f"driver:{self.assignment.pk}:TO_PICKUP:{event.pk}",
                    [121.021, 14.55],
                    [121.0286, 14.5652],
                ),
            ],
        )
        payload = response.json()["route"]
        self.assertEqual(payload["phase"], "TO_PICKUP")
        self.assertEqual(payload["execution_status"], "ASSIGNED")
        self.assertEqual(payload["vehicle_position"]["source"], "GNSS")
        self.assertEqual(payload["planned_route_status"], "AVAILABLE")
        self.assertEqual(payload["planned_route"]["distance_meters"], 12400)
        route = payload["route"]
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

    @patch("transport_requests.driver_views.routing.get_route_between", side_effect=routing.RouteServiceError)
    def test_route_provider_failure_is_controlled_without_fallback(self, _get_route_mock):
        self.create_event(recorded_at=timezone.now())
        self.client.force_login(self.driver_user)

        response = self.client.get(self.route_url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()["route"]
        self.assertEqual(payload["route_status"], "TEMPORARILY_UNAVAILABLE")
        self.assertIsNone(payload["route"])

    def test_missing_vehicle_telemetry_is_clean(self):
        self.client.force_login(self.driver_user)

        response = self.client.get(self.position_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"vehicle_position": None})

        route = self.client.get(self.route_url).json()["route"]
        self.assertEqual(route["route_status"], "POSITION_UNAVAILABLE")
        self.assertIsNone(route["vehicle_position"])
        self.assertIsNone(route["route"])

    @patch("transport_requests.driver_views.routing.get_route_between")
    def test_pickup_and_destination_phases_use_authoritative_endpoints(self, route_mock):
        route_mock.return_value = self.route_result()
        event = self.create_event(recorded_at=timezone.now())
        self.client.force_login(self.driver_user)

        self.assignment.execution_status = DispatchAssignment.ExecutionStatus.AT_PICKUP
        self.assignment.save(update_fields=["execution_status"])
        response = self.client.get(self.route_url)
        self.assertEqual(response.json()["route"]["phase"], "TO_DESTINATION")
        route_mock.assert_called_with(
            f"driver:{self.assignment.pk}:TO_DESTINATION:pickup",
            [121.0286, 14.5652],
            [121.0198, 14.5086],
        )

        self.assignment.execution_status = DispatchAssignment.ExecutionStatus.IN_TRANSIT
        self.assignment.save(update_fields=["execution_status"])
        response = self.client.get(self.route_url)
        self.assertEqual(response.json()["route"]["phase"], "TO_DESTINATION")
        route_mock.assert_called_with(
            f"driver:{self.assignment.pk}:TO_DESTINATION:{event.pk}",
            [121.021, 14.55],
            [121.0198, 14.5086],
        )

    def test_arrived_and_completed_have_no_active_route_and_do_not_mutate_request(self):
        self.create_event(recorded_at=timezone.now())
        self.client.force_login(self.driver_user)
        for execution_status, phase in (
            (DispatchAssignment.ExecutionStatus.AT_DESTINATION, "ARRIVED"),
            (DispatchAssignment.ExecutionStatus.COMPLETED, "COMPLETED"),
        ):
            self.assignment.execution_status = execution_status
            self.assignment.save(update_fields=["execution_status"])
            payload = self.client.get(self.route_url).json()["route"]
            self.assertEqual(payload["phase"], phase)
            self.assertEqual(payload["route_status"], "NOT_ACTIVE")
            self.assertIsNone(payload["route"])
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.status, TransportRequest.Status.READY_FOR_DISPATCH)

    def test_unaccepted_assignment_cannot_request_active_route(self):
        self.assignment.accepted_at = None
        self.assignment.accepted_by = None
        self.assignment.save(update_fields=["accepted_at", "accepted_by"])
        self.client.force_login(self.driver_user)
        self.assertEqual(self.client.get(self.route_url).status_code, 409)

    def test_vehicle_position_preserves_timestamp_and_existing_freshness_rule(self):
        now = datetime(2026, 8, 18, 4, 0, tzinfo=UTC)
        event = self.create_event(recorded_at=now - timedelta(seconds=301))
        self.client.force_login(self.driver_user)

        with patch("transport_requests.driver_views.timezone.now", return_value=now):
            response = self.client.get(self.position_url)

        self.assertEqual(response.status_code, 200)
        position = response.json()["vehicle_position"]
        self.assertEqual(
            set(position), {"latitude", "longitude", "recorded_at", "is_stale", "source"}
        )
        self.assertEqual(
            datetime.fromisoformat(position["recorded_at"].replace("Z", "+00:00")),
            event.recorded_at,
        )
        self.assertTrue(position["is_stale"])
        self.assertAlmostEqual(position["latitude"], 14.55)
        self.assertAlmostEqual(position["longitude"], 121.021)
        with patch(
            "transport_requests.routing.get_route_between", return_value=self.route_result()
        ):
            route = self.client.get(self.route_url).json()["route"]
        self.assertEqual(route["route_status"], "AVAILABLE")
        self.assertEqual(route["position_state"], "STALE")
        self.assertEqual(route["route_basis"], "LAST_KNOWN_VEHICLE_POSITION")
        self.assertTrue(route["vehicle_position"]["is_stale"])
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

    def test_invalid_vehicle_coordinates_are_not_exposed(self):
        event = self.create_event(recorded_at=timezone.now())
        event.location = Point(181, 91, srid=4326)
        event.save(update_fields=["location"])
        self.client.force_login(self.driver_user)

        response = self.client.get(self.position_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"vehicle_position": None})
