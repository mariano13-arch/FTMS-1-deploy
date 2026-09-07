from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Driver, Vehicle, VehicleInspection
from transport_requests import dispatch, services
from transport_requests.acceptance import accept_driver_assignment
from transport_requests.execution import transition_driver_execution
from transport_requests.models import (
    DispatchAssignment,
    DispatchExecutionEvent,
    IntegrationClient,
    TransportRequest,
    TransportRequestEvent,
)
from transport_requests.source_integration import (
    create_integration_client,
    credential_matches,
    rotate_integration_credential,
)


class SourceIntegrationApiTests(TestCase):
    ingestion_url = "/api/v1/integrations/transport-requests/"

    def setUp(self):
        self.hotel, self.hotel_credential = create_integration_client(
            name="Oxford Hotel",
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
        )
        self.restaurant, self.restaurant_credential = create_integration_client(
            name="Oxford Restaurant",
            source_system=TransportRequest.SourceSystem.RESTAURANT_MANAGEMENT_SYSTEM,
        )

    @staticmethod
    def client_for(credential):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {credential}")
        return client

    def payload(self, reference="SOURCE-001", **changes):
        data = {
            "external_reference": reference,
            "request_type": "AIRPORT_PICKUP",
            "requester_name": "Front Desk",
            "pickup_name": "Oxford Suites",
            "pickup_address": "Makati City",
            "pickup_latitude": "14.565200",
            "pickup_longitude": "121.028600",
            "destination_name": "NAIA Terminal 3",
            "destination_address": "Pasay City",
            "destination_latitude": "14.508600",
            "destination_longitude": "121.019800",
            "scheduled_pickup_at": (timezone.now() + timedelta(hours=2)).isoformat(),
            "passenger_count": 2,
        }
        data.update(changes)
        return data

    def poll(self, credential, reference):
        return self.client_for(credential).get(
            f"/api/v1/integrations/transport-requests/{reference}/"
        )

    def test_hotel_and_restaurant_credentials_authenticate_and_bind_source(self):
        hotel_response = self.client_for(self.hotel_credential).post(
            self.ingestion_url,
            self.payload("HMS-001"),
            format="json",
        )
        restaurant_response = self.client_for(self.restaurant_credential).post(
            self.ingestion_url,
            self.payload(
                "RMS-001",
                request_type="FOOD_DELIVERY",
                passenger_count=0,
                load_description="Meal trays",
                load_quantity=12,
            ),
            format="json",
        )

        self.assertEqual(hotel_response.status_code, 201)
        self.assertEqual(restaurant_response.status_code, 201)
        self.assertEqual(hotel_response.json()["source_system"], "HOTEL_MANAGEMENT_SYSTEM")
        self.assertEqual(
            restaurant_response.json()["source_system"],
            "RESTAURANT_MANAGEMENT_SYSTEM",
        )
        self.assertEqual(
            TransportRequest.objects.get(external_reference="HMS-001").created_by,
            self.hotel.user,
        )
        self.assertEqual(
            TransportRequest.objects.get(external_reference="RMS-001").created_by,
            self.restaurant.user,
        )

    def test_invalid_inactive_and_staff_session_credentials_are_rejected(self):
        invalid = self.client_for("unknown.invalid").post(
            self.ingestion_url, self.payload(), format="json"
        )
        self.assertEqual(invalid.status_code, 401)

        self.hotel.is_active = False
        self.hotel.save(update_fields=["is_active", "updated_at"])
        inactive = self.client_for(self.hotel_credential).post(
            self.ingestion_url, self.payload(), format="json"
        )
        self.assertEqual(inactive.status_code, 401)

        staff = get_user_model().objects.create_user(username="source-staff", is_staff=True)
        StaffProfile.objects.create(user=staff, role=StaffProfile.Role.FLEET_MANAGER)
        staff_client = APIClient()
        staff_client.force_authenticate(staff)
        self.assertEqual(
            staff_client.post(self.ingestion_url, self.payload(), format="json").status_code,
            403,
        )

    def test_source_cannot_be_caller_overridden_and_reference_is_required(self):
        conflicting = self.client_for(self.hotel_credential).post(
            self.ingestion_url,
            self.payload(source_system="RESTAURANT_MANAGEMENT_SYSTEM"),
            format="json",
        )
        missing = self.client_for(self.hotel_credential).post(
            self.ingestion_url,
            {key: value for key, value in self.payload().items() if key != "external_reference"},
            format="json",
        )
        blank = self.client_for(self.hotel_credential).post(
            self.ingestion_url,
            self.payload(reference="   "),
            format="json",
        )

        self.assertEqual(conflicting.status_code, 400)
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(blank.status_code, 400)
        self.assertEqual(TransportRequest.objects.count(), 0)

    def test_equivalent_replay_is_idempotent_and_conflict_returns_409(self):
        client = self.client_for(self.hotel_credential)
        payload = self.payload("HMS-REPLAY")

        created = client.post(self.ingestion_url, payload, format="json")
        replayed = client.post(self.ingestion_url, payload, format="json")
        conflicting = client.post(
            self.ingestion_url,
            {**payload, "passenger_count": 3},
            format="json",
        )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(replayed.status_code, 200)
        self.assertEqual(created.json(), replayed.json())
        self.assertEqual(conflicting.status_code, 409)
        self.assertEqual(
            TransportRequest.objects.filter(
                source_system="HOTEL_MANAGEMENT_SYSTEM",
                external_reference="HMS-REPLAY",
            ).count(),
            1,
        )

    def test_polling_is_source_scoped_even_for_shared_external_reference(self):
        reference = "SHARED-001"
        self.client_for(self.hotel_credential).post(
            self.ingestion_url, self.payload(reference), format="json"
        )
        self.client_for(self.hotel_credential).post(
            self.ingestion_url, self.payload("HMS-ONLY"), format="json"
        )
        self.client_for(self.restaurant_credential).post(
            self.ingestion_url,
            self.payload(
                reference,
                request_type="FOOD_DELIVERY",
                passenger_count=0,
                load_description="Meal trays",
                load_quantity=4,
            ),
            format="json",
        )
        self.client_for(self.restaurant_credential).post(
            self.ingestion_url,
            self.payload(
                "RMS-ONLY",
                request_type="FOOD_DELIVERY",
                passenger_count=0,
                load_description="Restaurant-only delivery",
                load_quantity=1,
            ),
            format="json",
        )

        hotel_result = self.poll(self.hotel_credential, reference)
        restaurant_result = self.poll(self.restaurant_credential, reference)

        self.assertEqual(hotel_result.status_code, 200)
        self.assertEqual(restaurant_result.status_code, 200)
        self.assertEqual(hotel_result.json()["source_system"], "HOTEL_MANAGEMENT_SYSTEM")
        self.assertEqual(
            restaurant_result.json()["source_system"],
            "RESTAURANT_MANAGEMENT_SYSTEM",
        )
        self.assertNotEqual(
            hotel_result.json()["ftms_request_id"],
            restaurant_result.json()["ftms_request_id"],
        )
        self.assertEqual(self.poll(self.hotel_credential, "RMS-ONLY").status_code, 404)
        self.assertEqual(self.poll(self.restaurant_credential, "HMS-ONLY").status_code, 404)

    def test_polling_derives_assignment_execution_and_completion_states(self):
        reference = "HMS-LIFECYCLE"
        self.client_for(self.hotel_credential).post(
            self.ingestion_url, self.payload(reference), format="json"
        )
        item = TransportRequest.objects.get(external_reference=reference)
        self.assertEqual(self.poll(self.hotel_credential, reference).json()["status"], "RECEIVED")

        item.status = TransportRequest.Status.APPROVED
        item.save(update_fields=["status", "updated_at"])
        self.assertEqual(self.poll(self.hotel_credential, reference).json()["status"], "APPROVED")

        vehicle = Vehicle.objects.create(
            device_id="SOURCE-VEH-001",
            plate_number="SRC-001",
            display_name="Source Integration Van",
        )
        driver = Driver.objects.create(driver_code="SOURCE-DRV-001", first_name="Alex")
        assignment = DispatchAssignment.objects.create(
            transport_request=item,
            vehicle=vehicle,
            driver=driver,
            selection_mode=DispatchAssignment.SelectionMode.MANUAL,
            override_reason="Source integration lifecycle test",
            confirmed_by=self.hotel.user,
        )
        self.assertEqual(self.poll(self.hotel_credential, reference).json()["status"], "ASSIGNED")

        item.status = TransportRequest.Status.READY_FOR_DISPATCH
        item.assigned_vehicle = vehicle
        item.save(update_fields=["status", "assigned_vehicle", "updated_at"])
        self.assertEqual(
            self.poll(self.hotel_credential, reference).json()["status"],
            "READY_FOR_DISPATCH",
        )

        assignment.accepted_at = timezone.now()
        assignment.save(update_fields=["accepted_at", "updated_at"])
        self.assertEqual(
            self.poll(self.hotel_credential, reference).json()["status"],
            "DRIVER_ACCEPTED",
        )

        assignment.execution_status = DispatchAssignment.ExecutionStatus.IN_TRANSIT
        assignment.save(update_fields=["execution_status", "updated_at"])
        in_progress = self.poll(self.hotel_credential, reference).json()
        self.assertEqual(in_progress["status"], "IN_PROGRESS")
        self.assertEqual(in_progress["execution_status"], "IN_TRANSIT")

        completed_at = timezone.now()
        assignment.execution_status = DispatchAssignment.ExecutionStatus.COMPLETED
        assignment.completed_at = completed_at
        assignment.save(update_fields=["execution_status", "completed_at", "updated_at"])
        completed = self.poll(self.hotel_credential, reference).json()
        repeated = self.poll(self.hotel_credential, reference).json()

        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(completed["execution_status"], "COMPLETED")
        self.assertEqual(
            completed["completion_timestamp"],
            completed_at.isoformat().replace("+00:00", "Z"),
        )
        self.assertEqual(completed, repeated)
        item.refresh_from_db()
        self.assertEqual(item.status, TransportRequest.Status.READY_FOR_DISPATCH)

    def test_trusted_request_completes_through_authoritative_workflow(self):
        reference = "HMS-END-TO-END"
        source_client = self.client_for(self.hotel_credential)
        payload = self.payload(reference)

        created = source_client.post(self.ingestion_url, payload, format="json")
        replayed = source_client.post(self.ingestion_url, payload, format="json")

        self.assertEqual(created.status_code, 201)
        self.assertEqual(replayed.status_code, 200)
        self.assertEqual(created.json(), replayed.json())
        self.assertEqual(
            TransportRequest.objects.filter(
                source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
                external_reference=reference,
            ).count(),
            1,
        )
        self.assertEqual(self.poll(self.restaurant_credential, reference).status_code, 404)

        manager = get_user_model().objects.create_user(
            username="source-workflow-manager", is_staff=True
        )
        StaffProfile.objects.create(user=manager, role=StaffProfile.Role.FLEET_MANAGER)
        driver_user = get_user_model().objects.create_user(username="source-workflow-driver")
        today = timezone.localdate()
        driver = Driver.objects.create(
            driver_code="SOURCE-WORKFLOW-DRV",
            first_name="Maria",
            last_name="Reyes",
            linked_user=driver_user,
            license_number="N01",
            license_expiry_date=today + timedelta(days=30),
            medical_certificate_expiry_date=today + timedelta(days=30),
        )
        vehicle = Vehicle.objects.create(
            device_id="SOURCE-WORKFLOW-VEH",
            plate_number="SRC-E2E",
            display_name="Source Workflow Van",
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=8,
        )
        VehicleInspection.objects.create(
            vehicle=vehicle,
            inspection_date=today,
            inspection_type=VehicleInspection.InspectionType.PRE_TRIP,
            result=VehicleInspection.Result.PASSED,
            exterior_condition=VehicleInspection.Condition.OK,
            interior_condition=VehicleInspection.Condition.OK,
            tires_condition=VehicleInspection.Condition.OK,
            lights_condition=VehicleInspection.Condition.OK,
            brakes_condition=VehicleInspection.Condition.OK,
            fluids_condition=VehicleInspection.Condition.OK,
            safety_equipment_condition=VehicleInspection.Condition.OK,
            inspected_by=manager,
        )

        item = TransportRequest.objects.get(external_reference=reference)
        services.approve(item, manager)
        assignment = dispatch.confirm_assignment(
            transport_request_id=item.pk,
            vehicle_id=vehicle.pk,
            driver_id=driver.pk,
            selection_mode=DispatchAssignment.SelectionMode.MANUAL,
            user=manager,
            override_reason="Final integrated workflow regression",
        )
        services.prepare_dispatch(item, manager)
        assignment, accepted = accept_driver_assignment(
            assignment_id=assignment.pk,
            driver=driver,
            user=driver_user,
            expected_confirmed_at=assignment.confirmed_at,
        )
        self.assertTrue(accepted)

        for action in (
            DispatchExecutionEvent.Action.START_TOWARD_PICKUP,
            DispatchExecutionEvent.Action.ARRIVE_AT_PICKUP,
            DispatchExecutionEvent.Action.DEPART_PICKUP,
            DispatchExecutionEvent.Action.ARRIVE_AT_DESTINATION,
            DispatchExecutionEvent.Action.COMPLETE,
        ):
            assignment, changed = transition_driver_execution(
                assignment_id=assignment.pk,
                driver=driver,
                user=driver_user,
                action=action,
            )
            self.assertTrue(changed)

        completion_timestamp = assignment.completed_at
        assignment, changed = transition_driver_execution(
            assignment_id=assignment.pk,
            driver=driver,
            user=driver_user,
            action=DispatchExecutionEvent.Action.COMPLETE,
        )
        self.assertFalse(changed)
        self.assertEqual(assignment.execution_events.count(), 5)

        completed = self.poll(self.hotel_credential, reference).json()
        self.assertEqual(completed["external_reference"], reference)
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(completed["execution_status"], "COMPLETED")
        self.assertEqual(
            completed["completion_timestamp"],
            completion_timestamp.isoformat().replace("+00:00", "Z"),
        )
        item.refresh_from_db()
        self.assertEqual(item.status, TransportRequest.Status.READY_FOR_DISPATCH)

    def test_rejected_request_exposes_existing_review_note(self):
        reference = "HMS-REJECTED"
        self.client_for(self.hotel_credential).post(
            self.ingestion_url, self.payload(reference), format="json"
        )
        item = TransportRequest.objects.get(external_reference=reference)
        item.status = TransportRequest.Status.REJECTED
        item.save(update_fields=["status", "updated_at"])
        TransportRequestEvent.objects.create(
            request=item,
            event_type="REJECTED",
            previous_status=TransportRequest.Status.FOR_APPROVAL,
            new_status=TransportRequest.Status.REJECTED,
            performed_by=self.hotel.user,
            note="Requested journey is outside service scope.",
        )

        result = self.poll(self.hotel_credential, reference).json()

        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(result["rejection_note"], "Requested journey is outside service scope.")

    def test_rotation_revocation_and_hash_storage(self):
        original = self.hotel_credential
        self.assertNotEqual(self.hotel.credential_hash, original)
        self.assertTrue(credential_matches(self.hotel, original))

        rotated_client, rotated = rotate_integration_credential(self.hotel)

        self.assertEqual(
            self.client_for(original)
            .post(self.ingestion_url, self.payload(), format="json")
            .status_code,
            401,
        )
        self.assertEqual(
            self.client_for(rotated)
            .post(self.ingestion_url, self.payload("ROTATED-001"), format="json")
            .status_code,
            201,
        )
        self.assertNotIn(rotated, rotated_client.credential_hash)
        rotated_client.is_active = False
        rotated_client.save(update_fields=["is_active", "updated_at"])
        self.assertEqual(self.poll(rotated, "ROTATED-001").status_code, 401)

    def test_management_command_provisions_and_rotates_without_persisting_plaintext(self):
        created_output = StringIO()
        call_command(
            "create_integration_client",
            "Command Hotel",
            "--source-system",
            "HOTEL_MANAGEMENT_SYSTEM",
            stdout=created_output,
        )
        credential = (
            created_output.getvalue().split("Credential (shown once): ", 1)[1].splitlines()[0]
        )
        client = IntegrationClient.objects.get(name="Command Hotel")
        self.assertTrue(credential_matches(client, credential))
        self.assertNotIn(credential, client.credential_hash)
        self.assertFalse(client.user.has_usable_password())

        rotated_output = StringIO()
        call_command(
            "create_integration_client",
            "Command Hotel",
            "--rotate",
            stdout=rotated_output,
        )
        rotated = rotated_output.getvalue().split("Credential (shown once): ", 1)[1].splitlines()[0]
        client.refresh_from_db()
        self.assertFalse(credential_matches(client, credential))
        self.assertTrue(credential_matches(client, rotated))
        self.assertIsNotNone(client.rotated_at)

    def test_ordinary_staff_creation_endpoint_remains_denied(self):
        staff = get_user_model().objects.create_user(username="ordinary-manager", is_staff=True)
        StaffProfile.objects.create(user=staff, role=StaffProfile.Role.FLEET_MANAGER)
        client = APIClient()
        client.force_authenticate(staff)

        response = client.post(
            "/api/v1/transport-requests/",
            self.payload("STAFF-001"),
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(TransportRequest.objects.filter(external_reference="STAFF-001").exists())
