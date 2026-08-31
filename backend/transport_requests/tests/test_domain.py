from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from transport_requests.domain import (
    DELIVERY_LOGISTICS,
    PASSENGER_TRANSPORT,
    category_for_request_type,
)
from transport_requests.models import TransportRequest
from transport_requests.serializers import TransportRequestDetailSerializer


class TransportRequestDomainTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="domain-manager", is_staff=True)

    def payload(self, **changes):
        data = {
            "source_system": "HOTEL_MANAGEMENT_SYSTEM",
            "external_reference": "DOMAIN-1",
            "request_type": "AIRPORT_PICKUP",
            "requester_name": "Front Desk",
            "pickup_name": "Pickup",
            "pickup_address": "Pickup address",
            "pickup_latitude": "14.500000",
            "pickup_longitude": "121.000000",
            "destination_name": "Destination",
            "destination_address": "Destination address",
            "destination_latitude": "14.600000",
            "destination_longitude": "121.100000",
            "scheduled_pickup_at": (timezone.now() + timedelta(hours=2)).isoformat(),
            "passenger_count": 1,
            "luggage_count": 0,
        }
        data.update(changes)
        return data

    def intake(self, **changes):
        return TransportRequestDetailSerializer(
            data=self.payload(**changes),
            context={"request": SimpleNamespace(user=self.user)},
        )

    def valid_intake(self, **changes):
        serializer = self.intake(**changes)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        return serializer

    def test_known_types_derive_their_category_and_passenger_zero_is_rejected(self):
        accepted = self.valid_intake()
        self.assertEqual(accepted.data["request_category"], PASSENGER_TRANSPORT)
        rejected = self.intake(external_reference="DOMAIN-2", passenger_count=0)
        self.assertFalse(rejected.is_valid())
        self.assertIn("passenger_count", rejected.errors)
        self.assertEqual(category_for_request_type("GUEST_TRANSFER"), PASSENGER_TRANSPORT)
        self.assertEqual(category_for_request_type("FOOD_DELIVERY"), DELIVERY_LOGISTICS)

    def test_delivery_zero_passengers_accepts_quantity_and_preserves_intake_identity(self):
        response = self.valid_intake(
            source_system="RESTAURANT_MANAGEMENT_SYSTEM",
            external_reference="RMS-DELIVERY-1",
            request_type="FOOD_DELIVERY",
            passenger_count=0,
            luggage_count=99,
            load_description="  Twelve meal trays  ",
            load_quantity=12,
            handling_instructions=" Keep upright ",
            temperature_requirement=" Keep warm ",
        )
        body = response.data
        self.assertEqual(body["request_category"], DELIVERY_LOGISTICS)
        self.assertEqual(body["passenger_count"], 0)
        self.assertEqual(body["load_description"], "Twelve meal trays")
        self.assertEqual(body["handling_instructions"], "Keep upright")
        self.assertEqual(body["temperature_requirement"], "Keep warm")
        self.assertEqual(body["source_system"], "RESTAURANT_MANAGEMENT_SYSTEM")
        self.assertEqual(body["external_reference"], "RMS-DELIVERY-1")
        duplicate = self.intake(
            source_system="RESTAURANT_MANAGEMENT_SYSTEM",
            external_reference="RMS-DELIVERY-1",
            request_type="FOOD_DELIVERY",
            passenger_count=0,
            load_description="Meal trays",
            load_quantity=12,
        )
        self.assertFalse(duplicate.is_valid())
        self.assertIn("external_reference", duplicate.errors)

    def test_delivery_accepts_weight_without_quantity(self):
        response = self.valid_intake(
            external_reference="WEIGHT-ONLY",
            request_type="SUPPLIER_PICKUP",
            passenger_count=0,
            load_description="Kitchen supplies",
            estimated_weight_kg="42.50",
        )
        self.assertEqual(response.data["estimated_weight_kg"], "42.50")

    def test_delivery_requires_description_and_real_cargo_measure_not_luggage(self):
        missing_description = self.intake(
            external_reference="NO-DESCRIPTION",
            request_type="CATERING_DELIVERY",
            passenger_count=0,
            load_quantity=2,
        )
        self.assertFalse(missing_description.is_valid())
        self.assertIn("load_description", missing_description.errors)
        luggage_only = self.intake(
            external_reference="LUGGAGE-ONLY",
            request_type="BANQUET_LOGISTICS",
            passenger_count=0,
            luggage_count=10,
            load_description="Banquet equipment",
        )
        self.assertFalse(luggage_only.is_valid())
        self.assertIn("load_quantity", luggage_only.errors)
        self.assertIn("estimated_weight_kg", luggage_only.errors)

    def test_ambiguous_types_require_explicit_valid_category(self):
        for request_type in ("BRANCH_TRANSFER", "OTHER"):
            missing = self.intake(
                external_reference=f"{request_type}-MISSING",
                request_type=request_type,
            )
            self.assertFalse(missing.is_valid())
            self.assertIn("request_category", missing.errors)
        passenger = self.valid_intake(
            external_reference="BRANCH-PASSENGER",
            request_type="BRANCH_TRANSFER",
            request_category=PASSENGER_TRANSPORT,
            passenger_count=1,
        )
        self.assertEqual(passenger.data["request_category"], PASSENGER_TRANSPORT)
        delivery = self.valid_intake(
            external_reference="OTHER-DELIVERY",
            request_type="OTHER",
            request_category=DELIVERY_LOGISTICS,
            passenger_count=0,
            load_description="Documents",
            load_quantity=1,
        )
        self.assertEqual(delivery.data["request_category"], DELIVERY_LOGISTICS)

    def test_known_type_rejects_conflicting_explicit_category(self):
        response = self.intake(request_category=DELIVERY_LOGISTICS)
        self.assertFalse(response.is_valid())
        self.assertIn("request_category", response.errors)

    def test_new_delivery_fields_are_empty_for_new_passenger_requests(self):
        response = self.valid_intake()
        item = TransportRequest.objects.get(pk=response.instance.pk)
        self.assertEqual(item.load_description, "")
        self.assertIsNone(item.load_quantity)
        self.assertIsNone(item.estimated_weight_kg)

    def test_migration_backfills_only_unambiguous_legacy_rows_without_fake_cargo(self):
        common = {
            "source_system": "OTHER_SUBSYSTEM",
            "requester_name": "Legacy intake",
            "pickup_name": "Pickup",
            "pickup_address": "Pickup address",
            "pickup_latitude": "14.500000",
            "pickup_longitude": "121.000000",
            "destination_name": "Destination",
            "destination_address": "Destination address",
            "destination_latitude": "14.600000",
            "destination_longitude": "121.100000",
            "scheduled_pickup_at": timezone.now() + timedelta(hours=1),
            "created_by": self.user,
        }
        passenger = TransportRequest.objects.create(
            **common,
            external_reference="LEGACY-PASSENGER",
            request_type="GUEST_TRANSFER",
            passenger_count=2,
        )
        delivery = TransportRequest.objects.create(
            **common,
            external_reference="LEGACY-DELIVERY",
            request_type="FOOD_DELIVERY",
            passenger_count=0,
        )
        ambiguous = TransportRequest.objects.create(
            **common,
            external_reference="LEGACY-AMBIGUOUS",
            request_type="OTHER",
            passenger_count=0,
        )
        migration = import_module(
            "transport_requests.migrations.0003_request_category_and_delivery_fields"
        )

        class Apps:
            @staticmethod
            def get_model(app_label, model_name):
                return TransportRequest

        migration.backfill_request_categories(Apps(), None)
        passenger.refresh_from_db()
        delivery.refresh_from_db()
        ambiguous.refresh_from_db()
        self.assertEqual(passenger.request_category, PASSENGER_TRANSPORT)
        self.assertEqual(delivery.request_category, DELIVERY_LOGISTICS)
        self.assertIsNone(ambiguous.request_category)
        self.assertEqual(delivery.load_description, "")
        self.assertIsNone(delivery.load_quantity)
        self.assertIsNone(delivery.estimated_weight_kg)
