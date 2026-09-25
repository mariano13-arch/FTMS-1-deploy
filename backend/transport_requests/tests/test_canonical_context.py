from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import serializers

from fleet.models import Vehicle
from transport_requests.flight_tracking import airport_pickup_timing, refresh_flight_context
from transport_requests.models import TransportRequest, TransportRequestFlightContext
from transport_requests.services import validate_vehicle
from transport_requests.source_integration import create_integration_client


class CanonicalTransportContextTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="canonical-context")

    def make_supply_request(self, weight=Decimal("500.00")):
        return TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.SUPPLY_CHAIN_MANAGEMENT_SYSTEM,
            external_reference="SCMS-001",
            request_type=TransportRequest.RequestType.SUPPLIER_PICKUP,
            request_category=TransportRequest.RequestCategory.DELIVERY_LOGISTICS,
            requester_name="Inventory Control",
            pickup_name="Supplier warehouse",
            pickup_address="Makati",
            pickup_latitude="14.565200",
            pickup_longitude="121.028600",
            destination_name="Hotel receiving",
            destination_address="Pasay",
            destination_latitude="14.508600",
            destination_longitude="121.019800",
            scheduled_pickup_at=timezone.now() + timedelta(hours=2),
            passenger_count=0,
            load_description="Housekeeping supplies",
            load_quantity=20,
            estimated_weight_kg=weight,
            created_by=self.user,
        )

    def test_supply_chain_is_a_trusted_source(self):
        client, credential = create_integration_client(
            name="Inventory Platform",
            source_system=TransportRequest.SourceSystem.SUPPLY_CHAIN_MANAGEMENT_SYSTEM,
        )
        self.assertEqual(client.source_system, "SUPPLY_CHAIN_MANAGEMENT_SYSTEM")
        self.assertTrue(credential.startswith(f"{client.key_identifier}."))

    def test_known_supply_weight_requires_sufficient_recorded_payload(self):
        item = self.make_supply_request()
        unknown = Vehicle.objects.create(
            device_id="SUPPLY-UNKNOWN", plate_number="SUP-001", display_name="Unknown payload"
        )
        too_small = Vehicle.objects.create(
            device_id="SUPPLY-SMALL", plate_number="SUP-002", display_name="Small truck",
            payload_capacity_kg=Decimal("499.99"),
        )
        suitable = Vehicle.objects.create(
            device_id="SUPPLY-OK", plate_number="SUP-003", display_name="Suitable truck",
            payload_capacity_kg=Decimal("500.00"),
        )
        with self.assertRaises(serializers.ValidationError):
            validate_vehicle(item, unknown, require_new_assignment_readiness=False)
        with self.assertRaises(serializers.ValidationError):
            validate_vehicle(item, too_small, require_new_assignment_readiness=False)
        validate_vehicle(item, suitable, require_new_assignment_readiness=False)

    @override_settings(
        AIRPORT_PASSENGER_READY_ALLOWANCE_MINUTES="30",
        DISPATCH_OPERATIONAL_BUFFER_MINUTES="15",
    )
    def test_airport_timing_uses_arrival_allowance_tomtom_and_buffer(self):
        arrival = timezone.now().replace(microsecond=0)
        context = TransportRequestFlightContext(scheduled_arrival_at=arrival)
        result = airport_pickup_timing(context, travel_time_seconds=1800)
        self.assertEqual(result["status"], "AVAILABLE")
        self.assertEqual(result["passenger_ready_at"], arrival + timedelta(minutes=30))
        self.assertEqual(result["recommended_departure_at"], arrival - timedelta(minutes=15))

    @override_settings(
        FLIGHTRADAR24_API_TOKEN="",
        AIRPORT_PASSENGER_READY_ALLOWANCE_MINUTES="",
        DISPATCH_OPERATIONAL_BUFFER_MINUTES="",
    )
    def test_missing_provider_and_operational_settings_are_truthful_blockers(self):
        item = self.make_supply_request(weight=None)
        item.request_type = TransportRequest.RequestType.AIRPORT_PICKUP
        item.request_category = TransportRequest.RequestCategory.PASSENGER_TRANSPORT
        item.passenger_count = 1
        item.save(update_fields=["request_type", "request_category", "passenger_count"])
        context = TransportRequestFlightContext.objects.create(
            transport_request=item, flight_number="PR 123"
        )
        refresh = refresh_flight_context(context)
        timing = airport_pickup_timing(context)
        self.assertEqual(refresh.status, "NOT_CONFIGURED")
        self.assertEqual(timing["status"], "BLOCKED")
        self.assertIn("passenger-ready allowance", timing["message"])
        self.assertIn("TomTom travel time", timing["message"])
