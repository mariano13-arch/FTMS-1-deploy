import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pyotp
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import StaffProfile, TwoFactorCredential, TwoFactorRecoveryCode
from accounts.two_factor import (
    CHALLENGE_MAX_ATTEMPTS,
    ChallengeCacheUnavailable,
    claim_challenge,
    encrypt_secret,
    issue_recovery_codes,
    load_challenge,
    release_challenge_claim,
)
from fleet.models import Driver


@override_settings(TWO_FACTOR_ENCRYPTION_KEY=Fernet.generate_key().decode())
class TwoFactorAuthenticationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.password = "A-strong-test-password-42!"
        self.user = get_user_model().objects.create_user(
            username="manager", password=self.password, is_staff=True
        )
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.FLEET_MANAGER)
        self.client = APIClient(enforce_csrf_checks=True)

    def csrf(self, client=None):
        client = client or self.client
        return client.get("/api/v1/auth/csrf/").json()["csrf_token"]

    def password_login(self, client=None):
        client = client or self.client
        return client.post(
            "/api/v1/auth/login/",
            {"username": self.user.username, "password": self.password},
            format="json", HTTP_X_CSRFTOKEN=self.csrf(client),
        )

    def enabled_credential(self, secret="JBSWY3DPEHPK3PXP"):
        return TwoFactorCredential.objects.create(
            user=self.user, encrypted_secret=encrypt_secret(secret), is_enabled=True
        ), secret

    def challenge(self):
        response = self.password_login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["two_factor_required"], True)
        self.assertNotIn("sessionid", response.cookies)
        return response.json()["challenge_token"]

    def verify(self, challenge, method, code):
        return self.client.post(
            "/api/v1/auth/2fa/verify/",
            {"challenge_token": challenge, "method": method, "code": code},
            format="json", HTTP_X_CSRFTOKEN=self.csrf(),
        )

    def test_password_only_staff_login_remains_authenticated(self):
        response = self.password_login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["username"], self.user.username)
        self.assertIn("sessionid", response.cookies)

    def test_enabled_credential_requires_opaque_challenge_and_wrong_password_has_none(self):
        self.enabled_credential()
        response = self.password_login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"two_factor_required", "challenge_token"})
        self.assertGreaterEqual(len(response.json()["challenge_token"]), 40)
        self.assertNotIn("sessionid", response.cookies)
        bad = self.client.post(
            "/api/v1/auth/login/",
            {"username": self.user.username, "password": "wrong"},
            format="json", HTTP_X_CSRFTOKEN=self.csrf(),
        )
        self.assertEqual(bad.status_code, 401)
        self.assertNotIn("challenge_token", bad.json())

    def test_password_phase_has_no_staff_session_until_second_factor_succeeds(self):
        _, secret = self.enabled_credential()
        challenge = self.challenge()
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)
        self.assertEqual(
            self.verify(challenge, "totp", pyotp.TOTP(secret).now()).status_code,
            200,
        )
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)

    def test_totp_login_clock_window_replay_and_single_use_challenge(self):
        credential, secret = self.enabled_credential()
        challenge = self.challenge()
        previous_code = pyotp.TOTP(secret).at(time.time() - 30)
        response = self.verify(challenge, "totp", previous_code)
        self.assertEqual(response.status_code, 200)
        self.assertIn("sessionid", response.cookies)
        credential.refresh_from_db()
        self.assertIsNotNone(credential.last_used_time_step)
        replay = self.verify(challenge, "totp", previous_code)
        self.assertEqual(replay.status_code, 401)
        second_challenge = self.challenge()
        current_code = pyotp.TOTP(secret).now()
        self.assertEqual(self.verify(second_challenge, "totp", current_code).status_code, 200)
        reused_challenge = self.verify(second_challenge, "totp", pyotp.TOTP(secret).now())
        self.assertEqual(reused_challenge.status_code, 401)

    def test_expired_and_exhausted_challenge_fail_closed(self):
        self.enabled_credential()
        challenge = self.challenge()
        with patch("accounts.two_factor.time.time", return_value=time.time() + 301):
            self.assertIsNone(load_challenge(challenge))
        self.assertEqual(self.verify(challenge, "totp", "000000").status_code, 401)
        challenge = self.challenge()
        for _ in range(CHALLENGE_MAX_ATTEMPTS):
            response = self.verify(challenge, "totp", "000000")
            self.assertEqual(response.status_code, 401)
        self.assertIsNone(load_challenge(challenge))

    def test_challenge_claim_is_atomic_for_concurrent_verifiers(self):
        self.enabled_credential()
        challenge = self.challenge()
        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = list(executor.map(lambda _: claim_challenge(challenge), range(2)))
        self.assertEqual(sum(claim is not None for claim in claims), 1)
        release_challenge_claim(challenge, next(claim for claim in claims if claim))

    def test_verify_requires_csrf_and_applies_its_own_throttle(self):
        self.enabled_credential()
        challenge = self.challenge()
        csrf_rejected = self.client.post(
            "/api/v1/auth/2fa/verify/",
            {"challenge_token": challenge, "method": "totp", "code": "000000"},
            format="json",
        )
        self.assertEqual(csrf_rejected.status_code, 403)
        for _ in range(10):
            self.verify(challenge, "totp", "000000")
        self.assertEqual(self.verify(challenge, "totp", "000000").status_code, 429)

    def test_recovery_codes_are_hashed_one_time_and_complete_login(self):
        credential, _ = self.enabled_credential()
        recovery_codes = issue_recovery_codes(credential)
        stored = TwoFactorRecoveryCode.objects.filter(credential=credential).first()
        self.assertNotIn(recovery_codes[0], stored.code_hash)
        challenge = self.challenge()
        self.assertEqual(self.verify(challenge, "recovery", recovery_codes[0]).status_code, 200)
        stored.refresh_from_db()
        self.assertIsNotNone(stored.used_at)
        new_challenge = self.challenge()
        self.assertEqual(self.verify(new_challenge, "recovery", recovery_codes[0]).status_code, 401)

    def test_authenticated_setup_confirm_status_and_encrypted_secret(self):
        login = self.password_login()
        token = login.json()["csrf_token"]
        setup = self.client.post(
            "/api/v1/auth/2fa/setup/", {}, format="json", HTTP_X_CSRFTOKEN=token
        )
        self.assertEqual(setup.status_code, 200)
        setup_data = setup.json()
        self.assertIn("otpauth://totp/FTMS:", setup_data["provisioning_uri"])
        credential = TwoFactorCredential.objects.get(user=self.user)
        self.assertFalse(credential.is_enabled)
        self.assertNotEqual(credential.encrypted_secret, setup_data["manual_setup_key"])
        invalid = self.client.post(
            "/api/v1/auth/2fa/confirm/",
            {"code": "000000"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(invalid.status_code, 400)
        credential.refresh_from_db()
        self.assertFalse(credential.is_enabled)
        code = pyotp.TOTP(setup_data["manual_setup_key"]).now()
        confirmed = self.client.post(
            "/api/v1/auth/2fa/confirm/",
            {"code": code},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(len(confirmed.json()["recovery_codes"]), 8)
        status_response = self.client.get("/api/v1/auth/2fa/status/")
        self.assertEqual(
            set(status_response.json()),
            {"enabled", "recovery_codes_remaining", "enabled_at"},
        )
        self.assertEqual(status_response.json()["recovery_codes_remaining"], 8)
        duplicate = self.client.post(
            "/api/v1/auth/2fa/setup/", {}, format="json", HTTP_X_CSRFTOKEN=token
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_missing_encryption_key_fails_closed_and_nonstaff_is_denied(self):
        self.enabled_credential()
        with override_settings(TWO_FACTOR_ENCRYPTION_KEY=""):
            self.assertEqual(self.password_login().status_code, 503)
        with override_settings(TWO_FACTOR_ENCRYPTION_KEY="invalid-key"):
            self.assertEqual(self.password_login().status_code, 503)
        nonstaff = get_user_model().objects.create_user(
            username="not-staff", password=self.password
        )
        other_client = APIClient()
        other_client.force_authenticate(nonstaff)
        self.assertEqual(other_client.get("/api/v1/auth/2fa/status/").status_code, 403)

    def test_cache_outages_are_controlled_and_never_create_a_session(self):
        self.enabled_credential()
        with patch(
            "accounts.views.create_challenge", side_effect=ChallengeCacheUnavailable
        ):
            login_response = self.password_login()
        self.assertEqual(login_response.status_code, 503)
        self.assertNotIn("sessionid", login_response.cookies)
        challenge = self.challenge()
        with patch(
            "accounts.views.load_challenge", side_effect=ChallengeCacheUnavailable
        ):
            verify_response = self.verify(challenge, "totp", "000000")
        self.assertEqual(verify_response.status_code, 503)
        self.assertNotIn("sessionid", verify_response.cookies)

    def test_adjacent_totp_step_is_recorded_and_older_step_is_rejected(self):
        credential, secret = self.enabled_credential()
        challenge = self.challenge()
        now = 1_700_000_100
        next_step = pyotp.TOTP(secret).at(now + 30)
        with patch("accounts.two_factor.time.time", return_value=now):
            self.assertEqual(self.verify(challenge, "totp", next_step).status_code, 200)
        credential.refresh_from_db()
        self.assertEqual(credential.last_used_time_step, (now + 30) // 30)
        older_challenge = self.challenge()
        current_step = pyotp.TOTP(secret).at(now)
        with patch("accounts.two_factor.time.time", return_value=now):
            self.assertEqual(
                self.verify(older_challenge, "totp", current_step).status_code,
                401,
            )

    def test_disable_requires_current_password_and_second_factor(self):
        credential, secret = self.enabled_credential()
        self.client.force_login(self.user)
        token = self.csrf()
        rejected = self.client.post(
            "/api/v1/auth/2fa/disable/",
            {"current_password": "wrong", "method": "totp", "code": pyotp.TOTP(secret).now()},
            format="json", HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(rejected.status_code, 400)
        accepted = self.client.post(
            "/api/v1/auth/2fa/disable/",
            {"current_password": self.password, "method": "totp", "code": pyotp.TOTP(secret).now()},
            format="json", HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(accepted.status_code, 204)
        self.assertFalse(TwoFactorCredential.objects.filter(pk=credential.pk).exists())
        self.assertFalse(TwoFactorRecoveryCode.objects.filter(credential_id=credential.pk).exists())

    def test_recovery_code_used_for_disable_cannot_be_reused(self):
        credential, _ = self.enabled_credential()
        recovery_code = issue_recovery_codes(credential)[0]
        self.client.force_login(self.user)
        token = self.csrf()
        response = self.client.post(
            "/api/v1/auth/2fa/disable/",
            {
                "current_password": self.password,
                "method": "recovery",
                "code": recovery_code,
            },
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 204)
        retry = self.client.post(
            "/api/v1/auth/2fa/disable/",
            {
                "current_password": self.password,
                "method": "recovery",
                "code": recovery_code,
            },
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(retry.status_code, 400)

    def test_dual_role_user_cannot_bypass_staff_two_factor_through_driver_login(self):
        _, secret = self.enabled_credential()
        Driver.objects.create(
            driver_code="DRV-DUAL-001",
            first_name="Dual",
            last_name="Role",
            linked_user=self.user,
        )
        driver_client = APIClient(enforce_csrf_checks=True)
        driver_token = driver_client.get("/api/v1/driver-auth/csrf/").json()["csrf_token"]
        driver_login = driver_client.post(
            "/api/v1/driver-auth/login/",
            {"username": self.user.username, "password": self.password},
            format="json",
            HTTP_X_CSRFTOKEN=driver_token,
        )
        self.assertEqual(driver_login.status_code, 401)
        self.assertNotIn("sessionid", driver_login.cookies)
        challenge = self.challenge()
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)
        self.assertEqual(
            self.verify(challenge, "totp", pyotp.TOTP(secret).now()).status_code,
            200,
        )
