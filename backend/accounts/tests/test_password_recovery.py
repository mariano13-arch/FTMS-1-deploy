from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from accounts.models import ActiveUserSession, StaffProfile, TwoFactorCredential


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    STAFF_PASSWORD_RESET_URL="https://ftms.example/reset-password",
)
class PasswordRecoveryTests(TestCase):
    password = "A-strong-test-password-42!"
    replacement = "A-new-strong-test-password-43!"

    def setUp(self):
        cache.clear()
        self.user = self.make_staff("manager", "manager@example.com")

    def make_staff(self, username, email, **fields):
        user = get_user_model().objects.create_user(
            username=username, email=email, password=self.password, is_staff=True, **fields
        )
        StaffProfile.objects.create(user=user, role=StaffProfile.Role.DISPATCHER)
        return user

    def csrf(self, client):
        return client.get("/api/v1/auth/csrf/").json()["csrf_token"]

    def post_public(self, path, data, client=None):
        client = client or APIClient(enforce_csrf_checks=True)
        return client.post(path, data, format="json", HTTP_X_CSRFTOKEN=self.csrf(client))

    def reset_payload(self, user=None, token=None, password=None):
        user = user or self.user
        value = password or self.replacement
        return {
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": token or default_token_generator.make_token(user),
            "new_password": value,
            "confirm_password": value,
        }

    def test_known_and_unknown_requests_are_indistinguishable(self):
        known = self.post_public("/api/v1/auth/forgot-password/", {"email": self.user.email})
        self.assertEqual(len(mail.outbox), 1)
        unknown = self.post_public("/api/v1/auth/forgot-password/", {"email": "nobody@example.com"})
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.json(), unknown.json())
        query = parse_qs(urlsplit(mail.outbox[0].body.splitlines()[3]).query)
        self.assertIn("uid", query)
        self.assertIn("token", query)

    def test_inactive_and_driver_accounts_do_not_receive_reset_email(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        get_user_model().objects.create_user(
            username="driver", email="driver@example.com", password=self.password
        )
        for email in (self.user.email, "driver@example.com"):
            response = self.post_public("/api/v1/auth/forgot-password/", {"email": email})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(mail.outbox, [])

    def test_forgot_password_is_rate_limited(self):
        client = APIClient(enforce_csrf_checks=True)
        responses = [
            self.post_public("/api/v1/auth/forgot-password/", {"email": self.user.email}, client)
            for _ in range(6)
        ]
        self.assertTrue(all(response.status_code == 200 for response in responses[:5]))
        self.assertEqual(responses[5].status_code, 429)

    def test_reset_completion_is_rate_limited_independently(self):
        client = APIClient(enforce_csrf_checks=True)
        payload = self.reset_payload(token="invalid")
        responses = [
            self.post_public("/api/v1/auth/reset-password/", payload, client)
            for _ in range(11)
        ]
        self.assertTrue(all(response.status_code == 400 for response in responses[:10]))
        self.assertEqual(responses[10].status_code, 429)

    def test_valid_token_changes_password_is_single_use_and_preserves_two_factor(self):
        credential = TwoFactorCredential.objects.create(
            user=self.user, encrypted_secret="preserved", is_enabled=True
        )
        payload = self.reset_payload()
        response = self.post_public("/api/v1/auth/reset-password/", payload)
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.replacement))
        credential.refresh_from_db()
        self.assertTrue(credential.is_enabled)
        self.assertEqual(self.post_public("/api/v1/auth/reset-password/", payload).status_code, 400)

    def test_invalid_expired_and_weak_password_are_rejected(self):
        invalid = self.reset_payload(token="invalid")
        self.assertEqual(self.post_public("/api/v1/auth/reset-password/", invalid).status_code, 400)
        weak = self.post_public(
            "/api/v1/auth/reset-password/", self.reset_payload(password="weak")
        )
        self.assertEqual(weak.status_code, 400)
        self.assertIn("new_password", weak.json())
        now = datetime.now()
        with patch("django.contrib.auth.tokens.PasswordResetTokenGenerator._now", return_value=now):
            expired_payload = self.reset_payload()
        with patch(
            "django.contrib.auth.tokens.PasswordResetTokenGenerator._now",
            return_value=now + timedelta(seconds=3601),
        ):
            expired = self.post_public("/api/v1/auth/reset-password/", expired_payload)
        self.assertEqual(expired.status_code, 400)

    def login(self, client):
        return client.post(
            "/api/v1/auth/login/",
            {"username": self.user.username, "password": self.password},
            format="json", HTTP_X_CSRFTOKEN=self.csrf(client),
        )

    def test_reset_invalidates_authoritative_session(self):
        client = APIClient(enforce_csrf_checks=True)
        self.assertEqual(self.login(client).status_code, 200)
        self.assertTrue(ActiveUserSession.objects.filter(user=self.user).exists())
        self.user.refresh_from_db()
        reset = self.post_public("/api/v1/auth/reset-password/", self.reset_payload())
        self.assertEqual(reset.status_code, 204)
        self.assertFalse(ActiveUserSession.objects.filter(user=self.user).exists())
        self.assertEqual(client.get("/api/v1/auth/me/").status_code, 401)

    def test_authenticated_change_requires_current_password_and_logs_out(self):
        client = APIClient(enforce_csrf_checks=True)
        login = self.login(client)
        wrong = client.post(
            "/api/v1/auth/change-password/",
            {
                "current_password": "wrong",
                "new_password": self.replacement,
                "confirm_password": self.replacement,
            },
            format="json", HTTP_X_CSRFTOKEN=login.json()["csrf_token"],
        )
        self.assertEqual(wrong.status_code, 400)
        changed = client.post(
            "/api/v1/auth/change-password/",
            {
                "current_password": self.password,
                "new_password": self.replacement,
                "confirm_password": self.replacement,
            },
            format="json", HTTP_X_CSRFTOKEN=login.json()["csrf_token"],
        )
        self.assertEqual(changed.status_code, 204)
        self.assertFalse(ActiveUserSession.objects.filter(user=self.user).exists())
        self.assertEqual(client.get("/api/v1/auth/me/").status_code, 401)

    def test_change_cannot_target_another_user(self):
        other = self.make_staff("other", "other@example.com")
        client = APIClient(enforce_csrf_checks=True)
        login = self.login(client)
        response = client.post(
            "/api/v1/auth/change-password/",
            {
                "current_password": self.password,
                "new_password": self.replacement,
                "confirm_password": self.replacement,
                "user_id": other.pk,
            },
            format="json", HTTP_X_CSRFTOKEN=login.json()["csrf_token"],
        )
        self.assertEqual(response.status_code, 400)
        other.refresh_from_db()
        self.assertTrue(other.check_password(self.password))
