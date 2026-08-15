from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Driver, Vehicle
from transport_requests import dispatch
from transport_requests.models import (
    DispatchAssignment,
    DispatchAssignmentEvent,
    TransportRequest,
)


class DispatchBoardTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="operator", is_staff=True)
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.DISPATCHER)
        self.client.force_authenticate(self.user)
        today = timezone.localdate()
        self.driver = Driver.objects.create(
            driver_code="DRV-001",
            first_name="Juan",
            last_name="Dela Cruz",
            license_number="N01",
            license_expiry_date=today + timedelta(days=30),
            medical_certificate_expiry_date=today + timedelta(days=30),
        )
        self.vehicle = Vehicle.objects.create(
            device_id="VEH-001",
            plate_number="ABC-123",
            display_name="Guest Van",
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=8,
        )
        self.request = self.make_request("REQ-001")

    def make_request(self, reference, *, hours=2):
        return TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference=reference,
            request_type=TransportRequest.RequestType.GUEST_TRANSFER,
            request_category=TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            requester_name="Front Desk",
            pickup_name="Hotel",
            pickup_address="Makati",
            pickup_latitude="14.565200",
            pickup_longitude="121.028600",
            destination_name="Airport",
            destination_address="Pasay",
            destination_latitude="14.508600",
            destination_longitude="121.019800",
            scheduled_pickup_at=timezone.now() + timedelta(hours=hours),
            estimated_duration_minutes=60,
            required_vehicle_type=Vehicle.VehicleType.VAN,
            passenger_count=4,
            status=TransportRequest.Status.APPROVED,
            created_by=self.user,
        )

    def confirmation(self, **overrides):
        body = {
            "transport_request_id": str(self.request.pk),
            "vehicle_id": self.vehicle.pk,
            "driver_id": self.driver.pk,
            "selection_mode": "MANUAL",
            "override_reason": "Operational selection",
            **overrides,
        }
        return self.client.post(
            "/api/v1/transport-requests/dispatch-board/confirm/", body, format="json"
        )

    def test_board_requires_auth_and_exposes_real_candidates(self):
        response = self.client.get("/api/v1/transport-requests/dispatch-board/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["requests"][0]["id"], str(self.request.pk))
        self.assertEqual(response.json()["eligible_drivers"][0]["eligibility_status"], "ELIGIBLE")
        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.get("/api/v1/transport-requests/dispatch-board/").status_code, 401
        )

    def test_manual_confirmation_syncs_vehicle_and_keeps_immutable_history(self):
        response = self.confirmation()
        self.assertEqual(response.status_code, 201)
        assignment = DispatchAssignment.objects.get(transport_request=self.request)
        self.request.refresh_from_db()
        self.assertEqual(assignment.driver, self.driver)
        self.assertEqual(assignment.vehicle, self.vehicle)
        self.assertEqual(assignment.confirmed_by, self.user)
        self.assertEqual(self.request.assigned_vehicle, self.vehicle)
        event = DispatchAssignmentEvent.objects.get(assignment=assignment)
        with self.assertRaises(ValueError):
            event.delete()
        old_endpoint = self.client.post(
            f"/api/v1/transport-requests/{self.request.pk}/assign-vehicle/",
            {"vehicle_device_id": self.vehicle.device_id},
            format="json",
        )
        self.assertEqual(old_endpoint.status_code, 400)

    def test_restricted_driver_and_change_without_reason_are_rejected(self):
        restricted = Driver.objects.create(
            driver_code="DRV-RESTRICTED", first_name="No", last_name="Evidence"
        )
        self.assertEqual(self.confirmation(driver_id=restricted.pk).status_code, 400)
        self.assertEqual(self.confirmation().status_code, 201)
        other = Vehicle.objects.create(
            device_id="VEH-002",
            plate_number="DEF-456",
            display_name="Other Van",
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=8,
        )
        self.assertEqual(
            self.confirmation(vehicle_id=other.pk, override_reason="").status_code, 400
        )

    def test_signed_recommendation_and_explicit_prepare_dispatch(self):
        token = dispatch.recommendation_token(
            self.request.pk, self.vehicle.pk, self.driver.pk
        )
        optimized = self.confirmation(
            selection_mode="OPTIMIZED", override_reason="", recommendation_token=token
        )
        self.assertEqual(optimized.status_code, 201)
        self.assertEqual(
            self.client.post(
                f"/api/v1/transport-requests/{self.request.pk}/prepare-dispatch/",
                {},
                format="json",
            ).json()["status"],
            "READY_FOR_DISPATCH",
        )
        self.assertEqual(
            self.confirmation(override_reason="Change after ready").status_code, 400
        )

    @patch("transport_requests.dispatch.matrix.eligible_vehicle_origins")
    @patch("transport_requests.dispatch.matrix.build_dispatch_matrix")
    def test_optimizer_executes_and_uses_tomtom_duration_deterministically(
        self, matrix_mock, origins_mock
    ):
        second_vehicle = Vehicle.objects.create(
            device_id="VEH-002",
            plate_number="DEF-456",
            display_name="Slower Van",
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=8,
        )
        matrix_mock.return_value = {
            "vehicle_ids": [self.vehicle.device_id, second_vehicle.device_id],
            "request_ids": [str(self.request.pk)],
            "durations_seconds": [[100], [500]],
            "distances_meters": [[1000], [2000]],
            "traffic_delays_seconds": [[10], [20]],
            "cell_statuses": [["OK"], ["OK"]],
        }
        origins_mock.return_value = [
            {"vehicle_id": self.vehicle.device_id, "latitude": 14.5, "longitude": 121.0},
            {"vehicle_id": second_vehicle.device_id, "latitude": 14.6, "longitude": 121.1},
        ]
        result = dispatch.recommendations()
        self.assertEqual(len(result["recommendations"]), 1)
        selected = result["recommendations"][0]
        self.assertEqual(selected["vehicle"], self.vehicle)
        self.assertEqual(selected["travel_time_seconds"], 100)
        self.assertIn("Driver eligibility is ELIGIBLE", selected["explanation"])
        self.assertEqual(selected["schedule_context"]["driver"]["status"], "AVAILABLE")
        self.assertEqual(selected["gis_preview"]["vehicle_location"]["vehicle_id"], "VEH-001")
        self.assertIsNone(selected["gis_preview"]["geometry"])
        comparison = result["candidate_comparison"][str(self.request.pk)]
        self.assertEqual(comparison[0]["result"], "RECOMMENDED")
        self.assertNotIn("safety_score", selected)

    def test_board_exposes_real_attention_and_persisted_audit_only(self):
        self.assertEqual(self.confirmation().status_code, 201)
        self.client.post(
            f"/api/v1/transport-requests/{self.request.pk}/prepare-dispatch/",
            {},
            format="json",
        )
        response = self.client.get("/api/v1/transport-requests/dispatch-board/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["ready_for_dispatch"], 1)
        events = payload["assignment_audit"][str(self.request.pk)]
        self.assertEqual(
            [event["kind"] for event in events],
            ["ASSIGNMENT_CONFIRMED", "PREPARED_FOR_DISPATCH"],
        )
        self.assertNotIn("RECOMMENDATION_GENERATED", [event["kind"] for event in events])

    def test_prepare_requires_canonical_assignment(self):
        self.request.assigned_vehicle = self.vehicle
        self.request.save(update_fields=["assigned_vehicle", "updated_at"])
        response = self.client.post(
            f"/api/v1/transport-requests/{self.request.pk}/prepare-dispatch/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("dispatch_assignment", response.json())
