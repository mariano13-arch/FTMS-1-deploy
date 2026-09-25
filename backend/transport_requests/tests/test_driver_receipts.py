import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from fleet.models import Driver, FuelPriceRecord, Vehicle
from transport_requests.models import (
    DispatchAssignment,
    TransportRequest,
    TripExpenseReceipt,
)

TEMP_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class DriverReceiptApiTests(TestCase):
    password = "A-strong-driver-password-42!"

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.client = APIClient()
        self.operator = get_user_model().objects.create_user(
            username="receipt-operator", is_staff=True
        )
        self.driver_user = get_user_model().objects.create_user(
            username="receipt-driver", password=self.password
        )
        self.driver = Driver.objects.create(
            driver_code="DRV-RECEIPT-001",
            first_name="Maria",
            last_name="Reyes",
            linked_user=self.driver_user,
        )
        self.other_user = get_user_model().objects.create_user(
            username="other-receipt-driver", password=self.password
        )
        self.other_driver = Driver.objects.create(
            driver_code="DRV-RECEIPT-002",
            first_name="Jose",
            last_name="Santos",
            linked_user=self.other_user,
        )
        self.vehicle = Vehicle.objects.create(
            device_id="RECEIPT-VEH-001",
            plate_number="ABC-123",
            display_name="Guest Van",
            vehicle_type=Vehicle.VehicleType.VAN,
            fuel_type=Vehicle.FuelType.GASOLINE,
            fuel_grade=Vehicle.FuelGrade.UNLEADED_91,
        )
        self.other_vehicle = Vehicle.objects.create(
            device_id="RECEIPT-VEH-002",
            plate_number="XYZ-999",
            display_name="Other Van",
        )
        self.request = self.make_request("RECEIPT-OWN")
        self.assignment = self.assign(self.request)

    def make_request(self, reference, *, status=TransportRequest.Status.READY_FOR_DISPATCH):
        return TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference=reference,
            request_type=TransportRequest.RequestType.GUEST_TRANSFER,
            request_category=TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            requester_name="Front Desk",
            pickup_name="FTMS Hotel",
            pickup_address="Makati City",
            pickup_latitude="14.565200",
            pickup_longitude="121.028600",
            destination_name="Airport",
            destination_address="Pasay City",
            destination_latitude="14.508600",
            destination_longitude="121.019800",
            scheduled_pickup_at=timezone.now() - timedelta(hours=1),
            estimated_duration_minutes=60,
            passenger_count=4,
            status=status,
            assigned_vehicle=self.vehicle,
            created_by=self.operator,
        )

    def assign(self, item, *, driver=None, vehicle=None):
        assignment = DispatchAssignment.objects.create(
            transport_request=item,
            vehicle=vehicle or self.vehicle,
            driver=driver or self.driver,
            selection_mode=DispatchAssignment.SelectionMode.MANUAL,
            override_reason="Controlled receipt test assignment",
            confirmed_by=self.operator,
            accepted_at=timezone.now() - timedelta(minutes=30),
            accepted_by=(driver or self.driver).linked_user,
            execution_status=DispatchAssignment.ExecutionStatus.EN_ROUTE_TO_PICKUP,
            execution_started_at=timezone.now() - timedelta(minutes=20),
        )
        return assignment

    def authenticate(self, user=None):
        self.client.force_login(user or self.driver_user)

    def image(self, name="receipt.jpg", size=16, content_type="image/jpeg"):
        return SimpleUploadedFile(name, b"x" * size, content_type)

    def fuel_payload(self, **overrides):
        return {
            "expense_type": "FUEL",
            "transaction_at": (timezone.now() - timedelta(minutes=5)).isoformat(),
            "amount": "500.00",
            "receipt_number": "FUEL-001",
            "merchant_or_operator": "Shell Station",
            "receipt_image": self.image(),
            "liters": "10.000",
            "unit_price": "50.0000",
            "fuel_type": Vehicle.FuelType.GASOLINE,
            "fuel_grade": Vehicle.FuelGrade.UNLEADED_91,
            **overrides,
        }

    def toll_payload(self, **overrides):
        return {
            "expense_type": "TOLL",
            "transaction_at": (timezone.now() - timedelta(minutes=5)).isoformat(),
            "amount": "125.00",
            "receipt_number": "TOLL-001",
            "merchant_or_operator": "NLEX",
            "receipt_image": self.image("toll.png", content_type="image/png"),
            "toll_plaza": "Balintawak",
            **overrides,
        }

    def receipt_url(self, assignment=None):
        assignment = assignment or self.assignment
        return f"/api/v1/driver-trips/{assignment.transport_request_id}/receipts/"

    def test_assigned_driver_can_create_fuel_and_toll_receipts(self):
        self.authenticate()

        fuel = self.client.post(
            self.receipt_url(), self.fuel_payload(), format="multipart"
        )
        toll = self.client.post(
            self.receipt_url(), self.toll_payload(receipt_number="TOLL-002"), format="multipart"
        )

        self.assertEqual(fuel.status_code, 201)
        self.assertEqual(toll.status_code, 201)
        self.assertEqual(TripExpenseReceipt.objects.count(), 2)
        receipt = TripExpenseReceipt.objects.get(expense_type="FUEL")
        self.assertEqual(receipt.driver, self.driver)
        self.assertEqual(receipt.vehicle, self.vehicle)
        self.assertEqual(fuel.json()["vehicle_display"], "Guest Van · ABC-123")
        self.assertNotIn("receipt_image", fuel.json())
        self.assertNotIn("trip_receipts/", str(fuel.json()))

    def test_driver_cannot_submit_against_another_drivers_assignment(self):
        other_request = self.make_request("RECEIPT-OTHER")
        other_assignment = self.assign(other_request, driver=self.other_driver)
        self.authenticate()

        response = self.client.post(
            self.receipt_url(other_assignment), self.fuel_payload(), format="multipart"
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(TripExpenseReceipt.objects.exists())

    def test_driver_and_vehicle_are_server_derived_and_cannot_be_overridden(self):
        self.authenticate()
        response = self.client.post(
            self.receipt_url(),
            self.fuel_payload(driver=self.other_driver.pk, vehicle=self.other_vehicle.pk),
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("driver", response.json())
        self.assertIn("vehicle", response.json())

    def test_validation_for_amount_type_fuel_fields_and_images(self):
        self.authenticate()
        cases = (
            (self.fuel_payload(amount="0.00"), "amount"),
            (self.fuel_payload(expense_type="MEAL"), "expense_type"),
            (self.toll_payload(liters="1.000"), "liters"),
            (self.fuel_payload(amount="400.00"), "amount"),
            (
                self.fuel_payload(
                    receipt_image=self.image("receipt.gif", content_type="image/gif")
                ),
                "receipt_image",
            ),
            (
                self.fuel_payload(
                    receipt_image=self.image("large.jpg", size=5 * 1024 * 1024 + 1)
                ),
                "receipt_image",
            ),
        )
        for payload, field in cases:
            with self.subTest(field=field):
                response = self.client.post(self.receipt_url(), payload, format="multipart")
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json())

    def test_owner_lists_retrieves_and_downloads_private_image(self):
        self.authenticate()
        first = self.client.post(
            self.receipt_url(),
            self.fuel_payload(receipt_number="FIRST"),
            format="multipart",
        ).json()
        second = self.client.post(
            self.receipt_url(),
            self.toll_payload(receipt_number="SECOND"),
            format="multipart",
        ).json()

        listed = self.client.get(self.receipt_url())
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            [item["id"] for item in listed.json()["results"]],
            [second["id"], first["id"]],
        )
        detail = self.client.get(f"/api/v1/driver-receipts/{first['id']}/")
        image = self.client.get(f"/api/v1/driver-receipts/{first['id']}/image/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(image.status_code, 200)
        self.assertNotIn("/media/", first["image_url"])

        self.client.force_login(self.other_user)
        self.assertEqual(
            self.client.get(f"/api/v1/driver-receipts/{first['id']}/").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f"/api/v1/driver-receipts/{first['id']}/image/").status_code,
            404,
        )

    def test_duplicate_warning_is_non_blocking(self):
        self.authenticate()
        first = self.client.post(self.receipt_url(), self.fuel_payload(), format="multipart")
        duplicate = self.client.post(
            self.receipt_url(),
            self.fuel_payload(receipt_image=self.image("duplicate.jpg")),
            format="multipart",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(duplicate.status_code, 201)
        self.assertFalse(first.json()["duplicate_warning"])
        self.assertTrue(duplicate.json()["duplicate_warning"])
        self.assertEqual(TripExpenseReceipt.objects.count(), 2)

    def test_no_ocr_or_reference_price_values_are_used(self):
        FuelPriceRecord.objects.create(
            fuel_type=Vehicle.FuelType.GASOLINE,
            fuel_grade=Vehicle.FuelGrade.UNLEADED_91,
            price_per_liter="99.9900",
            currency=FuelPriceRecord.Currency.PHP,
            effective_at=timezone.now() - timedelta(days=1),
            provider="ShellPH",
            source_mode=FuelPriceRecord.SourceMode.MANUAL,
        )
        self.authenticate()

        response = self.client.post(
            self.receipt_url(),
            self.fuel_payload(unit_price="50.0000", amount="500.00"),
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        receipt = TripExpenseReceipt.objects.get()
        self.assertEqual(str(receipt.unit_price), "50.0000")
        self.assertFalse(hasattr(receipt, "raw_ocr_text"))
