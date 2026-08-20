import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Driver, DriverDocument, VehicleDocument

TEMP_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class DriverApiTests(TestCase):
    password = "A-strong-test-password-42!"

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.client = APIClient()
        self.driver = Driver.objects.create(
            driver_code="DRV-001", first_name="Juan", last_name="Dela Cruz"
        )

    def user(self, role=None, superuser=False):
        user = get_user_model().objects.create_user(
            username=f"user-{get_user_model().objects.count()}",
            password=self.password,
            is_staff=True,
            is_superuser=superuser,
        )
        if role:
            StaffProfile.objects.create(user=user, role=role)
        return user

    def authenticate(self, user):
        self.assertTrue(self.client.login(username=user.username, password=self.password))

    def test_authentication_and_role_aware_registry_writes(self):
        url = "/api/v1/drivers/"
        self.assertEqual(self.client.get(url).status_code, 401)
        self.authenticate(self.user(StaffProfile.Role.DISPATCHER))
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(f"{url}{self.driver.pk}/").status_code, 200)
        self.assertEqual(self.client.post(url, {}, format="multipart").status_code, 403)
        self.client.logout()
        self.authenticate(self.user(StaffProfile.Role.FLEET_MANAGER))
        self.assertEqual(
            self.client.patch(
                f"{url}{self.driver.pk}/",
                {"contact_number": "09170000000"},
                format="multipart",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.patch(
                f"{url}{self.driver.pk}/",
                {"employment_status": "ON_LEAVE"},
                format="multipart",
            ).status_code,
            400,
        )
        self.assertEqual(self.client.post(url, {}, format="multipart").status_code, 403)
        self.client.logout()
        self.authenticate(self.user(superuser=True))
        response = self.client.post(
            url,
            {
                "driver_code": "DRV-002",
                "first_name": "Maria",
                "last_name": "Santos",
                "employment_status": "ACTIVE",
                "external_hr_id": "HR-002",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["external_hr_id"], "HR-002")
        created = Driver.objects.get(driver_code="DRV-002")
        self.assertEqual(response.json()["linked_user"], created.linked_user_id)
        self.assertEqual(created.linked_user.username, "DRV-002")

    def test_exact_eligibility_contract_and_honest_safety_contract(self):
        today = timezone.localdate()
        cases = [
            (
                {
                    "license_number": "N01",
                    "license_expiry_date": today,
                    "medical_certificate_expiry_date": today,
                },
                "ELIGIBLE",
            ),
            ({}, "RESTRICTED"),
            (
                {"license_number": "N01", "license_expiry_date": today - timedelta(days=1)},
                "NOT_ELIGIBLE",
            ),
            ({"medical_certificate_expiry_date": today - timedelta(days=1)}, "NOT_ELIGIBLE"),
            ({"employment_status": "ON_LEAVE"}, "NOT_ELIGIBLE"),
            ({"employment_status": "SUSPENDED"}, "NOT_ELIGIBLE"),
            ({"employment_status": "TERMINATED"}, "NOT_ELIGIBLE"),
        ]
        self.authenticate(self.user(StaffProfile.Role.DISPATCHER))
        for index, (values, expected) in enumerate(cases):
            candidate = Driver.objects.create(
                driver_code=f"CASE-{index}", first_name="Test", last_name=str(index), **values
            )
            data = self.client.get(f"/api/v1/drivers/{candidate.pk}/").json()
            self.assertEqual(data["eligibility_status"], expected)
            self.assertIsNone(data["safety_score"])
            self.assertEqual(data["safety_score_status"], "NOT_SCORED")
        restricted = self.client.get(f"/api/v1/drivers/{self.driver.pk}/").json()
        self.assertIn("Driver license number is missing", restricted["eligibility_reasons"])

    def test_documents_are_private_scoped_validated_and_role_protected(self):
        url = f"/api/v1/drivers/{self.driver.pk}/documents/"
        self.authenticate(self.user(StaffProfile.Role.DISPATCHER))
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {}, format="multipart").status_code, 403)
        self.client.logout()
        self.authenticate(self.user(StaffProfile.Role.FLEET_MANAGER))
        payload = {
            "document_type": "DRIVER_LICENSE",
            "title": "Driver license",
            "file": SimpleUploadedFile("license.pdf", b"%PDF test", "application/pdf"),
        }
        response = self.client.post(url, payload, format="multipart")
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("file", response.json())
        self.assertNotIn("driver_documents/", str(response.json()))
        self.assertEqual(self.client.get(response.json()["download_url"]).status_code, 200)
        self.assertEqual(DriverDocument.objects.count(), 1)
        self.assertEqual(VehicleDocument.objects.count(), 0)
        invalid = {
            **payload,
            "file": SimpleUploadedFile("bad.exe", b"x", "application/octet-stream"),
        }
        self.assertEqual(self.client.post(url, invalid, format="multipart").status_code, 400)
        large = {
            **payload,
            "file": SimpleUploadedFile(
                "large.pdf", b"x" * (5 * 1024 * 1024 + 1), "application/pdf"
            ),
        }
        self.assertEqual(self.client.post(url, large, format="multipart").status_code, 400)
