from datetime import timedelta
from io import StringIO
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.core.management import CommandError, call_command
from django.db.models import F
from django.test import TestCase, override_settings
from django.utils import timezone

from fleet.inspection_readiness import inspection_readiness
from fleet.maintenance import maintenance_readiness
from fleet.models import Driver, Vehicle
from fleet.serializers import driver_eligibility
from telemetry.models import TelemetryEvent
from transport_requests import dispatch, matrix
from transport_requests.management.commands.seed_transport_demo import (
    AIRPORTS,
    LOCATION_CATALOG,
)
from transport_requests.models import (
    DispatchAssignment,
    DispatchExecutionEvent,
    DispatchPlan,
    SourceResultOutbox,
    TransportRequest,
    TransportRequestFlightContext,
)


@override_settings(DEBUG=True)
class SeedTransportDemoTests(TestCase):
    def setUp(self):
        self.operator = get_user_model().objects.create_superuser(
            username="transport-demo-admin",
            password="development-only",
        )

    def seed(
        self,
        *,
        count=100,
        reset=False,
        full_local_transport_reset=False,
        confirm_local_demo_reset=False,
    ):
        output = StringIO()
        call_command(
            "seed_transport_demo",
            count=count,
            reset=reset,
            full_local_transport_reset=full_local_transport_reset,
            confirm_local_demo_reset=confirm_local_demo_reset,
            stdout=output,
        )
        return output.getvalue()

    def demo_requests(self):
        return TransportRequest.objects.filter(
            created_by=self.operator,
            external_reference__regex=r"^(HMS|SCM)-TR-2026-[0-9]{4}$",
        )

    def test_default_seed_has_canonical_distribution_and_truthful_boundaries(self):
        output = self.seed()
        requests = self.demo_requests()

        self.assertEqual(requests.count(), 100)
        expected_types = {
            TransportRequest.RequestType.GUEST_TRANSFER: 35,
            TransportRequest.RequestType.AIRPORT_PICKUP: 15,
            TransportRequest.RequestType.AIRPORT_DROPOFF: 10,
            TransportRequest.RequestType.SUPPLIER_PICKUP: 30,
            TransportRequest.RequestType.BRANCH_TRANSFER: 10,
        }
        for request_type, expected in expected_types.items():
            self.assertEqual(requests.filter(request_type=request_type).count(), expected)
        self.assertFalse(requests.exclude(request_type__in=expected_types).exists())
        passenger = requests.filter(
            request_category=TransportRequest.RequestCategory.PASSENGER_TRANSPORT
        )
        supply = requests.filter(
            request_category=TransportRequest.RequestCategory.DELIVERY_LOGISTICS
        )
        self.assertEqual(passenger.count(), 60)
        self.assertEqual(supply.count(), 40)
        self.assertFalse(
            passenger.exclude(
                source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM
            ).exists()
        )
        self.assertFalse(
            supply.exclude(
                source_system=(
                    TransportRequest.SourceSystem.SUPPLY_CHAIN_MANAGEMENT_SYSTEM
                )
            ).exists()
        )
        self.assertTrue(
            requests.filter(external_reference="HMS-TR-2026-0001").exists()
        )
        self.assertTrue(
            requests.filter(external_reference="SCM-TR-2026-0040").exists()
        )
        prohibited = re.compile(r"\b(demo|test|sample|mock|fake|dummy)\b", re.IGNORECASE)
        visible_fields = (
            "external_reference",
            "requester_name",
            "pickup_name",
            "pickup_address",
            "destination_name",
            "destination_address",
            "load_description",
            "handling_instructions",
            "notes",
        )
        for request in requests:
            visible_text = " ".join(str(getattr(request, field) or "") for field in visible_fields)
            self.assertIsNone(prohibited.search(visible_text), visible_text)
        self.assertGreater(requests.values("requester_name").distinct().count(), 2)
        self.assertGreater(requests.values("scheduled_pickup_at").distinct().count(), 10)
        self.assertGreater(requests.values("notes").distinct().count(), 1)

        approved_locations = {
            (location.name, location.address, location.latitude, location.longitude)
            for location in LOCATION_CATALOG.values()
        }
        route_pairs = set()
        for request in requests:
            pickup = (
                request.pickup_name,
                request.pickup_address,
                f"{request.pickup_latitude:.6f}",
                f"{request.pickup_longitude:.6f}",
            )
            destination = (
                request.destination_name,
                request.destination_address,
                f"{request.destination_latitude:.6f}",
                f"{request.destination_longitude:.6f}",
            )
            self.assertIn(pickup, approved_locations)
            self.assertIn(destination, approved_locations)
            self.assertNotEqual(pickup, destination)
            route_pairs.add((pickup[0], destination[0]))
        self.assertGreaterEqual(len(route_pairs), 20)
        self.assertGreaterEqual(requests.values("pickup_name").distinct().count(), 12)
        self.assertGreaterEqual(requests.values("destination_name").distinct().count(), 10)

        airport_names = {location.name for location in AIRPORTS}
        airport_pickups = requests.filter(
            request_type=TransportRequest.RequestType.AIRPORT_PICKUP
        )
        self.assertEqual(set(airport_pickups.values_list("pickup_name", flat=True)), airport_names)
        self.assertFalse(airport_pickups.filter(pickup_name=F("destination_name")).exists())
        supply_types = (
            TransportRequest.RequestType.SUPPLIER_PICKUP,
            TransportRequest.RequestType.BRANCH_TRANSFER,
        )
        self.assertFalse(
            requests.filter(request_type__in=supply_types).exclude(
                request_category=TransportRequest.RequestCategory.DELIVERY_LOGISTICS,
                source_system=TransportRequest.SourceSystem.SUPPLY_CHAIN_MANAGEMENT_SYSTEM,
            ).exists()
        )

        self.assertEqual(
            requests.filter(status=TransportRequest.Status.FOR_APPROVAL).count(), 100
        )
        self.assertFalse(requests.exclude(status=TransportRequest.Status.FOR_APPROVAL).exists())
        assignments = DispatchAssignment.objects.filter(transport_request__in=requests)
        self.assertEqual(assignments.count(), 0)
        self.assertEqual(DispatchExecutionEvent.objects.filter(assignment__in=assignments).count(), 0)

        self.assertEqual(Vehicle.objects.filter(device_id__startswith="DEMO-V").count(), 15)
        drivers = Driver.objects.filter(driver_code__startswith="DEMO-DRIVER-")
        self.assertEqual(drivers.count(), 15)
        self.assertEqual(
            sum(driver_eligibility(driver)[0] == "ELIGIBLE" for driver in drivers), 12
        )
        self.assertTrue(
            Vehicle.objects.filter(
                device_id__startswith="DEMO-V",
                vehicle_type=Vehicle.VehicleType.VAN,
                is_active=True,
            ).exists()
        )
        self.assertTrue(
            Vehicle.objects.filter(
                device_id__startswith="DEMO-V",
                vehicle_type=Vehicle.VehicleType.SERVICE_TRUCK,
                payload_capacity_kg__gte=1200,
                is_active=True,
            ).exists()
        )
        self.assertFalse(
            assignments.filter(
                transport_request__estimated_weight_kg__gt=500,
                vehicle__payload_capacity_kg__lt=500,
            ).exists()
        )
        self.assertFalse(
            inspection_readiness(Vehicle.objects.get(device_id="DEMO-V013")).eligible
        )
        self.assertFalse(
            maintenance_readiness(Vehicle.objects.get(device_id="DEMO-V012")).eligible
        )

        self.assertEqual(TransportRequestFlightContext.objects.count(), 0)
        self.assertEqual(SourceResultOutbox.objects.count(), 0)
        positions = TelemetryEvent.objects.filter(event_id__startswith="DEMO-TRANSPORT-POSITION-")
        self.assertEqual(positions.count(), 10)
        self.assertFalse(
            positions.exclude(position_source=TelemetryEvent.PositionSource.SIMULATED_TEST).exists()
        )
        self.assertFalse(positions.exclude(gnss_speed_kph__isnull=True).exists())
        self.assertTrue(
            all(event.recorded_at >= timezone.now() - timedelta(minutes=5) for event in positions)
        )
        self.assertEqual(
            len(
                matrix.eligible_vehicle_origins(
                    list(positions.values_list("vehicle__device_id", flat=True))
                )
            ),
            10,
        )
        self.assertEqual(DispatchPlan.objects.count(), 0)
        self.assertFalse(
            requests.filter(
                source_system__in=[
                    TransportRequest.SourceSystem.RESTAURANT_MANAGEMENT_SYSTEM,
                    TransportRequest.SourceSystem.MANUAL_STAFF_ENTRY,
                ]
            ).exists()
        )
        self.assertFalse(
            requests.filter(
                request_type__in=[
                    TransportRequest.RequestType.FOOD_DELIVERY,
                    TransportRequest.RequestType.CATERING_DELIVERY,
                ]
            ).exists()
        )
        self.assertIn("No route, ETA, or optimizer result was seeded", output)

        self.client.force_login(self.operator)
        board = self.client.get("/api/v1/transport-requests/dispatch-board/")
        self.assertEqual(board.status_code, 200)
        self.assertEqual(board.json()["requests"], [])
        self.assertEqual(board.json()["assignments"], [])
        self.assertEqual(board.json()["summary"]["ready_for_dispatch"], 0)

    @override_settings(TOMTOM_API_KEY="test-only-key")
    @patch("transport_requests.matrix._call_tomtom")
    def test_initial_dataset_does_not_enter_dispatch_recommendations(self, tomtom_mock):
        self.seed()
        result = dispatch.recommendations()

        tomtom_mock.assert_not_called()
        self.assertEqual(result["considered"], 0)
        self.assertEqual(result["recommendations"], [])
        self.assertEqual(DispatchAssignment.objects.count(), 0)

    def test_reset_is_idempotent_and_preserves_unrelated_rows(self):
        unrelated_vehicle = Vehicle.objects.create(
            device_id="REAL-V001",
            plate_number="REAL-001",
            display_name="Unrelated vehicle",
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=4,
        )
        unrelated_driver = Driver.objects.create(
            driver_code="REAL-DRIVER-001",
            first_name="Unrelated",
            last_name="Driver",
        )
        physical_event = TelemetryEvent.objects.create(
            schema_version="1.1",
            event_id="LOCAL-PHYSICAL-POSITION",
            sequence_number=1,
            vehicle=unrelated_vehicle,
            recorded_at=timezone.now(),
            location=Point(121.0, 14.5, srid=4326),
            position_source=TelemetryEvent.PositionSource.GNSS,
            gnss_speed_kph="0.00",
        )
        unrelated_request = TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference="LOCAL-SMOKE-REQUEST",
            request_type=TransportRequest.RequestType.GUEST_TRANSFER,
            request_category=TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            requester_name="Local smoke test",
            pickup_name="Local pickup",
            pickup_address="Local pickup",
            pickup_latitude="14.500000",
            pickup_longitude="121.000000",
            destination_name="Local destination",
            destination_address="Local destination",
            destination_latitude="14.600000",
            destination_longitude="121.100000",
            scheduled_pickup_at="2026-10-01T08:00:00Z",
            passenger_count=1,
            created_by=self.operator,
        )

        self.seed(count=10)
        self.seed(count=10)
        self.assertEqual(self.demo_requests().count(), 10)
        self.assertEqual(DispatchAssignment.objects.count(), 0)
        self.assertEqual(
            TelemetryEvent.objects.filter(event_id__startswith="DEMO-TRANSPORT-POSITION-").count(),
            10,
        )

        output = self.seed(count=10, reset=True)
        self.assertEqual(self.demo_requests().count(), 10)
        self.assertEqual(DispatchAssignment.objects.count(), 0)
        self.assertTrue(Vehicle.objects.filter(pk=unrelated_vehicle.pk).exists())
        self.assertTrue(Driver.objects.filter(pk=unrelated_driver.pk).exists())
        self.assertTrue(TransportRequest.objects.filter(pk=unrelated_request.pk).exists())
        self.assertTrue(TelemetryEvent.objects.filter(pk=physical_event.pk).exists())
        self.assertIn("Resetting local transport data", output)

    def test_full_local_reset_requires_confirmation_then_removes_all_requests(self):
        self.seed(count=10)
        unrelated_vehicle = Vehicle.objects.create(
            device_id="LOCAL-FLEET-KEEP",
            plate_number="KEEP-001",
            display_name="Preserved fleet resource",
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=4,
        )
        physical_event = TelemetryEvent.objects.create(
            schema_version="1.1",
            event_id="FULL-RESET-PHYSICAL-POSITION",
            sequence_number=1,
            vehicle=unrelated_vehicle,
            recorded_at=timezone.now(),
            location=Point(121.0, 14.5, srid=4326),
            position_source=TelemetryEvent.PositionSource.GNSS,
            gnss_speed_kph="0.00",
        )
        legacy = TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.RESTAURANT_MANAGEMENT_SYSTEM,
            external_reference="LEGACY-LOCAL-FOOD",
            request_type=TransportRequest.RequestType.FOOD_DELIVERY,
            request_category=TransportRequest.RequestCategory.DELIVERY_LOGISTICS,
            requester_name="Legacy local record",
            pickup_name="Legacy pickup",
            pickup_address="Legacy pickup",
            pickup_latitude="14.500000",
            pickup_longitude="121.000000",
            destination_name="Legacy destination",
            destination_address="Legacy destination",
            destination_latitude="14.600000",
            destination_longitude="121.100000",
            scheduled_pickup_at="2026-10-01T09:00:00Z",
            passenger_count=0,
            load_description="Legacy local test",
            created_by=self.operator,
        )

        with self.assertRaisesMessage(CommandError, "--confirm-local-demo-reset"):
            self.seed(count=10, full_local_transport_reset=True)
        self.assertTrue(TransportRequest.objects.filter(pk=legacy.pk).exists())

        output = self.seed(
            count=10,
            full_local_transport_reset=True,
            confirm_local_demo_reset=True,
        )
        self.assertFalse(TransportRequest.objects.filter(pk=legacy.pk).exists())
        self.assertEqual(TransportRequest.objects.count(), 10)
        self.assertEqual(DispatchAssignment.objects.count(), 0)
        self.assertTrue(Vehicle.objects.filter(pk=unrelated_vehicle.pk).exists())
        self.assertTrue(TelemetryEvent.objects.filter(pk=physical_event.pk).exists())
        self.assertTrue(get_user_model().objects.filter(pk=self.operator.pk).exists())
        self.assertIn("would delete ALL local transport workflow data", output)

    @override_settings(DEBUG=False)
    def test_full_local_reset_refuses_non_debug_environment(self):
        with self.assertRaisesMessage(CommandError, "restricted to DEBUG"):
            self.seed(
                count=10,
                full_local_transport_reset=True,
                confirm_local_demo_reset=True,
            )

    @override_settings(DEBUG=False)
    def test_command_refuses_non_debug_environment(self):
        with self.assertRaisesMessage(CommandError, "restricted to DEBUG"):
            self.seed(count=10, reset=True)
