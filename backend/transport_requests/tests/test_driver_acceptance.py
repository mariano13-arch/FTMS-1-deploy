from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Driver, Vehicle, VehicleInspection
from transport_requests import dispatch
from transport_requests.models import (
    DispatchAssignment,
    DispatchAssignmentEvent,
    TransportRequest,
)


class DriverAcceptanceApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.operator = get_user_model().objects.create_user(
            username="acceptance-operator", is_staff=True
        )
        StaffProfile.objects.create(
            user=self.operator, role=StaffProfile.Role.DISPATCHER
        )
        self.driver_user = get_user_model().objects.create_user(
            username="acceptance-driver", password="Strong-test-password-42!"
        )
        self.other_user = get_user_model().objects.create_user(
            username="acceptance-other", password="Strong-test-password-42!"
        )
        today = timezone.localdate()
        driver_fields = {
            "license_number": "N01",
            "license_expiry_date": today + timedelta(days=30),
            "medical_certificate_expiry_date": today + timedelta(days=30),
        }
        self.driver = Driver.objects.create(
            driver_code="DRV-ACCEPT-001",
            first_name="Maria",
            last_name="Reyes",
            linked_user=self.driver_user,
            **driver_fields,
        )
        self.other_driver = Driver.objects.create(
            driver_code="DRV-ACCEPT-002",
            first_name="Jose",
            last_name="Santos",
            linked_user=self.other_user,
            **driver_fields,
        )
        self.vehicle = Vehicle.objects.create(
            device_id="ACCEPT-VEH-001",
            plate_number="ACC-123",
            display_name="Acceptance Van",
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=8,
        )
        self.other_vehicle = Vehicle.objects.create(
            device_id="ACCEPT-VEH-002",
            plate_number="ACC-456",
            display_name="Replacement Van",
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=8,
        )
        VehicleInspection.objects.create(
            vehicle=self.other_vehicle,
            inspection_date=timezone.localdate(),
            inspection_type=VehicleInspection.InspectionType.PRE_TRIP,
            result=VehicleInspection.Result.PASSED,
            exterior_condition=VehicleInspection.Condition.OK,
            interior_condition=VehicleInspection.Condition.OK,
            tires_condition=VehicleInspection.Condition.OK,
            lights_condition=VehicleInspection.Condition.OK,
            brakes_condition=VehicleInspection.Condition.OK,
            fluids_condition=VehicleInspection.Condition.OK,
            safety_equipment_condition=VehicleInspection.Condition.OK,
            inspected_by=self.operator,
        )
        self.trip = TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference="ACCEPTANCE-TRIP",
            request_type=TransportRequest.RequestType.GUEST_TRANSFER,
            request_category=TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            requester_name="Front Desk",
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
            override_reason="Controlled acceptance test",
            confirmed_by=self.operator,
        )
        self.url = f"/api/v1/driver-trips/{self.trip.pk}/accept/"

    def accept(self, confirmed_at=None):
        return self.client.post(
            self.url,
            {"confirmed_at": (confirmed_at or self.assignment.confirmed_at).isoformat()},
            format="json",
        )

    def test_accept_requires_authentication_and_assignment_ownership(self):
        self.assertEqual(self.accept().status_code, 401)

        self.client.force_login(self.other_user)
        self.assertEqual(self.accept().status_code, 404)

    def test_released_assignment_acceptance_persists_and_is_idempotent(self):
        accepted_time = timezone.now()
        self.client.force_login(self.driver_user)

        with patch("transport_requests.acceptance.timezone.now", return_value=accepted_time):
            response = self.accept()

        self.assertEqual(response.status_code, 200)
        trip = response.json()["trip"]
        self.assertTrue(trip["is_accepted"])
        self.assertIsNotNone(trip["accepted_at"])
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.accepted_at, accepted_time)
        self.assertEqual(self.assignment.accepted_by, self.driver_user)
        event = self.assignment.events.get(
            event_type=DispatchAssignmentEvent.EventType.DRIVER_ACCEPTED
        )
        self.assertEqual(event.performed_by, self.driver_user)
        with self.assertRaises(ValueError):
            event.delete()

        repeated = self.accept()
        self.assertEqual(repeated.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.accepted_at, accepted_time)
        self.assertEqual(
            self.assignment.events.filter(
                event_type=DispatchAssignmentEvent.EventType.DRIVER_ACCEPTED
            ).count(),
            1,
        )
        refetched = self.client.get(f"/api/v1/driver-trips/{self.trip.pk}/")
        self.assertTrue(refetched.json()["trip"]["is_accepted"])

        self.client.force_authenticate(self.operator)
        board = self.client.get("/api/v1/transport-requests/dispatch-board/").json()
        self.assertTrue(board["assignments"][0]["is_accepted"])
        self.assertIsNotNone(board["assignments"][0]["accepted_at"])
        self.assertIn(
            "DRIVER_ACCEPTED",
            [event["kind"] for event in board["assignment_audit"][str(self.trip.pk)]],
        )

    def test_unreleased_and_cancelled_assignments_cannot_be_accepted(self):
        self.client.force_login(self.driver_user)
        for invalid_status in (
            TransportRequest.Status.APPROVED,
            TransportRequest.Status.CANCELLED,
        ):
            self.trip.status = invalid_status
            self.trip.save(update_fields=["status", "updated_at"])
            response = self.accept()
            self.assertEqual(response.status_code, 409)
        self.assignment.refresh_from_db()
        self.assertIsNone(self.assignment.accepted_at)
        self.assertFalse(
            self.assignment.events.filter(
                event_type=DispatchAssignmentEvent.EventType.DRIVER_ACCEPTED
            ).exists()
        )

    def test_reassignment_clears_acceptance_and_preserves_history(self):
        self.client.force_login(self.driver_user)
        self.assertEqual(self.accept().status_code, 200)
        accepted_event = self.assignment.events.get(
            event_type=DispatchAssignmentEvent.EventType.DRIVER_ACCEPTED
        )

        self.trip.status = TransportRequest.Status.APPROVED
        self.trip.save(update_fields=["status", "updated_at"])
        dispatch.confirm_assignment(
            transport_request_id=self.trip.pk,
            vehicle_id=self.other_vehicle.pk,
            driver_id=self.other_driver.pk,
            selection_mode=DispatchAssignment.SelectionMode.MANUAL,
            user=self.operator,
            override_reason="Driver availability changed",
        )

        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.driver, self.other_driver)
        self.assertIsNone(self.assignment.accepted_at)
        self.assertIsNone(self.assignment.accepted_by)
        self.assertTrue(DispatchAssignmentEvent.objects.filter(pk=accepted_event.pk).exists())
        changed = self.assignment.events.get(
            event_type=DispatchAssignmentEvent.EventType.ASSIGNMENT_CHANGED
        )
        self.assertEqual(changed.previous_driver, self.driver)
        self.assertEqual(changed.new_driver, self.other_driver)

        self.trip.status = TransportRequest.Status.READY_FOR_DISPATCH
        self.trip.save(update_fields=["status", "updated_at"])
        self.assignment.refresh_from_db()
        self.client.force_login(self.other_user)
        accepted_again = self.accept()
        self.assertEqual(accepted_again.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.accepted_by, self.other_user)
        self.assertEqual(
            self.assignment.events.filter(
                event_type=DispatchAssignmentEvent.EventType.DRIVER_ACCEPTED
            ).count(),
            2,
        )

    def test_stale_same_driver_acceptance_is_rejected_after_vehicle_change(self):
        stale_confirmation = self.assignment.confirmed_at
        self.client.force_login(self.driver_user)
        self.assertEqual(self.accept(stale_confirmation).status_code, 200)

        self.trip.status = TransportRequest.Status.APPROVED
        self.trip.save(update_fields=["status", "updated_at"])
        dispatch.confirm_assignment(
            transport_request_id=self.trip.pk,
            vehicle_id=self.other_vehicle.pk,
            driver_id=self.driver.pk,
            selection_mode=DispatchAssignment.SelectionMode.MANUAL,
            user=self.operator,
            override_reason="Vehicle changed after mobile load",
        )
        self.trip.status = TransportRequest.Status.READY_FOR_DISPATCH
        self.trip.save(update_fields=["status", "updated_at"])
        self.assignment.refresh_from_db()

        stale = self.accept(stale_confirmation)
        self.assertEqual(stale.status_code, 409)
        self.assertIn("changed after it was loaded", stale.json()["detail"])
        self.assignment.refresh_from_db()
        self.assertIsNone(self.assignment.accepted_at)

        self.assertEqual(self.accept().status_code, 200)
