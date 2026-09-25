from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import RolePermission, StaffProfile
from transport_requests.models import TransportRequest


class TransportRequestCreationAuthorizationTests(TestCase):
    url = "/api/v1/transport-requests/"

    def setUp(self):
        self.manager = self.staff("manager", StaffProfile.Role.FLEET_MANAGER)
        self.dispatcher = self.staff("dispatcher", StaffProfile.Role.DISPATCHER)
        self.super_admin = get_user_model().objects.create_superuser(
            username="root", password="test"
        )
        StaffProfile.objects.create(
            user=self.super_admin, role=StaffProfile.Role.FLEET_ADMIN
        )
        for role in (StaffProfile.Role.FLEET_MANAGER, StaffProfile.Role.DISPATCHER):
            for action in ("VIEW", "EDIT"):
                RolePermission.objects.get_or_create(
                    role=role, module="TRANSPORT_REQUESTS", action=action
                )
        RolePermission.objects.get_or_create(
            role=StaffProfile.Role.FLEET_MANAGER,
            module="TRANSPORT_REQUESTS", action="APPROVE",
        )
        self.request_record = TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference="HMS-TRUSTED-001",
            request_type=TransportRequest.RequestType.AIRPORT_PICKUP,
            requester_name="Front Desk",
            pickup_name="NAIA Terminal 3",
            pickup_address="Pasay City",
            pickup_latitude="14.508600",
            pickup_longitude="121.019800",
            destination_name="Oxford Suites Makati",
            destination_address="Makati City",
            destination_latitude="14.565200",
            destination_longitude="121.028600",
            scheduled_pickup_at=timezone.now() + timedelta(hours=2),
            passenger_count=2,
            created_by=self.super_admin,
        )

    @staticmethod
    def staff(username, role):
        user = get_user_model().objects.create_user(
            username=username, password="test", is_staff=True
        )
        StaffProfile.objects.create(user=user, role=role)
        return user

    @staticmethod
    def client_for(user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def creation_payload(self):
        return {
            "source_system": "HOTEL_MANAGEMENT_SYSTEM",
            "external_reference": "CALLER-SUPPLIED-HMS-MARKER",
            "request_type": "AIRPORT_PICKUP",
            "requester_name": "Front Desk",
            "pickup_name": "NAIA Terminal 3",
            "pickup_address": "Pasay City",
            "destination_name": "Oxford Suites Makati",
            "destination_address": "Makati City",
            "scheduled_pickup_at": (timezone.now() + timedelta(hours=3)).isoformat(),
            "passenger_count": 2,
        }

    def test_all_staff_roles_fail_closed_for_manual_collection_post(self):
        for user in (self.manager, self.dispatcher, self.super_admin):
            with self.subTest(user=user.username):
                response = self.client_for(user).post(
                    self.url, self.creation_payload(), format="json"
                )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(
                    response.json()["detail"],
                    "Transport Request creation requires a trusted HMS, RMS, or "
                    "supply-chain integration identity.",
                )
        self.assertEqual(TransportRequest.objects.count(), 1)

    def test_staff_read_access_is_unchanged(self):
        for user in (self.manager, self.dispatcher, self.super_admin):
            with self.subTest(user=user.username):
                listing = self.client_for(user).get(self.url)
                self.assertEqual(listing.status_code, 200)
                self.assertEqual(listing.json()["count"], 1)
                detail = self.client_for(user).get(
                    f"{self.url}{self.request_record.pk}/"
                )
                self.assertEqual(detail.status_code, 200)

    def test_existing_edit_and_approval_workflow_is_unchanged(self):
        dispatcher = self.client_for(self.dispatcher)
        detail_url = f"{self.url}{self.request_record.pk}/"
        edited = dispatcher.patch(
            detail_url, {"notes": "Pickup details verified"}, format="json"
        )
        self.assertEqual(edited.status_code, 200)

        approval_url = f"{detail_url}approve/"
        self.assertEqual(
            dispatcher.post(approval_url, {}, format="json").status_code, 403
        )
        approved = self.client_for(self.manager).post(
            approval_url, {}, format="json"
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["status"], "APPROVED")
