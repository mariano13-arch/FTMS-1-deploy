from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework import serializers
from rest_framework.test import APIClient

from accounts.models import RolePermission, StaffProfile, UserNotification
from accounts.notifications import notify_capability_users
from fleet.maintenance import transition_maintenance
from fleet.models import Vehicle, VehicleMaintenanceRecord
from transport_requests.models import TransportRequest
from transport_requests.services import prepare_dispatch


class NotificationApiTests(TestCase):
    def setUp(self):
        RolePermission.objects.all().delete()
        self.user = self.make_staff("manager", StaffProfile.Role.FLEET_MANAGER)
        self.other = self.make_staff("dispatcher", StaffProfile.Role.DISPATCHER)
        self.admin = self.make_staff("admin", StaffProfile.Role.FLEET_ADMIN)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.own = self.notification(self.user, "own:1")
        self.other_notification = self.notification(self.other, "other:1")

    @staticmethod
    def make_staff(username, role, *, active=True):
        user = get_user_model().objects.create_user(
            username=username,
            password="test-password",
            is_staff=True,
            is_active=active,
        )
        StaffProfile.objects.create(user=user, role=role)
        return user

    @staticmethod
    def notification(recipient, source_key, *, is_read=False):
        return UserNotification.objects.create(
            recipient=recipient,
            notification_type=UserNotification.Type.SOS_ACTIVE,
            title="Operational notification",
            message="A real persisted event requires attention.",
            target_url="/alerts",
            source_key=source_key,
            is_read=is_read,
        )

    def test_list_and_unread_count_are_scoped_to_authenticated_user(self):
        response = self.client.get("/api/v1/auth/notifications/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()["results"]], [self.own.pk])
        self.assertEqual(
            self.client.get("/api/v1/auth/notifications/unread-count/").json(),
            {"unread_count": 1},
        )

    def test_user_cannot_mark_another_users_notification_read(self):
        response = self.client.post(
            f"/api/v1/auth/notifications/{self.other_notification.pk}/read/"
        )
        self.assertEqual(response.status_code, 404)
        self.other_notification.refresh_from_db()
        self.assertFalse(self.other_notification.is_read)

    def test_notification_content_is_immutable(self):
        self.own.title = "Rewritten title"
        with self.assertRaisesMessage(ValidationError, "Notification content is immutable"):
            self.own.save()

    def test_mark_one_and_mark_all_only_change_current_users_rows(self):
        second = self.notification(self.user, "own:2")
        response = self.client.post(f"/api/v1/auth/notifications/{self.own.pk}/read/")
        self.assertEqual(response.status_code, 200)
        self.own.refresh_from_db()
        self.assertTrue(self.own.is_read)
        self.assertIsNotNone(self.own.read_at)

        response = self.client.post("/api/v1/auth/notifications/mark-all-read/")
        self.assertEqual(response.json(), {"updated": 1})
        second.refresh_from_db()
        self.other_notification.refresh_from_db()
        self.assertTrue(second.is_read)
        self.assertFalse(self.other_notification.is_read)

    def test_fleet_admin_has_an_own_account_inbox(self):
        admin_notification = self.notification(self.admin, "admin:1")
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/v1/auth/notifications/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["id"], admin_notification.pk)

    def test_inactive_nonstaff_and_driver_identities_are_denied(self):
        inactive = self.make_staff("inactive", StaffProfile.Role.FLEET_STAFF, active=False)
        nonstaff = get_user_model().objects.create_user("driver", password="test-password")
        for user in (inactive, nonstaff):
            with self.subTest(user=user.username):
                self.client.force_authenticate(user)
                self.assertEqual(
                    self.client.get("/api/v1/auth/notifications/").status_code,
                    403,
                )


class NotificationRecipientTests(TestCase):
    def setUp(self):
        RolePermission.objects.all().delete()
        self.allowed = NotificationApiTests.make_staff("allowed", StaffProfile.Role.DISPATCHER)
        self.denied = NotificationApiTests.make_staff("denied", StaffProfile.Role.FLEET_STAFF)
        self.inactive = NotificationApiTests.make_staff(
            "inactive-recipient", StaffProfile.Role.DISPATCHER, active=False
        )
        self.driver = get_user_model().objects.create_user(
            "driver-recipient", password="test-password"
        )
        RolePermission.objects.create(
            role=StaffProfile.Role.DISPATCHER,
            module="DISPATCH_BOARD",
            action="VIEW",
        )

    def notify(self):
        return notify_capability_users(
            module="DISPATCH_BOARD",
            action="VIEW",
            notification_type=UserNotification.Type.TRANSPORT_READY,
            title="Transport Request Ready for Dispatch",
            message="TR-REAL is ready for dispatch planning.",
            target_url="/dispatch-board",
            source_key="transport-request-event:1:ready-for-dispatch",
        )

    def test_recipient_selection_uses_capability_and_excludes_ineligible_identities(self):
        self.notify()
        self.assertTrue(UserNotification.objects.filter(recipient=self.allowed).exists())
        self.assertFalse(UserNotification.objects.filter(recipient=self.denied).exists())
        self.assertFalse(UserNotification.objects.filter(recipient=self.inactive).exists())
        self.assertFalse(UserNotification.objects.filter(recipient=self.driver).exists())

    def test_deterministic_source_key_prevents_duplicates(self):
        self.notify()
        self.notify()
        self.assertEqual(UserNotification.objects.filter(recipient=self.allowed).count(), 1)

    def test_actor_can_be_explicitly_excluded(self):
        notify_capability_users(
            module="DISPATCH_BOARD",
            action="VIEW",
            notification_type=UserNotification.Type.DISPATCH_CONFIRMED,
            title="Dispatch Confirmed",
            message="Dispatch was confirmed for TR-REAL.",
            target_url="/transport-requests/00000000-0000-0000-0000-000000000001",
            source_key="dispatch-assignment-event:1:assignment-confirmed",
            exclude_user_id=self.allowed.pk,
        )
        self.assertFalse(UserNotification.objects.filter(recipient=self.allowed).exists())

    def test_sos_message_does_not_claim_a_location(self):
        notify_capability_users(
            module="DISPATCH_BOARD",
            action="VIEW",
            notification_type=UserNotification.Type.SOS_ACTIVE,
            title="Emergency SOS Active",
            message="An emergency SOS was activated for Device 12.",
            target_url="/alerts",
            source_key="vehicle-emergency-sos:12:active",
        )
        notification = UserNotification.objects.get(recipient=self.allowed)
        self.assertNotIn("location", notification.message.lower())
        self.assertNotIn("coordinates", notification.message.lower())


class NotificationEventSourceTests(TestCase):
    def setUp(self):
        RolePermission.objects.all().delete()
        self.dispatcher = NotificationApiTests.make_staff(
            "event-dispatcher", StaffProfile.Role.DISPATCHER
        )
        self.staff = NotificationApiTests.make_staff("event-staff", StaffProfile.Role.FLEET_STAFF)
        for role, module in (
            (StaffProfile.Role.DISPATCHER, "DISPATCH_BOARD"),
            (StaffProfile.Role.FLEET_STAFF, "INSPECTIONS"),
            (StaffProfile.Role.FLEET_STAFF, "MAINTENANCE"),
        ):
            RolePermission.objects.create(role=role, module=module, action="VIEW")
        self.vehicle = Vehicle.objects.create(
            device_id="NOTIFY-VAN-1",
            plate_number="NOTIFY-1",
            display_name="Notification Test Van",
        )

    def request(self):
        return TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference="NOTIFY-TR-1",
            request_type=TransportRequest.RequestType.GUEST_TRANSFER,
            request_category=TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            requester_name="Front Desk",
            pickup_name="Oxford Suites Makati",
            pickup_address="Makati",
            pickup_latitude="14.5636",
            pickup_longitude="121.0297",
            destination_name="Airport",
            destination_address="Pasay",
            destination_latitude="14.5086",
            destination_longitude="121.0198",
            scheduled_pickup_at=timezone.now() + timedelta(hours=2),
            passenger_count=2,
            status=TransportRequest.Status.APPROVED,
            created_by=self.dispatcher,
            approved_by=self.dispatcher,
            approved_at=timezone.now(),
        )

    def test_ready_for_dispatch_notifies_only_dispatch_view_recipients_once(self):
        request = self.request()
        with self.captureOnCommitCallbacks(execute=True):
            prepare_dispatch(request, self.dispatcher)
        notification = UserNotification.objects.get(recipient=self.dispatcher)
        self.assertEqual(notification.target_url, "/dispatch-board")
        self.assertIn(request.request_number, notification.message)
        self.assertFalse(UserNotification.objects.filter(recipient=self.staff).exists())
        with (
            self.assertRaises(serializers.ValidationError),
            self.captureOnCommitCallbacks(execute=True),
        ):
            prepare_dispatch(request, self.dispatcher)
        self.assertEqual(UserNotification.objects.filter(recipient=self.dispatcher).count(), 1)

    def test_failed_transaction_does_not_leave_a_notification(self):
        request = self.request()
        try:
            with self.captureOnCommitCallbacks(execute=True):
                from django.db import transaction

                with transaction.atomic():
                    prepare_dispatch(request, self.dispatcher)
                    raise RuntimeError("force rollback")
        except RuntimeError:
            pass
        self.assertFalse(UserNotification.objects.exists())

    def test_maintenance_completion_notifies_view_recipients(self):
        record = VehicleMaintenanceRecord.objects.create(
            vehicle=self.vehicle,
            title="Brake service",
            status=VehicleMaintenanceRecord.Status.IN_PROGRESS,
            created_by=self.staff,
        )
        with self.captureOnCommitCallbacks(execute=True):
            transition_maintenance(record.pk, VehicleMaintenanceRecord.Status.COMPLETED)
        notification = UserNotification.objects.get(recipient=self.staff)
        self.assertEqual(notification.target_url, "/maintenance")
        self.assertIn("Brake service", notification.message)
