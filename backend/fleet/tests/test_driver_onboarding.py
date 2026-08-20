from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.mail.backends.base import BaseEmailBackend
from django.db import IntegrityError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from fleet.driver_onboarding import DriverUsernameConflict
from fleet.models import Driver


class FailingEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        raise RuntimeError("Development delivery failure")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DRIVER_MOBILE_ACCOUNT_SETUP_URL="ftms-driver://setup-password",
    DRIVER_MOBILE_APP_DOWNLOAD_URL="",
)
class DriverOnboardingTests(TestCase):
    password = "A-private-driver-password-42!"

    def setUp(self):
        cache.clear()
        self.admin = get_user_model().objects.create_superuser(
            username="driver-admin",
            password="A-strong-admin-password-42!",
            email="admin@example.test",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def create_driver(self, driver_code="DRV-NEW-001", email="driver@example.test"):
        return self.client.post(
            "/api/v1/drivers/",
            {
                "driver_code": driver_code,
                "first_name": "Maria",
                "middle_name": "Santos",
                "last_name": "Reyes",
                "email": email,
                "employment_status": "ACTIVE",
            },
            format="multipart",
        )

    def setup_parameters(self):
        setup_link = next(
            line for line in mail.outbox[-1].body.splitlines() if line.startswith("ftms-driver://")
        )
        query = parse_qs(urlsplit(setup_link).query)
        return query["uid"][0], query["token"][0]

    def setup_password(self, uid, token, password=None, confirmation=None):
        return APIClient().post(
            "/api/v1/driver-auth/setup-password/",
            {
                "uid": uid,
                "token": token,
                "new_password": password or self.password,
                "confirm_password": confirmation or password or self.password,
            },
            format="json",
        )

    def test_create_provisions_linked_non_staff_user_with_unusable_password(self):
        response = self.create_driver(driver_code=" drv-new-001 ")

        self.assertEqual(response.status_code, 201)
        driver = Driver.objects.select_related("linked_user").get(driver_code="DRV-NEW-001")
        user = driver.linked_user
        self.assertEqual(user.username, driver.driver_code)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.has_usable_password())
        self.assertTrue(response.json()["onboarding"]["account_provisioned"])

    def test_invitation_uses_driver_email_and_contains_no_plaintext_password(self):
        response = self.create_driver()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["onboarding"]["email_status"], "SENT")
        self.assertEqual(len(mail.outbox), 1)
        invitation = mail.outbox[0]
        self.assertEqual(invitation.to, ["driver@example.test"])
        self.assertIn("Maria Santos Reyes", invitation.body)
        self.assertIn("Username: DRV-NEW-001", invitation.body)
        self.assertIn("ftms-driver://setup-password", invitation.body)
        self.assertNotIn(self.password, invitation.body)

    @override_settings(
        DRIVER_MOBILE_ACCOUNT_SETUP_URL="http://localhost:8081/setup-password"
    )
    def test_web_setup_base_url_generates_web_preview_route(self):
        self.assertEqual(self.create_driver().status_code, 201)

        setup_link = next(
            line
            for line in mail.outbox[-1].body.splitlines()
            if line.startswith("http://localhost:8081/")
        )
        parts = urlsplit(setup_link)
        query = parse_qs(parts.query)

        self.assertEqual(parts.scheme, "http")
        self.assertEqual(parts.netloc, "localhost:8081")
        self.assertEqual(parts.path, "/setup-password")
        self.assertEqual(set(query), {"uid", "token"})
        self.assertTrue(query["uid"][0])
        self.assertTrue(query["token"][0])

    def test_native_setup_base_url_generates_mobile_deep_link(self):
        self.assertEqual(self.create_driver().status_code, 201)

        setup_link = next(
            line
            for line in mail.outbox[-1].body.splitlines()
            if line.startswith("ftms-driver://")
        )
        parts = urlsplit(setup_link)
        query = parse_qs(parts.query)

        self.assertEqual(parts.scheme, "ftms-driver")
        self.assertEqual(parts.netloc, "setup-password")
        self.assertEqual(parts.path, "")
        self.assertEqual(set(query), {"uid", "token"})

    def test_missing_email_is_reported_without_inventing_destination(self):
        response = self.create_driver(email="")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json()["onboarding"]["email_status"], "NOT_SENT_MISSING_EMAIL"
        )
        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNotNone(Driver.objects.get(driver_code="DRV-NEW-001").linked_user)

    @override_settings(
        EMAIL_BACKEND="fleet.tests.test_driver_onboarding.FailingEmailBackend"
    )
    def test_email_failure_leaves_consistent_link_and_reports_failure(self):
        with self.assertLogs("fleet.driver_onboarding", level="ERROR") as logs:
            response = self.create_driver()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["onboarding"]["email_status"], "NOT_SENT_ERROR")
        driver = Driver.objects.select_related("linked_user").get(driver_code="DRV-NEW-001")
        self.assertEqual(driver.linked_user.username, driver.driver_code)
        self.assertIn(f"driver_id={driver.pk}", logs.output[0])
        self.assertIn("error_type=RuntimeError", logs.output[0])
        self.assertNotIn("setup-password", logs.output[0])

    def test_duplicate_username_returns_conflict_without_creating_driver(self):
        existing = get_user_model().objects.create_user(username="drv-conflict")

        response = self.create_driver(driver_code="DRV-CONFLICT")

        self.assertEqual(response.status_code, 409)
        self.assertFalse(Driver.objects.filter(driver_code="DRV-CONFLICT").exists())
        self.assertEqual(get_user_model().objects.get(username="drv-conflict"), existing)

    def test_unrelated_integrity_error_surfaces_and_rolls_back_driver_and_user(self):
        user_model = get_user_model()
        original_save = user_model.save

        def fail_new_driver_user(instance, *args, **kwargs):
            if instance.username == "DRV-INTEGRITY":
                raise IntegrityError("Unrelated database constraint failure")
            return original_save(instance, *args, **kwargs)

        with patch.object(user_model, "save", new=fail_new_driver_user):
            with self.assertRaises(IntegrityError) as raised:
                self.create_driver(driver_code="DRV-INTEGRITY")

        self.assertNotIsInstance(raised.exception, DriverUsernameConflict)
        self.assertFalse(Driver.objects.filter(driver_code="DRV-INTEGRITY").exists())
        self.assertFalse(user_model.objects.filter(username="DRV-INTEGRITY").exists())

    def test_valid_token_sets_password_once_and_enables_driver_login(self):
        self.assertEqual(self.create_driver().status_code, 201)
        uid, token = self.setup_parameters()

        setup_response = self.setup_password(uid, token)

        self.assertEqual(setup_response.status_code, 204)
        user = get_user_model().objects.get(username="DRV-NEW-001")
        self.assertTrue(user.check_password(self.password))
        self.assertEqual(self.setup_password(uid, token).status_code, 400)

        login_client = APIClient(enforce_csrf_checks=True)
        csrf_response = login_client.get("/api/v1/driver-auth/csrf/")
        login_response = login_client.post(
            "/api/v1/driver-auth/login/",
            {"username": "DRV-NEW-001", "password": self.password},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_response.json()["csrf_token"],
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.json()["driver"]["driver_code"], "DRV-NEW-001")

    def test_invalid_token_and_mismatched_passwords_are_rejected(self):
        self.assertEqual(self.create_driver().status_code, 201)
        uid, token = self.setup_parameters()

        self.assertEqual(self.setup_password(uid, "invalid-token").status_code, 400)
        mismatch = self.setup_password(
            uid,
            token,
            password=self.password,
            confirmation="A-different-private-password-42!",
        )
        self.assertEqual(mismatch.status_code, 400)
        self.assertIn("confirm_password", mismatch.json())
        self.assertFalse(
            get_user_model().objects.get(username="DRV-NEW-001").has_usable_password()
        )

    def test_weak_password_is_rejected_by_django_validation(self):
        self.assertEqual(self.create_driver().status_code, 201)
        uid, token = self.setup_parameters()

        response = self.setup_password(uid, token, password="password")

        self.assertEqual(response.status_code, 400)
        self.assertIn("new_password", response.json())
        self.assertFalse(
            get_user_model().objects.get(username="DRV-NEW-001").has_usable_password()
        )
