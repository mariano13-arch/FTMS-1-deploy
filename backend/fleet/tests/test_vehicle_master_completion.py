from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from fleet.models import Vehicle, VehicleDocument
from fleet.serializers import VehicleSerializer


class VehicleCapacityTests(TestCase):
    def test_payload_and_gvwr_are_optional_nonnegative_metric_values(self):
        optional = Vehicle(
            device_id="CAP-001", plate_number="CAP-001", display_name="Optional Capacity"
        )
        optional.full_clean()

        recorded = Vehicle(
            device_id="CAP-002",
            plate_number="CAP-002",
            display_name="Recorded Capacity",
            payload_capacity_kg=Decimal("950.50"),
            gvwr_kg=Decimal("6350.00"),
        )
        recorded.full_clean()

        for field in ("payload_capacity_kg", "gvwr_kg"):
            invalid = Vehicle(
                device_id=f"BAD-{field}",
                plate_number=f"BAD-{field}",
                display_name="Invalid Capacity",
                **{field: Decimal("-0.01")},
            )
            with self.subTest(field=field), self.assertRaises(ValidationError):
                invalid.full_clean()

    def test_capacity_fields_are_exposed_without_fake_defaults(self):
        vehicle = Vehicle.objects.create(
            device_id="CAP-003",
            plate_number="CAP-003",
            display_name="API Capacity",
            payload_capacity_kg=Decimal("1000.25"),
            gvwr_kg=Decimal("7000.00"),
        )
        data = VehicleSerializer(vehicle).data
        self.assertEqual(data["payload_capacity_kg"], "1000.25")
        self.assertEqual(data["gvwr_kg"], "7000.00")


class VehicleDocumentHealthTests(TestCase):
    required_types = (
        VehicleDocument.DocumentType.OFFICIAL_RECEIPT,
        VehicleDocument.DocumentType.CERTIFICATE_OF_REGISTRATION,
        VehicleDocument.DocumentType.INSURANCE,
        VehicleDocument.DocumentType.EMISSION_CERTIFICATE,
        VehicleDocument.DocumentType.PMVIC_CERTIFICATE,
    )

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="records")
        self.vehicle = Vehicle.objects.create(
            device_id="HEALTH-001", plate_number="HEALTH-001", display_name="Records"
        )

    def add_document(
        self,
        document_type,
        expiry_date=None,
        *,
        effective_date=None,
        issued_date=None,
    ):
        return VehicleDocument.objects.create(
            vehicle=self.vehicle,
            document_type=document_type,
            title=document_type,
            issuer_name="Recorded issuer",
            effective_date=effective_date,
            issued_date=issued_date,
            expiry_date=expiry_date,
            file=f"vehicle_documents/{document_type}.pdf",
            uploaded_by=self.user,
        )

    def health(self):
        return VehicleSerializer(self.vehicle).data["document_health"]

    def test_missing_records_are_incomplete(self):
        self.assertEqual(self.health(), "INCOMPLETE")

    def test_unrelated_expired_records_do_not_affect_compliance(self):
        today = timezone.localdate()
        for document_type in (
            VehicleDocument.DocumentType.WARRANTY,
            VehicleDocument.DocumentType.PURCHASE_ORDER,
        ):
            self.add_document(document_type, today - timedelta(days=1))
        self.assertEqual(self.health(), "INCOMPLETE")

    def test_missing_one_required_category_is_incomplete(self):
        expiry = timezone.localdate() + timedelta(days=31)
        for document_type in self.required_types[:-1]:
            self.add_document(document_type, expiry)
        self.assertEqual(self.health(), "INCOMPLETE")

    def test_latest_required_record_expired_is_expired(self):
        today = timezone.localdate()
        self.add_document(
            VehicleDocument.DocumentType.INSURANCE,
            today - timedelta(days=1),
            effective_date=today,
        )
        self.assertEqual(self.health(), "EXPIRED")

    def test_expiry_exactly_30_days_is_expiring_soon_after_records_are_complete(self):
        today = timezone.localdate()
        for document_type in self.required_types:
            expiry = today + timedelta(days=30 if document_type == "INSURANCE" else 31)
            self.add_document(document_type, expiry)
        self.assertEqual(self.health(), "EXPIRING_SOON")

    def test_complete_healthy_tracked_records_are_current(self):
        expiry = timezone.localdate() + timedelta(days=31)
        for document_type in self.required_types:
            self.add_document(document_type, expiry)
        self.assertEqual(self.health(), "CURRENT")

    def test_newer_insurance_replaces_an_expired_historical_record(self):
        today = timezone.localdate()
        old = self.add_document(
            VehicleDocument.DocumentType.INSURANCE,
            today - timedelta(days=1),
            effective_date=today - timedelta(days=365),
        )
        newer = self.add_document(
            VehicleDocument.DocumentType.INSURANCE,
            today + timedelta(days=60),
            effective_date=today,
        )
        for document_type in self.required_types:
            if document_type != VehicleDocument.DocumentType.INSURANCE:
                self.add_document(document_type, today + timedelta(days=60))

        self.assertEqual(self.health(), "CURRENT")
        self.assertEqual(
            set(self.vehicle.documents.filter(document_type="INSURANCE")),
            {old, newer},
        )

    def test_newer_pmvic_governs_over_an_expired_historical_record(self):
        today = timezone.localdate()
        self.add_document(
            VehicleDocument.DocumentType.PMVIC_CERTIFICATE,
            today - timedelta(days=1),
            issued_date=today - timedelta(days=365),
        )
        self.add_document(
            VehicleDocument.DocumentType.PMVIC_CERTIFICATE,
            today + timedelta(days=60),
            issued_date=today,
        )
        for document_type in self.required_types:
            if document_type != VehicleDocument.DocumentType.PMVIC_CERTIFICATE:
                self.add_document(document_type, today + timedelta(days=60))

        self.assertEqual(self.health(), "CURRENT")
        self.assertEqual(
            self.vehicle.documents.filter(document_type="PMVIC_CERTIFICATE").count(),
            2,
        )
