from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import serializers
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.inspection_readiness import inspection_readiness
from fleet.models import Driver, Vehicle, VehicleInspection
from transport_requests import dispatch, services
from transport_requests.models import DispatchAssignment, TransportRequest


class InspectionDispatchReadinessTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="readiness", is_staff=True)
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.DISPATCHER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        today = timezone.localdate()
        self.driver = Driver.objects.create(
            driver_code="DRV-READY",
            first_name="Ready",
            last_name="Driver",
            license_number="READY-1",
            license_expiry_date=today + timedelta(days=30),
            medical_certificate_expiry_date=today + timedelta(days=30),
        )
        self.vehicle = self.make_vehicle("READY-001")
        self.other_vehicle = self.make_vehicle("READY-002")
        self.request = TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference="READINESS-001",
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
            scheduled_pickup_at=timezone.now() + timedelta(hours=2),
            estimated_duration_minutes=60,
            required_vehicle_type=Vehicle.VehicleType.VAN,
            passenger_count=4,
            status=TransportRequest.Status.APPROVED,
            created_by=self.user,
        )

    def make_vehicle(self, device_id, *, active=True):
        return Vehicle.objects.create(
            device_id=device_id,
            plate_number=device_id,
            display_name=device_id,
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=8,
            is_active=active,
        )

    def inspect(self, vehicle, result, *, days=0, inspection_type="PRE_TRIP"):
        return VehicleInspection.objects.create(
            vehicle=vehicle,
            inspection_date=timezone.localdate() + timedelta(days=days),
            inspection_type=inspection_type,
            result=result,
            exterior_condition=VehicleInspection.Condition.OK,
            interior_condition=VehicleInspection.Condition.OK,
            tires_condition=VehicleInspection.Condition.OK,
            lights_condition=VehicleInspection.Condition.OK,
            brakes_condition=VehicleInspection.Condition.OK,
            fluids_condition=VehicleInspection.Condition.OK,
            safety_equipment_condition=VehicleInspection.Condition.OK,
            inspected_by=self.user,
        )

    def confirmation(self, *, vehicle=None, override_reason="Operational selection"):
        selected = vehicle or self.vehicle
        return self.client.post(
            "/api/v1/transport-requests/dispatch-board/confirm/",
            {
                "transport_request_id": str(self.request.pk),
                "vehicle_id": selected.pk,
                "driver_id": self.driver.pk,
                "selection_mode": "MANUAL",
                "override_reason": override_reason,
            },
            format="json",
        )

    def test_result_rules_and_no_inspection(self):
        self.assertEqual(inspection_readiness(self.vehicle).reason, "Inspection required.")
        for result, eligible, reason in (
            (VehicleInspection.Result.PASSED, True, ""),
            (
                VehicleInspection.Result.NEEDS_ATTENTION,
                False,
                "Inspection needs attention.",
            ),
            (VehicleInspection.Result.FAILED, False, "Inspection failed."),
        ):
            with self.subTest(result=result):
                vehicle = self.make_vehicle(f"RESULT-{result}")
                self.inspect(vehicle, result)
                readiness = inspection_readiness(vehicle)
                self.assertEqual(readiness.eligible, eligible)
                self.assertEqual(readiness.reason, reason)

    def test_newest_overall_inspection_wins_regardless_of_type(self):
        older = self.inspect(
            self.vehicle,
            VehicleInspection.Result.FAILED,
            days=-1,
            inspection_type=VehicleInspection.InspectionType.PERIODIC,
        )
        newest = self.inspect(
            self.vehicle,
            VehicleInspection.Result.PASSED,
            inspection_type=VehicleInspection.InspectionType.POST_TRIP,
        )
        self.assertTrue(inspection_readiness(self.vehicle).eligible)
        self.assertEqual(list(self.vehicle.inspections.all()), [newest, older])
        latest = self.inspect(
            self.vehicle,
            VehicleInspection.Result.NEEDS_ATTENTION,
            inspection_type=VehicleInspection.InspectionType.PRE_TRIP,
        )
        self.assertFalse(inspection_readiness(self.vehicle).eligible)
        self.assertEqual(self.vehicle.inspections.first(), latest)

    def test_vehicle_inspections_are_isolated(self):
        self.inspect(self.vehicle, VehicleInspection.Result.PASSED)
        self.inspect(self.other_vehicle, VehicleInspection.Result.FAILED)
        self.assertTrue(inspection_readiness(self.vehicle).eligible)
        self.assertFalse(inspection_readiness(self.other_vehicle).eligible)

    def test_inactive_and_schedule_conflict_rules_remain(self):
        inactive = self.make_vehicle("INACTIVE-PASSED", active=False)
        self.inspect(inactive, VehicleInspection.Result.PASSED)
        with self.assertRaisesMessage(serializers.ValidationError, "Vehicle must be active"):
            services.validate_vehicle(self.request, inactive)

        self.inspect(self.vehicle, VehicleInspection.Result.PASSED)
        conflict = TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference="READINESS-CONFLICT",
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
            scheduled_pickup_at=self.request.scheduled_pickup_at,
            estimated_duration_minutes=60,
            passenger_count=1,
            status=TransportRequest.Status.APPROVED,
            assigned_vehicle=self.vehicle,
            created_by=self.user,
        )
        with self.assertRaises(services.AllocationConflict):
            services.validate_vehicle(self.request, self.vehicle)
        self.assertEqual(conflict.assigned_vehicle, self.vehicle)

    @patch("transport_requests.views.matrix.eligible_vehicle_origins")
    def test_dispatch_board_excludes_blocked_candidates(self, origins_mock):
        self.inspect(self.vehicle, VehicleInspection.Result.PASSED)
        self.inspect(self.other_vehicle, VehicleInspection.Result.FAILED)
        origins_mock.return_value = [
            {"vehicle_id": self.vehicle.device_id, "latitude": 14.5, "longitude": 121.0}
        ]
        response = self.client.get("/api/v1/transport-requests/dispatch-board/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [item["id"] for item in payload["manual_candidates"][str(self.request.pk)]["vehicles"]],
            [self.vehicle.pk],
        )
        self.assertEqual([item["id"] for item in payload["active_vehicles"]], [self.vehicle.pk])

    @patch("transport_requests.dispatch.matrix.build_dispatch_matrix")
    @patch("transport_requests.dispatch.matrix.eligible_vehicle_origins")
    def test_blocked_vehicle_is_removed_before_optimizer_input(
        self, origins_mock, matrix_mock
    ):
        self.inspect(self.vehicle, VehicleInspection.Result.FAILED)
        self.inspect(self.other_vehicle, VehicleInspection.Result.NEEDS_ATTENTION)
        origins_mock.return_value = []
        result = dispatch.recommendations([self.request.pk])
        origins_mock.assert_called_once_with([])
        matrix_mock.assert_not_called()
        self.assertEqual(result["recommendations"], [])

    def test_manual_stale_override_and_direct_assignment_are_blocked(self):
        self.inspect(self.vehicle, VehicleInspection.Result.PASSED)
        with patch(
            "transport_requests.views.matrix.eligible_vehicle_origins",
            return_value=[{"vehicle_id": self.vehicle.device_id}],
        ):
            board = self.client.get("/api/v1/transport-requests/dispatch-board/")
        self.assertEqual(
            board.json()["manual_candidates"][str(self.request.pk)]["vehicles"][0]["id"],
            self.vehicle.pk,
        )
        self.inspect(self.vehicle, VehicleInspection.Result.FAILED)
        rejected = self.confirmation(override_reason="Manager accepts the risk")
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("Inspection failed", rejected.json()["vehicle"])
        direct = self.client.post(
            f"/api/v1/transport-requests/{self.request.pk}/assign-vehicle/",
            {"vehicle_device_id": self.vehicle.device_id, "note": "Direct selection"},
            format="json",
        )
        self.assertEqual(direct.status_code, 400)
        self.assertIn("Inspection failed", direct.json()["vehicle"])
        self.assertFalse(DispatchAssignment.objects.exists())
        self.assertIsNone(TransportRequest.objects.get(pk=self.request.pk).assigned_vehicle_id)

    def test_confirmed_assignment_and_inspection_history_are_preserved(self):
        passed = self.inspect(self.vehicle, VehicleInspection.Result.PASSED)
        self.assertEqual(self.confirmation().status_code, 201)
        failed = self.inspect(self.vehicle, VehicleInspection.Result.FAILED)
        self.assertEqual(
            self.client.post(
                f"/api/v1/transport-requests/{self.request.pk}/prepare-dispatch/",
                {},
                format="json",
            ).status_code,
            200,
        )
        assignment = DispatchAssignment.objects.get(transport_request=self.request)
        self.assertEqual(assignment.vehicle, self.vehicle)
        self.assertEqual(list(self.vehicle.inspections.all()), [failed, passed])
