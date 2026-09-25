from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.audit import record_audit_event
from accounts.models import AuditEvent, RolePermission, StaffProfile


class AuditEventTests(TestCase):
    password = "A-strong-test-password-42!"

    def setUp(self):
        cache.clear()
        self.admin = self.create_staff("admin", StaffProfile.Role.FLEET_ADMIN)
        self.manager = self.create_staff("manager", StaffProfile.Role.FLEET_MANAGER)
        self.dispatcher = self.create_staff("dispatcher", StaffProfile.Role.DISPATCHER)
        self.staff = self.create_staff("staff", StaffProfile.Role.FLEET_STAFF)

    def create_staff(self, username, role):
        user = get_user_model().objects.create_user(
            username=username,
            password=self.password,
            is_staff=True,
            is_active=True,
        )
        StaffProfile.objects.create(user=user, role=role)
        return user

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_helper_redacts_sensitive_metadata(self):
        event = record_audit_event(
            action="LOGIN_FAILURE",
            actor=self.admin,
            target=self.admin,
            metadata={
                "reason": "invalid_credentials",
                "password": "secret",
                "nested": {"csrf_token": "token", "safe": "kept"},
            },
        )

        self.assertEqual(event.metadata["reason"], "invalid_credentials")
        self.assertNotIn("password", event.metadata)
        self.assertEqual(event.metadata["nested"], {"safe": "kept"})

    def test_audit_event_is_application_immutable(self):
        event = record_audit_event(action="LOGIN_SUCCESS", actor=self.admin, target=self.admin)
        event.action = "CHANGED"

        with self.assertRaises(ValueError):
            event.save()
        with self.assertRaises(ValueError):
            event.delete()

    def test_fleet_admin_can_list_and_managed_staff_are_denied(self):
        record_audit_event(action="LOGIN_SUCCESS", actor=self.admin, target=self.admin)

        self.assertEqual(
            self.client_for(self.admin).get("/api/v1/auth/audit-logs/").status_code,
            200,
        )
        for user in (self.manager, self.dispatcher, self.staff):
            with self.subTest(role=user.staff_profile.role):
                self.assertEqual(
                    self.client_for(user).get("/api/v1/auth/audit-logs/").status_code,
                    403,
                )

    def test_filters_and_pagination(self):
        first = record_audit_event(action="LOGIN_SUCCESS", actor=self.admin, target=self.admin)
        second = record_audit_event(
            action="STAFF_ROLE_CHANGED",
            actor=self.admin,
            target=self.manager,
            changes={"role": {"old": "FLEET_STAFF", "new": "DISPATCHER"}},
        )
        AuditEvent.objects.filter(pk=first.pk).update(
            occurred_at=timezone.now() - timedelta(days=2)
        )

        client = self.client_for(self.admin)
        self.assertEqual(
            client.get("/api/v1/auth/audit-logs/?action=STAFF_ROLE_CHANGED").json()["count"],
            1,
        )
        self.assertEqual(
            client.get(f"/api/v1/auth/audit-logs/?actor={self.admin.pk}").json()["count"],
            2,
        )
        self.assertEqual(client.get("/api/v1/auth/audit-logs/?outcome=SUCCESS").json()["count"], 2)
        self.assertEqual(
            client.get(
                f"/api/v1/auth/audit-logs/?occurred_after={second.occurred_at.isoformat()}"
            ).json()["count"],
            1,
        )
        self.assertIn("results", client.get("/api/v1/auth/audit-logs/?page_size=1").json())

    def test_staff_and_permission_mutations_create_sanitized_events(self):
        client = self.client_for(self.admin)
        create = client.post(
            "/api/v1/auth/staff/",
            {
                "username": "new-user",
                "email": "new-user@example.com",
                "first_name": "New",
                "last_name": "User",
                "role": "FLEET_STAFF",
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        target = get_user_model().objects.get(username="new-user")

        role = client.patch(
            f"/api/v1/auth/staff/{target.pk}/role/",
            {"role": "DISPATCHER"},
            format="json",
        )
        status = client.patch(
            f"/api/v1/auth/staff/{target.pk}/status/",
            {"is_active": False},
            format="json",
        )
        permissions = client.put(
            "/api/v1/auth/role-permissions/DISPATCHER/",
            {"permissions": [{"module": "USERS_ACCESS", "action": "VIEW_USERS"}]},
            format="json",
        )

        self.assertEqual(role.status_code, 200)
        self.assertEqual(status.status_code, 200)
        self.assertEqual(permissions.status_code, 200)
        self.assertTrue(
            AuditEvent.objects.filter(action="STAFF_CREATED", target_id=str(target.pk)).exists()
        )
        self.assertEqual(
            AuditEvent.objects.get(action="STAFF_ROLE_CHANGED", target_id=str(target.pk)).changes,
            {"role": {"old": "FLEET_STAFF", "new": "DISPATCHER"}},
        )
        self.assertEqual(
            AuditEvent.objects.get(action="STAFF_STATUS_CHANGED", target_id=str(target.pk)).changes,
            {"is_active": {"old": True, "new": False}},
        )
        self.assertEqual(
            AuditEvent.objects.get(action="ROLE_PERMISSIONS_REPLACED").metadata,
            {"added": ["USERS_ACCESS.VIEW_USERS"], "removed": []},
        )
        self.assertEqual(RolePermission.objects.filter(role="DISPATCHER").count(), 1)
