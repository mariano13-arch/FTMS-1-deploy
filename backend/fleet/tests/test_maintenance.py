from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import serializers
from rest_framework.test import APIClient

from accounts.models import RolePermission, StaffProfile
from fleet.maintenance import maintenance_readiness
from fleet.models import Driver, Vehicle, VehicleInspection, VehicleMaintenanceRecord
from transport_requests import dispatch, services
from transport_requests.models import DispatchAssignment, TransportRequest


class VehicleMaintenanceTests(TestCase):
    def setUp(self):
        self.manager = self.user("manager", StaffProfile.Role.FLEET_MANAGER)
        self.superuser = self.user("admin", superuser=True)
        self.dispatcher = self.user("dispatcher", StaffProfile.Role.DISPATCHER)
        self.vehicle = self.make_vehicle("MAINT-001")
        self.other_vehicle = self.make_vehicle("MAINT-002")
        self.inspection = self.inspect(self.vehicle, VehicleInspection.Result.PASSED)
        self.client = APIClient()
        self.client.force_authenticate(self.manager)
        for action in ("VIEW", "CREATE", "SCHEDULE", "START", "COMPLETE", "CANCEL"):
            RolePermission.objects.get_or_create(
                role=StaffProfile.Role.FLEET_MANAGER, module="MAINTENANCE", action=action
            )
        RolePermission.objects.get_or_create(
            role=StaffProfile.Role.DISPATCHER, module="MAINTENANCE", action="VIEW"
        )

    def user(self, username, role=None, superuser=False):
        user = get_user_model().objects.create_user(
            username=username, is_staff=True, is_superuser=superuser
        )
        StaffProfile.objects.create(
            user=user,
            role=role or StaffProfile.Role.FLEET_ADMIN,
        )
        return user

    def make_vehicle(self, device_id):
        return Vehicle.objects.create(
            device_id=device_id,
            plate_number=device_id,
            display_name=device_id,
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=8,
        )

    def inspect(self, vehicle, result):
        return VehicleInspection.objects.create(
            vehicle=vehicle,
            inspection_date=timezone.localdate(),
            inspection_type=VehicleInspection.InspectionType.PRE_TRIP,
            result=result,
            exterior_condition=VehicleInspection.Condition.OK,
            interior_condition=VehicleInspection.Condition.OK,
            tires_condition=VehicleInspection.Condition.OK,
            lights_condition=VehicleInspection.Condition.OK,
            brakes_condition=VehicleInspection.Condition.OK,
            fluids_condition=VehicleInspection.Condition.OK,
            safety_equipment_condition=VehicleInspection.Condition.OK,
            inspected_by=self.manager,
        )

    def create_record(self, **overrides):
        payload = {
            "vehicle_device_id": self.vehicle.device_id,
            "title": "Inspect cooling system",
            "notes": "Confirmed by fleet manager.",
            **overrides,
        }
        return self.client.post("/api/v1/vehicles/maintenance/", payload, format="json")

    def test_manager_and_superadmin_create_server_owned_open_records(self):
        for user in (self.manager, self.superuser):
            with self.subTest(user=user.username):
                self.client.force_authenticate(user)
                response = self.create_record()
                self.assertEqual(response.status_code, 201)
                record = VehicleMaintenanceRecord.objects.get(pk=response.json()["id"])
                self.assertEqual(record.vehicle, self.vehicle)
                self.assertEqual(record.created_by, user)
                self.assertEqual(record.status, VehicleMaintenanceRecord.Status.OPEN)
                self.assertEqual(record.source, VehicleMaintenanceRecord.Source.MANUAL)
                self.assertIsNotNone(record.created_at)
        rejected = self.create_record(status="COMPLETED", created_by=self.dispatcher.pk)
        self.assertEqual(rejected.status_code, 400)

    def test_dispatcher_is_read_only(self):
        record = VehicleMaintenanceRecord.objects.create(
            vehicle=self.vehicle, title="Read only", created_by=self.manager
        )
        self.client.force_authenticate(self.dispatcher)
        self.assertEqual(self.client.get("/api/v1/vehicles/maintenance/").status_code, 200)
        self.assertFalse(self.client.get("/api/v1/vehicles/maintenance/").json()["can_manage"])
        self.assertEqual(self.create_record().status_code, 403)
        self.assertEqual(
            self.client.post(
                f"/api/v1/vehicles/maintenance/{record.pk}/transition/",
                {"status": "IN_PROGRESS"},
                format="json",
            ).status_code,
            403,
        )

    def test_inspection_origin_must_match_vehicle(self):
        linked = self.create_record(inspection_id=self.inspection.pk)
        self.assertEqual(linked.status_code, 201)
        self.assertEqual(linked.json()["source"], "INSPECTION")
        self.assertEqual(linked.json()["inspection"]["id"], self.inspection.pk)
        other_inspection = self.inspect(self.other_vehicle, VehicleInspection.Result.FAILED)
        response = self.create_record(inspection_id=other_inspection.pk)
        self.assertEqual(response.status_code, 400)
        self.assertIn("inspection_id", response.json())
        self.assertEqual(self.inspection.result, VehicleInspection.Result.PASSED)

    def test_valid_transitions_set_server_timestamps_and_terminal_states_stop(self):
        record_id = self.create_record().json()["id"]
        scheduled_at = timezone.now() + timedelta(days=2)
        scheduled = self.client.post(
            f"/api/v1/vehicles/maintenance/{record_id}/transition/",
            {"status": "SCHEDULED", "scheduled_at": scheduled_at.isoformat()},
            format="json",
        )
        self.assertEqual(scheduled.status_code, 200)
        started = self.client.post(
            f"/api/v1/vehicles/maintenance/{record_id}/transition/",
            {"status": "IN_PROGRESS"},
            format="json",
        )
        self.assertEqual(started.status_code, 200)
        self.assertIsNotNone(started.json()["started_at"])
        completed = self.client.post(
            f"/api/v1/vehicles/maintenance/{record_id}/transition/",
            {"status": "COMPLETED"},
            format="json",
        )
        self.assertEqual(completed.status_code, 200)
        self.assertIsNotNone(completed.json()["completed_at"])
        self.assertEqual(
            self.client.post(
                f"/api/v1/vehicles/maintenance/{record_id}/transition/",
                {"status": "IN_PROGRESS"},
                format="json",
            ).status_code,
            400,
        )
        cancelled_id = self.create_record(title="Cancel this action").json()["id"]
        self.assertEqual(
            self.client.post(
                f"/api/v1/vehicles/maintenance/{cancelled_id}/transition/",
                {"status": "CANCELLED"},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/vehicles/maintenance/{cancelled_id}/transition/",
                {"status": "SCHEDULED", "scheduled_at": scheduled_at.isoformat()},
                format="json",
            ).status_code,
            400,
        )

    def dispatch_request(self):
        return TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference="MAINT-DISPATCH",
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
            status=TransportRequest.Status.READY_FOR_DISPATCH,
            created_by=self.manager,
        )

    def test_active_statuses_block_while_terminal_statuses_pass_maintenance_gate(self):
        request = self.dispatch_request()
        for status in (
            VehicleMaintenanceRecord.Status.OPEN,
            VehicleMaintenanceRecord.Status.SCHEDULED,
            VehicleMaintenanceRecord.Status.IN_PROGRESS,
        ):
            record = VehicleMaintenanceRecord.objects.create(
                vehicle=self.vehicle,
                title=status,
                status=status,
                scheduled_at=timezone.now() if status == "SCHEDULED" else None,
                started_at=timezone.now() if status == "IN_PROGRESS" else None,
                created_by=self.manager,
            )
            with self.subTest(status=status):
                self.assertFalse(maintenance_readiness(self.vehicle).eligible)
                with self.assertRaisesMessage(serializers.ValidationError, "Active maintenance"):
                    services.validate_vehicle(request, self.vehicle)
            record.delete()
        for status in (
            VehicleMaintenanceRecord.Status.COMPLETED,
            VehicleMaintenanceRecord.Status.CANCELLED,
        ):
            VehicleMaintenanceRecord.objects.create(
                vehicle=self.vehicle,
                title=status,
                status=status,
                started_at=timezone.now() if status == "COMPLETED" else None,
                completed_at=timezone.now() if status == "COMPLETED" else None,
                created_by=self.manager,
            )
        self.assertTrue(maintenance_readiness(self.vehicle).eligible)
        services.validate_vehicle(request, self.vehicle)

    def test_completion_does_not_bypass_latest_failed_inspection(self):
        self.inspect(self.vehicle, VehicleInspection.Result.FAILED)
        VehicleMaintenanceRecord.objects.create(
            vehicle=self.vehicle,
            title="Completed repair",
            status=VehicleMaintenanceRecord.Status.COMPLETED,
            started_at=timezone.now(),
            completed_at=timezone.now(),
            created_by=self.manager,
        )
        with self.assertRaisesMessage(serializers.ValidationError, "Inspection failed"):
            services.validate_vehicle(self.dispatch_request(), self.vehicle)

    @patch("transport_requests.views.matrix.eligible_vehicle_origins")
    def test_stale_candidate_cannot_bypass_new_open_record(self, origins_mock):
        origins_mock.return_value = [{"vehicle_id": self.vehicle.device_id}]
        request = self.dispatch_request()
        board = self.client.get("/api/v1/transport-requests/dispatch-board/")
        self.assertEqual(
            board.json()["manual_candidates"][str(request.pk)]["vehicles"][0]["id"],
            self.vehicle.pk,
        )
        self.create_record(title="Newly opened maintenance")
        driver = Driver.objects.create(
            driver_code="MAINT-DRV",
            first_name="Fleet",
            last_name="Driver",
            license_number="N01",
            license_expiry_date=timezone.localdate() + timedelta(days=30),
            medical_certificate_expiry_date=timezone.localdate() + timedelta(days=30),
        )
        response = self.client.post(
            "/api/v1/transport-requests/dispatch-board/confirm/",
            {
                "transport_request_id": str(request.pk),
                "vehicle_id": self.vehicle.pk,
                "driver_id": driver.pk,
                "selection_mode": "MANUAL",
                "override_reason": "Stale browser selection",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Active maintenance", response.json()["vehicle"])
        self.assertFalse(DispatchAssignment.objects.exists())

    @patch("transport_requests.dispatch.matrix.build_dispatch_matrix")
    @patch("transport_requests.dispatch.matrix.eligible_vehicle_origins")
    def test_active_maintenance_is_excluded_before_optimizer(self, origins_mock, matrix_mock):
        request = self.dispatch_request()
        self.create_record()
        Driver.objects.create(
            driver_code="OPT-MAINT-DRV",
            first_name="Optimizer",
            last_name="Driver",
            license_number="N02",
            license_expiry_date=timezone.localdate() + timedelta(days=30),
            medical_certificate_expiry_date=timezone.localdate() + timedelta(days=30),
        )
        origins_mock.return_value = []
        dispatch.recommendations([request.pk])
        origins_mock.assert_called_once_with([])
        matrix_mock.assert_not_called()
