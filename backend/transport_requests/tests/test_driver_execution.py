from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from fleet.models import Driver, Vehicle
from transport_requests.models import (
    DispatchAssignment,
    DispatchExecutionEvent,
    TransportRequest,
)


class DriverExecutionApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.operator = get_user_model().objects.create_user(
            username="execution-operator", is_staff=True
        )
        self.driver_user = get_user_model().objects.create_user(
            username="execution-driver", password="Strong-test-password-42!"
        )
        self.driver = Driver.objects.create(
            driver_code="DRV-EXEC-001",
            first_name="Maria",
            last_name="Reyes",
            linked_user=self.driver_user,
        )
        self.other_user = get_user_model().objects.create_user(
            username="execution-other", password="Strong-test-password-42!"
        )
        self.other_driver = Driver.objects.create(
            driver_code="DRV-EXEC-002",
            first_name="Jose",
            last_name="Santos",
            linked_user=self.other_user,
        )
        self.unlinked_user = get_user_model().objects.create_user(
            username="execution-unlinked", password="Strong-test-password-42!"
        )
        self.vehicle = Vehicle.objects.create(
            device_id="DRV-EXEC-VEH-001",
            plate_number="EXEC-123",
            display_name="Execution Van",
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=8,
        )
        self.trip = TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference="EXECUTION-TRIP",
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
            status=TransportRequest.Status.APPROVED,
            assigned_vehicle=self.vehicle,
            created_by=self.operator,
        )
        self.assignment = DispatchAssignment.objects.create(
            transport_request=self.trip,
            vehicle=self.vehicle,
            driver=self.driver,
            selection_mode=DispatchAssignment.SelectionMode.MANUAL,
            override_reason="Controlled execution test",
            confirmed_by=self.operator,
        )
        self.url = f"/api/v1/driver-trips/{self.trip.pk}/transition/"

    def post_action(self, action):
        return self.client.post(self.url, {"action": action}, format="json")

    def test_initial_state_is_safe_for_new_and_preexisting_assignments(self):
        self.assertEqual(
            DispatchAssignment._meta.get_field("execution_status").get_default(),
            DispatchAssignment.ExecutionStatus.ASSIGNED,
        )
        self.assertEqual(
            self.assignment.execution_status, DispatchAssignment.ExecutionStatus.ASSIGNED
        )
        self.assertIsNone(self.assignment.execution_started_at)

    def test_access_is_driver_scoped_and_requires_linked_driver(self):
        self.assertEqual(self.post_action("START_TOWARD_PICKUP").status_code, 401)

        self.client.force_login(self.other_user)
        self.assertEqual(self.post_action("START_TOWARD_PICKUP").status_code, 404)

        self.client.force_login(self.unlinked_user)
        self.assertEqual(self.post_action("START_TOWARD_PICKUP").status_code, 403)

    def test_malformed_or_arbitrary_status_payload_is_rejected(self):
        self.client.force_login(self.driver_user)
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 400)
        self.assertEqual(self.post_action("SKIP_TO_COMPLETED").status_code, 400)
        self.assertEqual(
            self.client.post(
                self.url,
                {"action": "START_TOWARD_PICKUP", "status": "COMPLETED"},
                format="json",
            ).status_code,
            400,
        )

    def test_every_forward_transition_records_server_timestamp_and_audit(self):
        self.client.force_login(self.driver_user)
        base = timezone.now()
        transitions = [
            (
                "START_TOWARD_PICKUP",
                "EN_ROUTE_TO_PICKUP",
                "execution_started_at",
            ),
            ("ARRIVE_AT_PICKUP", "AT_PICKUP", "pickup_arrived_at"),
            ("DEPART_PICKUP", "IN_TRANSIT", "pickup_departed_at"),
            (
                "ARRIVE_AT_DESTINATION",
                "AT_DESTINATION",
                "destination_arrived_at",
            ),
            ("COMPLETE", "COMPLETED", "completed_at"),
        ]

        previous_status = "ASSIGNED"
        for index, (action, expected_status, timestamp_field) in enumerate(transitions):
            expected_time = base + timedelta(minutes=index + 1)
            with patch("transport_requests.execution.timezone.now", return_value=expected_time):
                response = self.post_action(action)
            self.assertEqual(response.status_code, 200)
            execution = response.json()["execution"]
            self.assertEqual(execution["status"], expected_status)
            self.assertEqual(
                execution["allowed_actions"],
                [transitions[index + 1][0]] if index + 1 < len(transitions) else [],
            )
            self.assignment.refresh_from_db()
            self.assertEqual(getattr(self.assignment, timestamp_field), expected_time)
            event = self.assignment.execution_events.order_by("pk").last()
            self.assertEqual(event.previous_status, previous_status)
            self.assertEqual(event.new_status, expected_status)
            self.assertEqual(event.action, action)
            self.assertEqual(event.performed_by, self.driver_user)
            self.assertEqual(event.actor_type, DispatchExecutionEvent.ActorType.DRIVER)
            previous_status = expected_status

        self.assertEqual(self.assignment.execution_events.count(), len(transitions))

    def test_skip_backward_terminal_and_duplicate_actions_are_safe(self):
        self.client.force_login(self.driver_user)
        self.assertEqual(self.post_action("ARRIVE_AT_PICKUP").status_code, 409)

        self.assertEqual(self.post_action("START_TOWARD_PICKUP").status_code, 200)
        event_count = self.assignment.execution_events.count()
        duplicate = self.post_action("START_TOWARD_PICKUP")
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(self.assignment.execution_events.count(), event_count)

        self.assertEqual(self.post_action("ARRIVE_AT_PICKUP").status_code, 200)
        self.assertEqual(self.post_action("START_TOWARD_PICKUP").status_code, 409)
        for action in ("DEPART_PICKUP", "ARRIVE_AT_DESTINATION", "COMPLETE"):
            self.assertEqual(self.post_action(action).status_code, 200)

        event_count = self.assignment.execution_events.count()
        self.assertEqual(self.post_action("COMPLETE").status_code, 200)
        self.assertEqual(self.assignment.execution_events.count(), event_count)
        self.assertEqual(self.post_action("ARRIVE_AT_DESTINATION").status_code, 409)

    def test_cancelled_transport_request_blocks_transition(self):
        self.trip.status = TransportRequest.Status.CANCELLED
        self.trip.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.driver_user)

        response = self.post_action("START_TOWARD_PICKUP")

        self.assertEqual(response.status_code, 409)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.execution_status, "ASSIGNED")
        self.assertEqual(self.assignment.execution_events.count(), 0)

    def test_execution_events_are_immutable(self):
        self.client.force_login(self.driver_user)
        self.assertEqual(self.post_action("START_TOWARD_PICKUP").status_code, 200)
        event = self.assignment.execution_events.get()

        event.new_status = DispatchAssignment.ExecutionStatus.COMPLETED
        with self.assertRaises(ValueError):
            event.save()
        with self.assertRaises(ValueError):
            event.delete()
