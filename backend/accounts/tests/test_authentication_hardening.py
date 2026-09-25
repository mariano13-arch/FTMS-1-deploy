from datetime import timedelta
from unittest.mock import patch

import pyotp
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import (
    get_default_password_validators,
    validate_password,
)
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import (
    ActiveUserSession,
    StaffLoginSecurityState,
    StaffProfile,
    TwoFactorCredential,
)
from accounts.throttles import PasswordResetCompletionThrottle


@override_settings(TWO_FACTOR_ENCRYPTION_KEY=Fernet.generate_key().decode())
class AuthenticationHardeningTests(TestCase):
    password = "A-strong-test-password-42!"

    def setUp(self):
        cache.clear()

    def make_staff(self, username, role):
        user = get_user_model().objects.create_user(
            username=username, password=self.password, is_staff=True
        )
        StaffProfile.objects.create(user=user, role=role)
        return user

    def csrf(self, client):
        return client.get("/api/v1/auth/csrf/").json()["csrf_token"]

    def login(self, client, username, password=None):
        return client.post(
            "/api/v1/auth/login/",
            {"username": username, "password": password or self.password},
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf(client),
        )

    def confirm_enrollment(self, client, login_response):
        body = login_response.json()
        return client.post(
            "/api/v1/auth/2fa/enrollment/confirm/",
            {
                "challenge_token": body["challenge_token"],
                "code": pyotp.TOTP(body["setup"]["manual_setup_key"]).now(),
            },
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf(client),
        )

    def test_required_roles_enroll_before_operational_session(self):
        for role in (StaffProfile.Role.FLEET_ADMIN, StaffProfile.Role.FLEET_MANAGER):
            with self.subTest(role=role):
                user = self.make_staff(role.lower(), role)
                client = APIClient(enforce_csrf_checks=True)
                login_response = self.login(client, user.username)

                self.assertEqual(login_response.status_code, 200)
                self.assertTrue(login_response.json()["mfa_enrollment_required"])
                self.assertNotIn("sessionid", login_response.cookies)
                self.assertEqual(client.get("/api/v1/auth/me/").status_code, 401)

                confirmed = self.confirm_enrollment(client, login_response)
                self.assertEqual(confirmed.status_code, 200)
                self.assertIn("sessionid", confirmed.cookies)
                self.assertEqual(len(confirmed.json()["recovery_codes"]), 8)
                self.assertTrue(ActiveUserSession.objects.filter(user=user).exists())

                credential = TwoFactorCredential.objects.get(user=user)
                self.assertTrue(credential.is_enabled)
                next_client = APIClient(enforce_csrf_checks=True)
                future_login = self.login(next_client, user.username)
                self.assertTrue(future_login.json()["two_factor_required"])
                self.assertNotIn("sessionid", future_login.cookies)

    def test_required_roles_cannot_disable_mfa(self):
        for role in (StaffProfile.Role.FLEET_ADMIN, StaffProfile.Role.FLEET_MANAGER):
            with self.subTest(role=role):
                user = self.make_staff(role.lower(), role)
                client = APIClient(enforce_csrf_checks=True)
                confirmed = self.confirm_enrollment(client, self.login(client, user.username))
                response = client.post(
                    "/api/v1/auth/2fa/disable/",
                    {
                        "current_password": self.password,
                        "method": "recovery",
                        "code": confirmed.json()["recovery_codes"][0],
                    },
                    format="json",
                    HTTP_X_CSRFTOKEN=confirmed.json()["csrf_token"],
                )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["detail"], "MFA is required for this role.")
                self.assertTrue(TwoFactorCredential.objects.get(user=user).is_enabled)

    def test_nonmandatory_roles_keep_password_only_login(self):
        for role in (StaffProfile.Role.DISPATCHER, StaffProfile.Role.FLEET_STAFF):
            with self.subTest(role=role):
                user = self.make_staff(role.lower(), role)
                response = self.login(APIClient(enforce_csrf_checks=True), user.username)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["user"]["role"], role)

    @patch("accounts.throttles.LoginThrottle.get_rate", return_value="1000/min")
    def test_fifth_failure_locks_and_expired_lock_allows_login(self, _rate):
        user = self.make_staff("locked-manager", StaffProfile.Role.FLEET_MANAGER)
        client = APIClient(enforce_csrf_checks=True)
        for _ in range(4):
            response = self.login(client, user.username, "incorrect-password")
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json(), {"detail": "Invalid credentials."})

        fifth = self.login(client, user.username, "incorrect-password")
        self.assertEqual(fifth.status_code, 401)
        self.assertEqual(fifth.json()["code"], "temporarily_locked")
        self.assertIn("Too many failed sign-in attempts.", fifth.json()["detail"])
        self.assertGreaterEqual(fifth.json()["retry_after_seconds"], 0)
        self.assertLessEqual(fifth.json()["retry_after_seconds"], 900)

        state = StaffLoginSecurityState.objects.get(user=user)
        self.assertEqual(state.failed_login_attempts, 5)
        self.assertGreater(state.locked_until, timezone.now())
        locked = self.login(client, user.username)
        self.assertEqual(locked.status_code, 401)
        self.assertEqual(locked.json()["code"], "temporarily_locked")
        self.assertIn("Too many failed sign-in attempts.", locked.json()["detail"])
        self.assertGreaterEqual(locked.json()["retry_after_seconds"], 0)
        self.assertLessEqual(locked.json()["retry_after_seconds"], 900)

        state.locked_until = timezone.now() - timedelta(seconds=1)
        state.save(update_fields=("locked_until", "updated_at"))
        allowed = self.login(client, user.username)
        self.assertEqual(allowed.status_code, 200)
        self.assertTrue(allowed.json()["mfa_enrollment_required"])
        state.refresh_from_db()
        self.assertEqual(state.failed_login_attempts, 0)
        self.assertIsNone(state.locked_until)

    @patch("accounts.throttles.LoginThrottle.get_rate", return_value="1000/min")
    def test_success_resets_failures_and_unknown_user_is_generic(self, _rate):
        user = self.make_staff("dispatcher", StaffProfile.Role.DISPATCHER)
        client = APIClient(enforce_csrf_checks=True)
        self.assertEqual(self.login(client, user.username, "wrong").status_code, 401)
        self.assertEqual(self.login(client, user.username).status_code, 200)
        state = StaffLoginSecurityState.objects.get(user=user)
        self.assertEqual(state.failed_login_attempts, 0)
        self.assertIsNone(state.locked_until)

        unknown = self.login(APIClient(enforce_csrf_checks=True), "unknown", "wrong")
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(unknown.json(), {"detail": "Invalid credentials."})
        self.assertFalse(StaffLoginSecurityState.objects.filter(user__username="unknown").exists())

    def test_password_policy_and_reset_completion_throttle(self):
        user = self.make_staff("password-policy", StaffProfile.Role.DISPATCHER)
        with self.assertRaises(ValidationError):
            validate_password("short-pass", user=user)
        with self.assertRaises(ValidationError):
            validate_password("1234567890123456", user=user)
        validate_password("a sufficiently long passphrase", user=user)
        validator_names = {
            type(validator).__name__ for validator in get_default_password_validators()
        }
        self.assertIn("CommonPasswordValidator", validator_names)
        self.assertIn("NumericPasswordValidator", validator_names)
        self.assertIn("UserAttributeSimilarityValidator", validator_names)
        self.assertEqual(PasswordResetCompletionThrottle.scope, "password_reset_completion")
