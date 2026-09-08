import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Vehicle

TEMP_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class VehiclePhotoTests(TestCase):
    password = "A-strong-test-password-42!"

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.client = APIClient()
        self.vehicle = Vehicle.objects.create(
            device_id="PHOTO-001", plate_number="PIC-001", display_name="Photo Vehicle"
        )
        user = get_user_model().objects.create_user(
            username="fleet-photo-manager", password=self.password, is_staff=True
        )
        StaffProfile.objects.create(user=user, role=StaffProfile.Role.FLEET_MANAGER)
        self.assertTrue(self.client.login(username=user.username, password=self.password))

    def photo(self, name="vehicle.jpg", content=b"jpeg-image"):
        return SimpleUploadedFile(name, content, content_type="image/jpeg")

    def test_vehicle_without_photo_has_null_url(self):
        response = self.client.get("/api/v1/vehicles/PHOTO-001/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["photo_url"])

    def test_authorized_upload_is_serialized_and_served(self):
        response = self.client.patch(
            "/api/v1/vehicles/PHOTO-001/",
            {"photo": self.photo(), "model_year": "2026", "passenger_capacity": "8"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["model_year"], 2026)
        self.assertEqual(response.json()["photo_url"], "/api/v1/vehicles/PHOTO-001/photo/")
        self.assertEqual(self.client.get(response.json()["photo_url"]).status_code, 200)
        live = self.client.get("/api/v1/fleet-live/vehicles/").json()["vehicles"][0]
        self.assertEqual(live["photo_url"], response.json()["photo_url"])

    def test_replacing_photo_removes_old_file(self):
        self.client.patch(
            "/api/v1/vehicles/PHOTO-001/", {"photo": self.photo()}, format="multipart"
        )
        self.vehicle.refresh_from_db()
        old_name = self.vehicle.photo.name
        storage = self.vehicle.photo.storage
        response = self.client.patch(
            "/api/v1/vehicles/PHOTO-001/",
            {"photo": self.photo("replacement.jpg", b"replacement")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(storage.exists(old_name))

    def test_invalid_photo_is_rejected(self):
        invalid = SimpleUploadedFile("vehicle.txt", b"not-image", content_type="text/plain")
        response = self.client.patch(
            "/api/v1/vehicles/PHOTO-001/", {"photo": invalid}, format="multipart"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("photo", response.json())
