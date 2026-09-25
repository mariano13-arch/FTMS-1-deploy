import time
from unittest.mock import patch

import pyotp
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import ActiveUserSession, StaffProfile, TwoFactorCredential
from accounts.two_factor import encrypt_secret


@override_settings(TWO_FACTOR_ENCRYPTION_KEY=Fernet.generate_key().decode())
class SessionSecurityTests(TestCase):
    password = "A-strong-test-password-42!"
    start = 1_700_000_000.0

    def setUp(self):
        cache.clear()
        self.user = self.create_staff("manager", StaffProfile.Role.DISPATCHER)

    def create_staff(self, username, role=None, **user_fields):
        user = get_user_model().objects.create_user(
            username=username,
            password=self.password,
            is_staff=True,
            **user_fields,
        )
        if role:
            StaffProfile.objects.create(user=user, role=role)
        return user

    def csrf(self, client):
        return client.get("/api/v1/auth/csrf/").json()["csrf_token"]

    def login(self, client, username="manager", at=None):
        token = self.csrf(client)
        with patch(
            "accounts.session_security._now_timestamp",
            return_value=self.start if at is None else at,
        ):
            return client.post(
                "/api/v1/auth/login/",
                {"username": username, "password": self.password},
                format="json",
                HTTP_X_CSRFTOKEN=token,
            )

    def get_me(self, client, at):
        with patch("accounts.session_security._now_timestamp", return_value=at):
            return client.get("/api/v1/auth/me/")

    def test_login_establishes_non_persistent_session_and_same_session_continues(self):
        client = APIClient(enforce_csrf_checks=True)
        response = self.login(client)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)
        self.assertEqual(response.cookies[settings.SESSION_COOKIE_NAME]["expires"], "")
        self.assertEqual(response.cookies[settings.SESSION_COOKIE_NAME]["max-age"], "")
        registration = ActiveUserSession.objects.get(user=self.user)
        self.assertEqual(registration.session_key, client.session.session_key)
        self.assertEqual(self.get_me(client, self.start + 1).status_code, 200)
        self.assertEqual(self.get_me(client, self.start + 2).status_code, 200)

    def test_second_completed_login_invalidates_first_and_stale_logout_is_safe(self):
        first = APIClient(enforce_csrf_checks=True)
        second = APIClient(enforce_csrf_checks=True)
        first_login = self.login(first)
        first_key = first.session.session_key
        second_login = self.login(second, at=self.start + 1)

        self.assertEqual(first_login.status_code, 200)
        self.assertEqual(second_login.status_code, 200)
        self.assertFalse(Session.objects.filter(session_key=first_key).exists())
        self.assertEqual(self.get_me(first, self.start + 2).status_code, 401)
        self.assertEqual(
            first.post(
                "/api/v1/auth/logout/",
                HTTP_X_CSRFTOKEN=first_login.json()["csrf_token"],
            ).status_code,
            401,
        )
        self.assertEqual(self.get_me(second, self.start + 2).status_code, 200)

    def test_password_stage_for_two_factor_does_not_replace_active_session(self):
        secret = "JBSWY3DPEHPK3PXP"
        TwoFactorCredential.objects.create(
            user=self.user,
            encrypted_secret=encrypt_secret(secret),
            is_enabled=True,
        )
        first = APIClient(enforce_csrf_checks=True)
        second = APIClient(enforce_csrf_checks=True)

        challenge_a = self.login(first).json()["challenge_token"]
        with patch("accounts.session_security._now_timestamp", return_value=self.start):
            completed_a = first.post(
                "/api/v1/auth/2fa/verify/",
                {
                    "challenge_token": challenge_a,
                    "method": "totp",
                    "code": pyotp.TOTP(secret).now(),
                },
                format="json",
                HTTP_X_CSRFTOKEN=self.csrf(first),
            )
        self.assertEqual(completed_a.status_code, 200)

        challenge_b = self.login(second, at=self.start + 1).json()["challenge_token"]
        self.assertEqual(self.get_me(first, self.start + 2).status_code, 200)

        with patch("accounts.session_security._now_timestamp", return_value=self.start + 3):
            completed_b = second.post(
                "/api/v1/auth/2fa/verify/",
                {
                    "challenge_token": challenge_b,
                    "method": "totp",
                    "code": pyotp.TOTP(secret).at(time.time() + 30),
                },
                format="json",
                HTTP_X_CSRFTOKEN=self.csrf(second),
            )
        self.assertEqual(completed_b.status_code, 200)
        self.assertEqual(self.get_me(first, self.start + 4).status_code, 401)
        self.assertEqual(self.get_me(second, self.start + 4).status_code, 200)

    @override_settings(FTMS_SESSION_IDLE_TIMEOUT_SECONDS=900)
    def test_idle_timeout_is_authoritative_and_background_requests_do_not_renew_it(self):
        client = APIClient(enforce_csrf_checks=True)
        self.login(client)

        self.assertEqual(self.get_me(client, self.start + 899).status_code, 200)
        expired = self.get_me(client, self.start + 900)
        self.assertEqual(expired.status_code, 401)
        self.assertIn("inactivity", expired.json()["detail"])
        self.assertFalse(ActiveUserSession.objects.filter(user=self.user).exists())

    @override_settings(FTMS_SESSION_IDLE_TIMEOUT_SECONDS=900)
    def test_meaningful_activity_uses_server_time_and_extends_only_idle_limit(self):
        client = APIClient(enforce_csrf_checks=True)
        login_response = self.login(client)
        with patch(
            "accounts.session_security._now_timestamp", return_value=self.start + 600
        ):
            activity = client.post(
                "/api/v1/auth/activity/",
                {},
                format="json",
                HTTP_X_CSRFTOKEN=login_response.json()["csrf_token"],
            )
        self.assertEqual(activity.status_code, 204)
        self.assertEqual(self.get_me(client, self.start + 1_499).status_code, 200)
        self.assertEqual(self.get_me(client, self.start + 1_500).status_code, 401)

    @override_settings(
        FTMS_SESSION_IDLE_TIMEOUT_SECONDS=30_000,
        FTMS_SESSION_ABSOLUTE_TIMEOUT_SECONDS=28_800,
    )
    def test_absolute_timeout_cannot_be_extended_by_activity(self):
        client = APIClient(enforce_csrf_checks=True)
        login_response = self.login(client)
        with patch(
            "accounts.session_security._now_timestamp", return_value=self.start + 28_799
        ):
            self.assertEqual(
                client.post(
                    "/api/v1/auth/activity/",
                    {},
                    format="json",
                    HTTP_X_CSRFTOKEN=login_response.json()["csrf_token"],
                ).status_code,
                204,
            )
        expired = self.get_me(client, self.start + 28_800)
        self.assertEqual(expired.status_code, 401)
        self.assertEqual(expired.json()["detail"], "Your session expired. Please sign in again.")

    def test_explicit_logout_unregisters_only_current_session(self):
        client = APIClient(enforce_csrf_checks=True)
        response = self.login(client)
        with patch(
            "accounts.session_security._now_timestamp", return_value=self.start + 1
        ):
            logged_out = client.post(
                "/api/v1/auth/logout/",
                HTTP_X_CSRFTOKEN=response.json()["csrf_token"],
            )
        self.assertEqual(logged_out.status_code, 204)
        self.assertFalse(ActiveUserSession.objects.filter(user=self.user).exists())
        self.assertEqual(client.get("/api/v1/auth/me/").status_code, 401)

    def test_supported_staff_account_types_use_session_controls(self):
        dispatcher = self.create_staff("dispatcher", StaffProfile.Role.DISPATCHER)
        fleet_staff = self.create_staff("fleet-staff", StaffProfile.Role.FLEET_STAFF)
        for username, user in (("dispatcher", dispatcher), ("fleet-staff", fleet_staff)):
            with self.subTest(username=username):
                client = APIClient(enforce_csrf_checks=True)
                self.assertEqual(self.login(client, username=username).status_code, 200)
                self.assertTrue(ActiveUserSession.objects.filter(user=user).exists())
