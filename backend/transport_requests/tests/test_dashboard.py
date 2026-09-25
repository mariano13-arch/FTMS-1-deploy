from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Vehicle
from telemetry.models import TelemetryDevice, VehicleEmergencySOS
from transport_requests.models import TransportRequest


class DashboardSummaryTests(TestCase):
    endpoint = "/api/v1/dashboard/summary/"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="dashboard-manager", password="test-password", is_staff=True
        )
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.FLEET_ADMIN)
        self.client = APIClient()

    @staticmethod
    def dispatch_response(**overrides):
        summary = {
            "approved_requests": 0,
            "awaiting_assignment": 0,
            "confirmed_assignments": 0,
            "ready_for_dispatch": 0,
            "optimizer_eligible": 0,
            "needs_attention": 0,
            "no_eligible_driver": 0,
            "no_gis_vehicle": 0,
            "schedule_conflict": 0,
            "number_coding_blocked": 0,
            **overrides,
        }
        return summary

    def get(self):
        with patch(
            "transport_requests.dashboard.dispatch_board_summary",
            return_value=self.dispatch_response(),
        ):
            return self.client.get(self.endpoint)

    def test_requires_authenticated_staff(self):
        self.assertIn(self.client.get(self.endpoint).status_code, (401, 403))
        ordinary = get_user_model().objects.create_user(
            username="ordinary-dashboard-user", password="test-password"
        )
        self.client.force_authenticate(ordinary)
        self.assertEqual(self.client.get(self.endpoint).status_code, 403)

    def test_empty_state_is_factual_and_omits_unsupported_metrics(self):
        self.client.force_authenticate(self.user)
        response = self.get()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["request_status"]["total"], 0)
        self.assertEqual(data["sos_activity"]["total"], 0)
        self.assertEqual(data["fuel_evidence"]["values"][-1]["count"], 0)
        forbidden = {
            "fleet_utilization",
            "global_eligible_drivers",
            "global_available_vehicles",
            "maintenance_prediction_risk",
            "actual_fuel_used",
            "actual_fuel_cost",
            "fuel_savings",
        }
        self.assertTrue(forbidden.isdisjoint(data))

    def test_request_statuses_are_exact_current_state_counts(self):
        self.client.force_authenticate(self.user)
        common = {
            "source_system": TransportRequest.SourceSystem.MANUAL_STAFF_ENTRY,
            "request_type": TransportRequest.RequestType.GUEST_TRANSFER,
            "request_category": TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            "requester_name": "Dashboard fixture",
            "pickup_name": "Hotel",
            "pickup_address": "Hotel address",
            "pickup_latitude": "14.500000",
            "pickup_longitude": "121.000000",
            "destination_name": "Airport",
            "destination_address": "Airport address",
            "destination_latitude": "14.600000",
            "destination_longitude": "121.100000",
            "scheduled_pickup_at": timezone.now(),
            "passenger_count": 1,
            "created_by": self.user,
        }
        TransportRequest.objects.create(**common, status=TransportRequest.Status.FOR_APPROVAL)
        TransportRequest.objects.create(**common, status=TransportRequest.Status.READY_FOR_DISPATCH)
        values = {
            row["value"]: row["count"] for row in self.get().json()["request_status"]["values"]
        }
        self.assertEqual(values[TransportRequest.Status.FOR_APPROVAL], 1)
        self.assertEqual(values[TransportRequest.Status.READY_FOR_DISPATCH], 1)
        self.assertNotIn("COMPLETED", values)

    def test_dispatch_summary_reuses_authoritative_board_logic(self):
        self.client.force_authenticate(self.user)
        with patch(
            "transport_requests.dashboard.dispatch_board_summary",
            return_value=self.dispatch_response(
                awaiting_assignment=4,
                optimizer_eligible=2,
                needs_attention=2,
                no_eligible_driver=1,
            ),
        ) as board:
            data = self.client.get(self.endpoint).json()
        board.assert_called_once()
        values = {row["value"]: row["count"] for row in data["dispatch_queue"]["values"]}
        self.assertEqual(values["optimizer_eligible"], 2)
        self.assertEqual(values["no_eligible_driver"], 1)
        self.assertNotIn("confirmed_assignments", values)

    def test_sos_is_factual_and_never_invents_location(self):
        self.client.force_authenticate(self.user)
        vehicle = Vehicle.objects.create(
            device_id="DASH-VEH-1", plate_number="DASH-1", display_name="Dashboard Van"
        )
        device = TelemetryDevice.objects.create(device_id="DASH-DEVICE-1")
        VehicleEmergencySOS.objects.create(
            device=device,
            vehicle=vehicle,
            status=VehicleEmergencySOS.Status.ACTIVE,
            source=VehicleEmergencySOS.Source.PHYSICAL_BUTTON,
            activated_at=timezone.now(),
        )
        sos = self.get().json()["sos_activity"]
        self.assertEqual(sos["total"], 1)
        self.assertIsNone(sos["recent"][0]["location"])
