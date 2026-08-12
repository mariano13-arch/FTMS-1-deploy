import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Vehicle, VehicleDocument

TEMP_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class VehicleDocumentTests(TestCase):
    password = "A-strong-test-password-42!"

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.client = APIClient()
        self.vehicle = Vehicle.objects.create(
            device_id="DOC-001", plate_number="DOC-001", display_name="Document Van"
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

    def upload(self, **overrides):
        payload = {
            "document_type": "INSURANCE",
            "title": "Insurance certificate",
            "reference_number": "INS-001",
            "file": SimpleUploadedFile("insurance.pdf", b"%PDF test", "application/pdf"),
            **overrides,
        }
        return self.client.post(
            "/api/v1/vehicles/DOC-001/documents/", payload, format="multipart"
        )

    def test_anonymous_rejected_and_dispatcher_reads_but_cannot_upload(self):
        self.assertEqual(self.client.get("/api/v1/vehicles/DOC-001/documents/").status_code, 401)
        self.authenticate(self.user(StaffProfile.Role.DISPATCHER))
        self.assertEqual(self.client.get("/api/v1/vehicles/DOC-001/documents/").status_code, 200)
        self.assertEqual(self.upload().status_code, 403)

    def test_manager_uploads_with_server_owned_identity_and_downloads(self):
        manager = self.user(StaffProfile.Role.FLEET_MANAGER)
        self.authenticate(manager)
        response = self.upload(uploaded_by=999)
        self.assertEqual(response.status_code, 400)
        response = self.upload()
        self.assertEqual(response.status_code, 201)
        document = VehicleDocument.objects.get()
        self.assertEqual(document.uploaded_by, manager)
        self.assertNotIn("file", response.json())
        self.assertEqual(
            self.client.get(response.json()["download_url"]).status_code, 200
        )

    def test_superadmin_updates_metadata_delete_unsupported_and_vehicle_isolated(self):
        self.authenticate(self.user(superuser=True))
        document_id = self.upload().json()["id"]
        detail = f"/api/v1/vehicles/DOC-001/documents/{document_id}/"
        self.assertEqual(
            self.client.patch(detail, {"title": "Updated"}, format="multipart").status_code,
            200,
        )
        self.assertEqual(self.client.delete(detail).status_code, 405)
        other = Vehicle.objects.create(
            device_id="DOC-002", plate_number="DOC-002", display_name="Other"
        )
        self.assertEqual(
            self.client.get(
                f"/api/v1/vehicles/{other.device_id}/documents/{document_id}/"
            ).status_code,
            404,
        )

    def test_file_type_size_invalid_vehicle_and_pagination(self):
        self.authenticate(self.user(StaffProfile.Role.FLEET_MANAGER))
        self.assertEqual(
            self.upload(
                file=SimpleUploadedFile("unsafe.exe", b"data", "application/octet-stream")
            ).status_code,
            400,
        )
        self.assertEqual(
            self.upload(
                file=SimpleUploadedFile(
                    "large.pdf",
                    b"x" * (5 * 1024 * 1024 + 1),
                    "application/pdf",
                )
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/vehicles/UNKNOWN/documents/", {}, format="multipart"
            ).status_code,
            404,
        )
        for index in range(11):
            self.assertEqual(self.upload(title=f"Document {index}").status_code, 201)
        page = self.client.get("/api/v1/vehicles/DOC-001/documents/").json()
        self.assertEqual(page["count"], 11)
        self.assertEqual(len(page["results"]), 10)
        self.assertIsNotNone(page["next"])


class ExpandedVehicleFieldsTests(TestCase):
    password = "A-strong-test-password-42!"

    def setUp(self):
        self.client = APIClient()
        admin = get_user_model().objects.create_superuser(
            username="admin", password=self.password
        )
        self.client.login(username=admin.username, password=self.password)

    def payload(self):
        return {
            "device_id": "ASSET-001", "plate_number": "ABC-123",
            "display_name": "Asset Van", "vehicle_type": "VAN",
            "vin": " vin-001 ", "fuel_type": "DIESEL",
            "transmission_type": "AUTOMATIC", "ownership_type": "COMPANY_OWNED",
            "supplier_name": "Supplier", "purchase_order_number": "PO-001",
            "purchase_price": "1200000.00", "purchase_currency": "php",
        }

    def test_create_update_optional_fields_search_and_immutable_device(self):
        response = self.client.post("/api/v1/vehicles/", self.payload(), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["vin"], "VIN-001")
        self.assertEqual(response.json()["purchase_currency"], "PHP")
        detail = "/api/v1/vehicles/ASSET-001/"
        self.assertEqual(
            self.client.patch(detail, {"color": "White"}, format="json").status_code,
            200,
        )
        self.assertEqual(
            self.client.patch(detail, {"device_id": "OTHER"}, format="json").status_code,
            400,
        )
        self.assertEqual(
            self.client.get("/api/v1/vehicles/?search=PO-001").json()["count"], 1
        )

    def test_optional_fields_and_validation(self):
        minimal = {
            "device_id": "ASSET-002", "plate_number": "ABC-124",
            "display_name": "Minimal", "vehicle_type": "OTHER",
        }
        response = self.client.post("/api/v1/vehicles/", minimal, format="json")
        self.assertEqual(response.status_code, 201)
        for field, value in (
            ("fuel_type", "STEAM"),
            ("transmission_type", "INVALID"),
            ("ownership_type", "BORROWED"),
            ("purchase_price", "-1.00"),
        ):
            with self.subTest(field=field):
                response = self.client.post(
                    "/api/v1/vehicles/",
                    {
                        **minimal,
                        "device_id": f"BAD-{field}",
                        "plate_number": f"BAD-{field}",
                        field: value,
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
