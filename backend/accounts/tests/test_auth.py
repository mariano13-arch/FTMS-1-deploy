from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile


class AuthenticationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.password = "A-strong-test-password-42!"
        self.user = get_user_model().objects.create_user(
            username="manager", password=self.password, is_staff=True, first_name="Fleet",
            last_name="Manager",
        )
        StaffProfile.objects.create(
            user=self.user, role=StaffProfile.Role.FLEET_MANAGER
        )
        self.client = APIClient(enforce_csrf_checks=True)

    def token(self):
        response = self.client.get("/api/v1/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)
        return response.json()["csrf_token"]

    def test_csrf_bootstrap_and_login_rotation(self):
        before = self.token()
        response = self.client.post(
            "/api/v1/auth/login/",
            {"username": "manager", "password": self.password},
            format="json", HTTP_X_CSRFTOKEN=before,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["role"], "FLEET_MANAGER")
        self.assertNotEqual(response.json()["csrf_token"], before)
        self.assertIn("sessionid", response.cookies)

    def test_login_requires_csrf_and_strict_payload(self):
        self.assertEqual(
            self.client.post("/api/v1/auth/login/", {}, format="json").status_code, 403
        )
        token = self.token()
        response = self.client.post(
            "/api/v1/auth/login/",
            {"username": "manager", "password": self.password, "extra": True},
            format="json", HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 400)

    def test_login_rejects_non_object_missing_null_and_non_string_fields(self):
        token = self.token()
        invalid_payloads = [
            [], None, {}, {"username": None, "password": self.password},
            {"username": 1, "password": self.password},
            {"username": True, "password": self.password},
            {"username": {}, "password": self.password},
            {"username": [], "password": self.password},
            {"username": "manager", "password": 1},
            {"username": "manager", "password": False},
            {"username": "manager", "password": None},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                cache.clear()
                response = self.client.post(
                    "/api/v1/auth/login/", payload,
                    format="json", HTTP_X_CSRFTOKEN=token,
                )
                self.assertEqual(response.status_code, 400)

    def test_generic_denial_for_unauthorized_accounts(self):
        token = self.token()
        for username, kwargs in [
            ("invalid", {}),
            ("inactive", {"is_staff": True, "is_active": False}),
            ("nonstaff", {}),
            ("profileless", {"is_staff": True}),
        ]:
            if username != "invalid":
                get_user_model().objects.create_user(
                    username=username, password=self.password, **kwargs
                )
            response = self.client.post(
                "/api/v1/auth/login/",
                {"username": username, "password": self.password},
                format="json", HTTP_X_CSRFTOKEN=token,
            )
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json(), {"detail": "Invalid credentials."})

    def test_me_and_csrf_logout(self):
        token = self.token()
        login_response = self.client.post(
            "/api/v1/auth/login/",
            {"username": "manager", "password": self.password},
            format="json", HTTP_X_CSRFTOKEN=token,
        )
        rotated = login_response.json()["csrf_token"]
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/auth/logout/").status_code, 403)
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/logout/", HTTP_X_CSRFTOKEN=rotated
            ).status_code,
            204,
        )
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)

    def test_login_throttle(self):
        token = self.token()
        for expected in (401, 401, 401, 401, 401, 429):
            response = self.client.post(
                "/api/v1/auth/login/",
                {"username": "wrong", "password": "wrong"},
                format="json", HTTP_X_CSRFTOKEN=token,
            )
            self.assertEqual(response.status_code, expected)
