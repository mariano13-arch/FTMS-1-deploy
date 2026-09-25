from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from accounts.models import AuditEvent
from fleet.models import Driver, Vehicle
from transport_requests.models import (
    DispatchAssignment,
    TransportRequest,
    TripExpenseReceipt,
)
from transport_requests.receipt_ocr import (
    ReceiptOcrError,
    ReceiptOcrResult,
    parse_receipt_candidates,
)


def synthetic_image(image_format="JPEG", *, oversized=False):
    buffer = BytesIO()
    Image.new("RGB", (80, 40), "white").save(buffer, format=image_format)
    content = buffer.getvalue()
    if oversized:
        content += b"x" * (5 * 1024 * 1024 + 1 - len(content))
    extension = "jpg" if image_format == "JPEG" else image_format.lower()
    content_type = "image/jpeg" if image_format == "JPEG" else f"image/{extension}"
    return SimpleUploadedFile(f"synthetic.{extension}", content, content_type)


class DriverReceiptOcrApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.operator = get_user_model().objects.create_user(
            username="ocr-operator", is_staff=True
        )
        self.driver_user = get_user_model().objects.create_user(username="ocr-driver")
        self.driver = Driver.objects.create(
            driver_code="DRV-OCR-001",
            first_name="Test",
            last_name="Driver",
            linked_user=self.driver_user,
        )
        self.other_user = get_user_model().objects.create_user(username="other-ocr-driver")
        self.other_driver = Driver.objects.create(
            driver_code="DRV-OCR-002",
            first_name="Other",
            last_name="Driver",
            linked_user=self.other_user,
        )
        self.vehicle = Vehicle.objects.create(
            device_id="OCR-VEH-001",
            plate_number="OCR-001",
            display_name="OCR Test Vehicle",
            vehicle_type=Vehicle.VehicleType.VAN,
        )
        self.assignment = self.make_assignment("OCR-OWN", self.driver)
        self.url = (
            f"/api/v1/driver-trips/{self.assignment.transport_request_id}/"
            "receipts/ocr-preview/"
        )
        self.client.force_login(self.driver_user)

    def make_assignment(self, reference, driver):
        item = TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference=reference,
            request_type=TransportRequest.RequestType.GUEST_TRANSFER,
            request_category=TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            requester_name="Test Requester",
            pickup_name="Test Pickup",
            pickup_address="Makati City",
            pickup_latitude="14.565200",
            pickup_longitude="121.028600",
            destination_name="Test Destination",
            destination_address="Pasay City",
            destination_latitude="14.508600",
            destination_longitude="121.019800",
            scheduled_pickup_at=timezone.now(),
            estimated_duration_minutes=30,
            passenger_count=1,
            status=TransportRequest.Status.READY_FOR_DISPATCH,
            assigned_vehicle=self.vehicle,
            created_by=self.operator,
        )
        return DispatchAssignment.objects.create(
            transport_request=item,
            vehicle=self.vehicle,
            driver=driver,
            selection_mode=DispatchAssignment.SelectionMode.MANUAL,
            override_reason="Synthetic OCR test assignment",
            confirmed_by=self.operator,
            accepted_at=timezone.now(),
            accepted_by=driver.linked_user,
            execution_status=DispatchAssignment.ExecutionStatus.EN_ROUTE_TO_PICKUP,
            execution_started_at=timezone.now(),
        )

    def post(self, expense_type="FUEL", image=None):
        return self.client.post(
            self.url,
            {"expense_type": expense_type, "receipt_image": image or synthetic_image()},
            format="multipart",
        )

    @patch("transport_requests.driver_views.analyze_receipt")
    def test_assigned_driver_can_preview_fuel_and_toll(self, analyze):
        analyze.return_value = ReceiptOcrResult(candidates={"amount": "125.00"}, warnings=[])

        fuel = self.post()
        toll = self.post("TOLL", synthetic_image("PNG"))

        self.assertEqual(fuel.status_code, 200)
        self.assertEqual(toll.status_code, 200)
        self.assertEqual(fuel.json()["expense_type"], "FUEL")
        self.assertEqual(toll.json()["expense_type"], "TOLL")
        self.assertEqual(analyze.call_count, 2)

    def test_another_driver_cannot_preview_unrelated_trip(self):
        assignment = self.make_assignment("OCR-OTHER", self.other_driver)
        url = f"/api/v1/driver-trips/{assignment.transport_request_id}/receipts/ocr-preview/"

        response = self.client.post(
            url,
            {"expense_type": "FUEL", "receipt_image": synthetic_image()},
            format="multipart",
        )

        self.assertEqual(response.status_code, 404)

    @patch("transport_requests.driver_views.analyze_receipt")
    def test_jpeg_and_png_are_accepted(self, analyze):
        analyze.return_value = ReceiptOcrResult(candidates={}, warnings=[])
        self.assertEqual(self.post(image=synthetic_image("JPEG")).status_code, 200)
        self.assertEqual(self.post(image=synthetic_image("PNG")).status_code, 200)

    def test_unsupported_oversized_and_corrupted_images_are_rejected(self):
        gif = synthetic_image("GIF")
        spoofed_gif = SimpleUploadedFile(
            "spoofed.jpg", gif.read(), content_type="image/jpeg"
        )
        oversized = synthetic_image(oversized=True)
        corrupted = SimpleUploadedFile("broken.jpg", b"not an image", "image/jpeg")

        for image in (gif, spoofed_gif, oversized, corrupted):
            with self.subTest(name=image.name):
                response = self.post(image=image)
                self.assertEqual(response.status_code, 400)
                self.assertIn("receipt_image", response.json())

    @patch("transport_requests.driver_views.analyze_receipt")
    def test_preview_is_transient_and_does_not_expose_raw_text(self, analyze):
        raw_text = "TEST FUEL STATION SECRET RECEIPT BODY"
        analyze.return_value = ReceiptOcrResult(
            candidates={"merchant_or_operator": "Test Fuel Station"}, warnings=[]
        )
        receipt_count = TripExpenseReceipt.objects.count()
        audit_count = AuditEvent.objects.count()

        response = self.post()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(TripExpenseReceipt.objects.count(), receipt_count)
        self.assertEqual(AuditEvent.objects.count(), audit_count)
        self.assertNotIn(raw_text, response.content.decode())
        self.assertNotIn("raw", response.json())

    @patch("transport_requests.driver_views.analyze_receipt")
    def test_engine_failure_allows_manual_fallback(self, analyze):
        analyze.side_effect = ReceiptOcrError("engine unavailable")

        response = self.post("TOLL")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["candidates"]["amount"])
        self.assertIn("manual", response.json()["warnings"][0].lower())
        self.assertFalse(TripExpenseReceipt.objects.exists())


class ReceiptCandidateParserTests(TestCase):
    def test_fuel_candidates_are_parsed_from_explicit_labels(self):
        result = parse_receipt_candidates(
            """
            MERCHANT: TEST FUEL STATION
            DATE: 2026-09-25 14:30
            RECEIPT NO: TEST-1001
            LITERS: 25.30
            PRICE/L: PHP 59.29
            FUEL: GASOLINE
            GRADE: UNLEADED 91
            GRAND TOTAL: ₱1,500.00
            """,
            "FUEL",
        )

        self.assertEqual(result.candidates["amount"], "1500.00")
        self.assertEqual(result.candidates["liters"], "25.300")
        self.assertEqual(result.candidates["unit_price"], "59.2900")
        self.assertEqual(result.candidates["fuel_type"], "GASOLINE")
        self.assertEqual(result.candidates["fuel_grade"], "UNLEADED_91")
        self.assertEqual(result.candidates["receipt_number"], "TEST-1001")
        self.assertEqual(result.candidates["transaction_at"], "2026-09-25T14:30:00")

    def test_explicit_diesel_and_grade_are_parsed(self):
        result = parse_receipt_candidates(
            "FUEL: DIESEL\nGRADE: PREMIUM DIESEL\nTOTAL AMOUNT PHP 750.00", "FUEL"
        )

        self.assertEqual(result.candidates["fuel_type"], "DIESEL")
        self.assertEqual(result.candidates["fuel_grade"], "PREMIUM_DIESEL")
        self.assertEqual(result.candidates["amount"], "750.00")

    def test_toll_candidates_exclude_fuel_fields(self):
        result = parse_receipt_candidates(
            """
            OPERATOR: TEST TOLL OPERATOR
            TOLL PLAZA: TEST NORTH PLAZA
            REF NO: REF-900
            AMOUNT DUE: P 125.00
            """,
            "TOLL",
        )

        self.assertEqual(result.candidates["amount"], "125.00")
        self.assertEqual(result.candidates["receipt_number"], "REF-900")
        self.assertEqual(result.candidates["toll_plaza"], "Test North Plaza")
        self.assertNotIn("liters", result.candidates)
        self.assertNotIn("fuel_type", result.candidates)

    def test_unknown_values_and_ambiguous_date_are_not_guessed(self):
        result = parse_receipt_candidates(
            "DATE: 09/10/2026\nUNLABELED 999.00\n123456789", "FUEL"
        )

        self.assertTrue(all(value is None for value in result.candidates.values()))
        self.assertIn("manual", result.warnings[0].lower())

    def test_date_without_time_is_returned_separately(self):
        result = parse_receipt_candidates("DATE: 25/09/2026", "TOLL")

        self.assertIsNone(result.candidates["transaction_at"])
        self.assertEqual(result.candidates["transaction_date"], "2026-09-25")

    def test_unlabeled_currency_is_not_used_as_total(self):
        result = parse_receipt_candidates("PHP 1,250.00", "TOLL")

        self.assertIsNone(result.candidates["amount"])
