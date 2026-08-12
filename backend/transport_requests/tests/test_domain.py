from datetime import timedelta
from importlib import import_module

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from transport_requests.domain import (
    DELIVERY_LOGISTICS,
    PASSENGER_TRANSPORT,
    category_for_request_type,
)
from transport_requests.models import TransportRequest


class TransportRequestDomainTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="domain-manager", is_staff=True)
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.FLEET_MANAGER)
        self.client.force_authenticate(self.user)

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

    def post(self, **changes):
        return self.client.post(
            "/api/v1/transport-requests/", self.payload(**changes), format="json"
        )

    def test_known_types_derive_their_category_and_passenger_zero_is_rejected(self):
        accepted = self.post()
        self.assertEqual(accepted.status_code, 201)
        self.assertEqual(accepted.json()["request_category"], PASSENGER_TRANSPORT)
        rejected = self.post(external_reference="DOMAIN-2", passenger_count=0)
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("passenger_count", rejected.json())
        self.assertEqual(category_for_request_type("GUEST_TRANSFER"), PASSENGER_TRANSPORT)
        self.assertEqual(category_for_request_type("FOOD_DELIVERY"), DELIVERY_LOGISTICS)

    def test_delivery_zero_passengers_accepts_quantity_and_preserves_intake_identity(self):
        response = self.post(
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
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["request_category"], DELIVERY_LOGISTICS)
        self.assertEqual(body["passenger_count"], 0)
        self.assertEqual(body["load_description"], "Twelve meal trays")
        self.assertEqual(body["handling_instructions"], "Keep upright")
        self.assertEqual(body["temperature_requirement"], "Keep warm")
        self.assertEqual(body["source_system"], "RESTAURANT_MANAGEMENT_SYSTEM")
        self.assertEqual(body["external_reference"], "RMS-DELIVERY-1")
        duplicate = self.client.post(
            "/api/v1/transport-requests/",
            self.payload(
                source_system="RESTAURANT_MANAGEMENT_SYSTEM",
                external_reference="RMS-DELIVERY-1",
                request_type="FOOD_DELIVERY",
                passenger_count=0,
                load_description="Meal trays",
                load_quantity=12,
            ),
            format="json",
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_delivery_accepts_weight_without_quantity(self):
        response = self.post(
            external_reference="WEIGHT-ONLY",
            request_type="SUPPLIER_PICKUP",
            passenger_count=0,
            load_description="Kitchen supplies",
            estimated_weight_kg="42.50",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["estimated_weight_kg"], "42.50")

    def test_delivery_requires_description_and_real_cargo_measure_not_luggage(self):
        missing_description = self.post(
            external_reference="NO-DESCRIPTION",
            request_type="CATERING_DELIVERY",
            passenger_count=0,
            load_quantity=2,
        )
        self.assertEqual(missing_description.status_code, 400)
        self.assertIn("load_description", missing_description.json())
        luggage_only = self.post(
            external_reference="LUGGAGE-ONLY",
            request_type="BANQUET_LOGISTICS",
            passenger_count=0,
            luggage_count=10,
            load_description="Banquet equipment",
        )
        self.assertEqual(luggage_only.status_code, 400)
        self.assertIn("load_quantity", luggage_only.json())
        self.assertIn("estimated_weight_kg", luggage_only.json())

    def test_ambiguous_types_require_explicit_valid_category(self):
        for request_type in ("BRANCH_TRANSFER", "OTHER"):
            missing = self.post(
                external_reference=f"{request_type}-MISSING",
                request_type=request_type,
            )
            self.assertEqual(missing.status_code, 400)
            self.assertIn("request_category", missing.json())
        passenger = self.post(
            external_reference="BRANCH-PASSENGER",
            request_type="BRANCH_TRANSFER",
            request_category=PASSENGER_TRANSPORT,
            passenger_count=1,
        )
        self.assertEqual(passenger.status_code, 201)
        delivery = self.post(
            external_reference="OTHER-DELIVERY",
            request_type="OTHER",
            request_category=DELIVERY_LOGISTICS,
            passenger_count=0,
            load_description="Documents",
            load_quantity=1,
        )
        self.assertEqual(delivery.status_code, 201)

    def test_known_type_rejects_conflicting_explicit_category(self):
        response = self.post(request_category=DELIVERY_LOGISTICS)
        self.assertEqual(response.status_code, 400)
        self.assertIn("request_category", response.json())

    def test_new_delivery_fields_are_empty_for_new_passenger_requests(self):
        response = self.post()
        self.assertEqual(response.status_code, 201)
        item = TransportRequest.objects.get(pk=response.json()["id"])
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
