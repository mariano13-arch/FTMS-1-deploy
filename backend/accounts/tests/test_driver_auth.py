from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.test import TestCase
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Driver


class DriverAuthenticationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.password = "A-strong-test-password-42!"
        self.driver_user = get_user_model().objects.create_user(
            username="mobile-driver",
            password=self.password,
            first_name="Account",
            last_name="Name",
        )
        self.driver = Driver.objects.create(
            driver_code="DRV-MOBILE-001",
            first_name="Maria",
            middle_name="Santos",
            last_name="Reyes",
            email="maria.driver@example.test",
            linked_user=self.driver_user,
            license_number="N01-23-456789",
            license_expiry_date=date(2030, 6, 30),
            medical_certificate_expiry_date=date(2027, 6, 30),
        )
        self.client = APIClient(enforce_csrf_checks=True)

    def token(self):
        response = self.client.get("/api/v1/driver-auth/csrf/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)
        return response.json()["csrf_token"]

    def login(self, username="mobile-driver", password=None):
        return self.client.post(
            "/api/v1/driver-auth/login/",
            {"username": username, "password": password or self.password},
            format="json",
            HTTP_X_CSRFTOKEN=self.token(),
        )

    def test_linked_driver_can_login_and_receives_minimum_identity(self):
        response = self.login()

        self.assertEqual(response.status_code, 200)
        self.assertIn("sessionid", response.cookies)
        self.assertEqual(
            response.json()["driver"],
            {
                "user_id": self.driver_user.pk,
                "username": "mobile-driver",
                "driver_id": self.driver.pk,
                "driver_code": "DRV-MOBILE-001",
                "display_name": "Maria Santos Reyes",
                "email": "maria.driver@example.test",
                "employment_status": "ACTIVE",
                "employment_status_label": "Active",
                "license_number": "N01-23-456789",
                "license_expiry_date": "2030-06-30",
                "medical_certificate_expiry_date": "2027-06-30",
                "eligibility_status": "ELIGIBLE",
                "eligibility_reasons": [],
            },
        )
        self.assertNotIn("external_hr_id", response.json()["driver"])
        self.assertNotIn("contact_number", response.json()["driver"])
        self.assertNotIn("linked_user", response.json()["driver"])

    def test_wrong_password_is_rejected(self):
        response = self.login(password="incorrect-password")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Invalid credentials."})
        self.assertNotIn("sessionid", response.cookies)

    def test_unlinked_ordinary_user_is_rejected(self):
        get_user_model().objects.create_user(
            username="ordinary-user", password=self.password
        )

        response = self.login(username="ordinary-user")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Invalid credentials."})

    def test_staff_only_user_is_rejected_by_driver_login(self):
        staff_user = get_user_model().objects.create_user(
            username="staff-only", password=self.password, is_staff=True
        )
        StaffProfile.objects.create(
            user=staff_user, role=StaffProfile.Role.FLEET_MANAGER
        )

        response = self.login(username="staff-only")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Invalid credentials."})

    def test_staff_or_superuser_linked_to_a_driver_cannot_use_driver_auth(self):
        for username, is_superuser in (("staff-driver", False), ("super-driver", True)):
            with self.subTest(username=username):
                user = get_user_model().objects.create_user(
                    username=username,
                    password=self.password,
                    is_staff=True,
                    is_superuser=is_superuser,
                )
                if not is_superuser:
                    StaffProfile.objects.create(
                        user=user, role=StaffProfile.Role.FLEET_MANAGER
                    )
                Driver.objects.create(
                    driver_code=f"DRV-{username.upper()}",
                    first_name="Blocked",
                    last_name="Identity",
                    linked_user=user,
                )
                self.assertEqual(self.login(username=username).status_code, 401)
                self.client.force_login(user)
                self.assertEqual(
                    self.client.get("/api/v1/driver-auth/me/").status_code,
                    403,
                )
                self.client.logout()

    def test_staff_or_superuser_linked_to_driver_cannot_setup_driver_password(self):
        for username, is_superuser in (("staff-setup", False), ("super-setup", True)):
            with self.subTest(username=username):
                user = get_user_model().objects.create_user(
                    username=username,
                    is_staff=True,
                    is_superuser=is_superuser,
                )
                user.set_unusable_password()
                user.save(update_fields=["password"])
                if not is_superuser:
                    StaffProfile.objects.create(
                        user=user, role=StaffProfile.Role.FLEET_MANAGER
                    )
                Driver.objects.create(
                    driver_code=f"DRV-{username.upper()}",
                    first_name="Blocked",
                    last_name="Setup",
                    linked_user=user,
                )
                response = self.client.post(
                    "/api/v1/driver-auth/setup-password/",
                    {
                        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                        "token": default_token_generator.make_token(user),
                        "new_password": self.password,
                        "confirm_password": self.password,
                    },
                    format="json",
                    HTTP_X_CSRFTOKEN=self.token(),
                )
                self.assertEqual(response.status_code, 400)

    def test_me_returns_linked_driver_identity(self):
        self.assertEqual(self.login().status_code, 200)

        response = self.client.get("/api/v1/driver-auth/me/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["driver"]["driver_id"], self.driver.pk)
        self.assertEqual(response.json()["driver"]["driver_code"], "DRV-MOBILE-001")
        self.assertEqual(response.json()["driver"]["display_name"], "Maria Santos Reyes")
        self.assertEqual(response.json()["driver"]["eligibility_status"], "ELIGIBLE")
        self.assertEqual(response.json()["driver"]["license_expiry_date"], "2030-06-30")

    def test_unauthenticated_me_is_rejected(self):
        response = self.client.get("/api/v1/driver-auth/me/")

        self.assertEqual(response.status_code, 401)

    def test_logout_invalidates_driver_session(self):
        login_response = self.login()
        rotated_token = login_response.json()["csrf_token"]

        response = self.client.post(
            "/api/v1/driver-auth/logout/", HTTP_X_CSRFTOKEN=rotated_token
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get("/api/v1/driver-auth/me/").status_code, 401)

    def test_existing_staff_login_remains_available_to_staff(self):
        staff_user = get_user_model().objects.create_user(
            username="fleet-manager", password=self.password, is_staff=True
        )
        StaffProfile.objects.create(
            user=staff_user, role=StaffProfile.Role.FLEET_MANAGER
        )
        token = self.client.get("/api/v1/auth/csrf/").json()["csrf_token"]

        response = self.client.post(
            "/api/v1/auth/login/",
            {"username": "fleet-manager", "password": self.password},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["role"], "FLEET_MANAGER")
