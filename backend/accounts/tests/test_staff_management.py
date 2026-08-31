from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.test.utils import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from accounts.models import StaffProfile


class StaffManagementTests(TestCase):
    def setUp(self):
        cache.clear()
        self.password = "A-strong-test-password-42!"
        self.super_admin = get_user_model().objects.create_superuser(
            username="root", password=self.password, email="root@example.com"
        )
        self.manager = self.create_staff("manager", StaffProfile.Role.FLEET_MANAGER)
        self.dispatcher = self.create_staff("dispatcher", StaffProfile.Role.DISPATCHER)
        self.managed_url = "/api/v1/auth/staff/"

    def create_staff(self, username, role, *, active=True, usable_password=True):
        user = get_user_model().objects.create_user(
            username=username,
            password=self.password if usable_password else None,
            is_staff=True,
            is_active=active,
        )
        if not usable_password:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        StaffProfile.objects.create(user=user, role=role)
        return user

    def authenticated_client(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def create_payload(self, username="new-manager", role="FLEET_MANAGER"):
        return {
            "username": username,
            "email": f"{username}@example.com",
            "first_name": "New",
            "last_name": "Staff",
            "role": role,
        }

    def test_super_admin_lists_only_sanitized_managed_staff(self):
        response = self.authenticated_client(self.super_admin).get(self.managed_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {item["username"] for item in response.json()["results"]},
            {"manager", "dispatcher"},
        )
        forbidden = {"password", "token", "sessionid", "setup_token"}
        for item in response.json()["results"]:
            self.assertTrue(forbidden.isdisjoint(item))
            self.assertIn(item["setup_status"], {"complete", "pending"})

    def test_staff_management_requires_super_admin(self):
        targets = [
            ("get", self.managed_url, None),
            ("post", self.managed_url, self.create_payload()),
            ("patch", f"{self.managed_url}{self.manager.pk}/role/", {"role": "DISPATCHER"}),
            ("patch", f"{self.managed_url}{self.manager.pk}/status/", {"is_active": False}),
        ]
        for user in (self.manager, self.dispatcher):
            for method, url, payload in targets:
                with self.subTest(role=user.staff_profile.role, method=method, url=url):
                    if payload is not None:
                        response = getattr(self.authenticated_client(user), method)(
                            url, payload, format="json"
                        )
                    else:
                        response = getattr(self.authenticated_client(user), method)(url)
                    self.assertEqual(response.status_code, 403)
        self.assertEqual(APIClient().get(self.managed_url).status_code, 401)

    def test_super_admin_creates_supported_roles_with_unusable_password(self):
        client = self.authenticated_client(self.super_admin)
        for role in (StaffProfile.Role.FLEET_MANAGER, StaffProfile.Role.DISPATCHER):
            username = f"new-{role.lower()}"
            with self.subTest(role=role):
                response = client.post(
                    self.managed_url, self.create_payload(username, role), format="json"
                )
                self.assertEqual(response.status_code, 201)
                user = get_user_model().objects.get(username=username)
                self.assertTrue(user.is_staff)
                self.assertFalse(user.is_superuser)
                self.assertFalse(user.has_usable_password())
                self.assertEqual(user.staff_profile.role, role)
                self.assertEqual(response.json()["setup_status"], "pending")
                self.assertNotIn("password", response.json())
                self.assertNotIn("token", response.json())

    def test_create_rejects_duplicate_invalid_role_super_admin_and_password(self):
        client = self.authenticated_client(self.super_admin)
        cases = [
            (self.create_payload("manager"), "username"),
            (self.create_payload("invalid-role", "SUPER_ADMIN"), "role"),
            ({**self.create_payload("with-password"), "password": self.password}, "password"),
        ]
        for payload, field in cases:
            with self.subTest(field=field):
                response = client.post(self.managed_url, payload, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json())

    @patch(
        "accounts.views.StaffProfile.objects.create",
        side_effect=RuntimeError("profile creation failed"),
    )
    def test_creation_is_atomic(self, _create_profile):
        with self.assertRaises(RuntimeError):
            self.authenticated_client(self.super_admin).post(
                self.managed_url, self.create_payload("atomic-user"), format="json"
            )
        self.assertFalse(get_user_model().objects.filter(username="atomic-user").exists())

    def test_role_update_and_status_management(self):
        client = self.authenticated_client(self.super_admin)
        role_response = client.patch(
            f"{self.managed_url}{self.manager.pk}/role/",
            {"role": "DISPATCHER"},
            format="json",
        )
        self.assertEqual(role_response.status_code, 200)
        self.manager.staff_profile.refresh_from_db()
        self.assertEqual(self.manager.staff_profile.role, StaffProfile.Role.DISPATCHER)

        for active in (False, True):
            response = client.patch(
                f"{self.managed_url}{self.manager.pk}/status/",
                {"is_active": active},
                format="json",
            )
            self.assertEqual(response.status_code, 200)
            self.manager.refresh_from_db()
            self.assertEqual(self.manager.is_active, active)

    def test_invalid_status_role_and_non_profile_target_are_rejected(self):
        client = self.authenticated_client(self.super_admin)
        self.assertEqual(
            client.patch(
                f"{self.managed_url}{self.manager.pk}/status/",
                {"is_active": "false"},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            client.patch(
                f"{self.managed_url}{self.manager.pk}/role/",
                {"role": "SUPER_ADMIN"},
                format="json",
            ).status_code,
            400,
        )
        profileless = get_user_model().objects.create_user(
            username="profileless", password=self.password, is_staff=True
        )
        self.assertEqual(
            client.patch(
                f"{self.managed_url}{profileless.pk}/role/",
                {"role": "DISPATCHER"},
                format="json",
            ).status_code,
            400,
        )

    def test_normal_endpoint_cannot_modify_superuser(self):
        client = self.authenticated_client(self.super_admin)
        for suffix, payload in (
            ("role/", {"role": "DISPATCHER"}),
            ("status/", {"is_active": False}),
        ):
            response = client.patch(
                f"{self.managed_url}{self.super_admin.pk}/{suffix}",
                payload,
                format="json",
            )
            self.assertEqual(response.status_code, 400)
        self.super_admin.refresh_from_db()
        self.assertTrue(self.super_admin.is_superuser)
        self.assertTrue(self.super_admin.is_active)


class StaffPasswordSetupTests(TestCase):
    def setUp(self):
        cache.clear()
        self.password = "A-new-strong-staff-password-42!"
        self.user = get_user_model().objects.create_user(
            username="invited", is_staff=True, is_active=True
        )
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        StaffProfile.objects.create(
            user=self.user, role=StaffProfile.Role.FLEET_MANAGER
        )
        self.client = APIClient(enforce_csrf_checks=True)
        self.url = "/api/v1/auth/staff/setup-password/"

    def setup_payload(self, *, token=None, password=None):
        value = password or self.password
        return {
            "uid": urlsafe_base64_encode(force_bytes(self.user.pk)),
            "token": token or default_token_generator.make_token(self.user),
            "new_password": value,
            "confirm_password": value,
        }

    def csrf_token(self):
        return self.client.get("/api/v1/auth/csrf/").json()["csrf_token"]

    def post_setup(self, payload):
        return self.client.post(
            self.url,
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

    def test_valid_setup_sets_password_invalidates_token_and_allows_login(self):
        payload = self.setup_payload()
        response = self.post_setup(payload)
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))
        self.assertEqual(self.post_setup(payload).status_code, 400)

        login_token = self.csrf_token()
        login = self.client.post(
            "/api/v1/auth/login/",
            {"username": self.user.username, "password": self.password},
            format="json",
            HTTP_X_CSRFTOKEN=login_token,
        )
        self.assertEqual(login.status_code, 200)

    def test_invalid_token_inactive_account_and_weak_password_are_rejected(self):
        self.assertEqual(
            self.post_setup(self.setup_payload(token="invalid-token")).status_code,
            400,
        )
        weak = self.post_setup(self.setup_payload(password="weak"))
        self.assertEqual(weak.status_code, 400)
        self.assertIn("new_password", weak.json())
        self.assertFalse(self.user.has_usable_password())

        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(self.post_setup(self.setup_payload()).status_code, 400)

    def test_deactivated_staff_cannot_log_in(self):
        self.assertEqual(self.post_setup(self.setup_payload()).status_code, 204)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        token = self.csrf_token()
        response = self.client.post(
            "/api/v1/auth/login/",
            {"username": self.user.username, "password": self.password},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 401)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    STAFF_ACCOUNT_SETUP_URL="https://ftms.example/setup-staff-password",
)
class StaffInvitationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.password = "A-strong-test-password-42!"
        self.super_admin = get_user_model().objects.create_superuser(
            username="root-invitations", password=self.password
        )
        self.manager = self.create_staff(
            "invitation-manager", StaffProfile.Role.FLEET_MANAGER, usable=True
        )
        self.dispatcher = self.create_staff(
            "invitation-dispatcher", StaffProfile.Role.DISPATCHER, usable=True
        )
        self.pending = self.create_staff(
            "pending-staff", StaffProfile.Role.FLEET_MANAGER, usable=False
        )
        self.client = APIClient()
        self.client.force_authenticate(self.super_admin)

    def create_staff(self, username, role, *, usable):
        user = get_user_model().objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password=self.password if usable else None,
            is_staff=True,
            is_active=True,
        )
        if not usable:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        StaffProfile.objects.create(user=user, role=role)
        return user

    def resend_url(self, user):
        return f"/api/v1/auth/staff/{user.pk}/resend-invitation/"

    def invitation_parameters(self, message):
        setup_url = next(
            line for line in message.body.splitlines() if "setup-staff-password" in line
        )
        query = parse_qs(urlsplit(setup_url).query)
        return query["uid"][0], query["token"][0]

    def test_creation_sends_invitation_without_exposing_link(self):
        response = self.client.post(
            "/api/v1/auth/staff/",
            {
                "username": "created-by-admin",
                "email": "created@example.com",
                "first_name": "Created",
                "last_name": "Staff",
                "role": "DISPATCHER",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["invitation_delivery"], "SENT")
        user = get_user_model().objects.get(username="created-by-admin")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["created@example.com"])
        self.assertIn("setup-staff-password", mail.outbox[0].body)
        serialized = response.content.decode()
        self.assertNotIn("setup-staff-password", serialized)
        self.assertNotIn("uid=", serialized)
        self.assertNotIn("token=", serialized)

    def test_generated_invitation_completes_password_setup(self):
        self.assertEqual(self.client.post(self.resend_url(self.pending)).status_code, 200)
        uid, token = self.invitation_parameters(mail.outbox[0])
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf = csrf_client.get("/api/v1/auth/csrf/").json()["csrf_token"]
        response = csrf_client.post(
            "/api/v1/auth/staff/setup-password/",
            {
                "uid": uid,
                "token": token,
                "new_password": "A-new-valid-password-42!",
                "confirm_password": "A-new-valid-password-42!",
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 204)
        self.pending.refresh_from_db()
        self.assertTrue(self.pending.check_password("A-new-valid-password-42!"))

    def test_only_super_admin_can_resend_invitation(self):
        for user, expected in (
            (self.manager, 403),
            (self.dispatcher, 403),
            (None, 401),
        ):
            client = APIClient()
            if user is not None:
                client.force_authenticate(user)
            with self.subTest(user=getattr(user, "username", "anonymous")):
                self.assertEqual(
                    client.post(self.resend_url(self.pending)).status_code, expected
                )
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_rejects_completed_inactive_and_superuser_accounts(self):
        self.pending.is_active = False
        self.pending.save(update_fields=["is_active"])
        for target in (self.manager, self.pending, self.super_admin):
            with self.subTest(target=target.username):
                self.assertEqual(
                    self.client.post(self.resend_url(target)).status_code, 400
                )
        self.assertEqual(len(mail.outbox), 0)

    @patch("accounts.staff_invitations.send_mail", side_effect=RuntimeError("mail down"))
    def test_email_failure_is_sanitized_and_account_remains_created(self, _send):
        with self.assertLogs("accounts.staff_invitations", level="ERROR") as logs:
            response = self.client.post(
                "/api/v1/auth/staff/",
                {
                    "username": "delivery-failed",
                    "email": "delivery-failed@example.com",
                    "role": "FLEET_MANAGER",
                },
                format="json",
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["invitation_delivery"], "NOT_SENT_ERROR")
        self.assertTrue(
            get_user_model().objects.filter(username="delivery-failed").exists()
        )
        self.assertNotIn("setup-staff-password", response.content.decode())
        self.assertNotIn("setup-staff-password", logs.output[0])
        self.assertNotIn("token", logs.output[0].lower())

    @override_settings(
        EMAIL_BACKEND="accounts.tests.test_staff_management.FailingEmailBackend"
    )
    def test_resend_email_failure_returns_service_unavailable(self):
        response = self.client.post(self.resend_url(self.pending))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["invitation_delivery"], "NOT_SENT_ERROR")
        self.assertNotIn("setup-staff-password", response.content.decode())

    def test_email_is_required_and_staff_list_never_exposes_setup_url(self):
        missing = self.client.post(
            "/api/v1/auth/staff/",
            {"username": "no-email", "role": "DISPATCHER"},
            format="json",
        )
        self.assertEqual(missing.status_code, 400)
        self.assertIn("email", missing.json())
        listed = self.client.get("/api/v1/auth/staff/")
        self.assertEqual(listed.status_code, 200)
        body = listed.content.decode()
        self.assertNotIn("setup-staff-password", body)
        self.assertNotIn("uid=", body)
        self.assertNotIn("token=", body)


class FailingEmailBackend:
    def __init__(self, *args, **kwargs):
        pass

    def send_messages(self, email_messages):
        raise RuntimeError("mail down")
