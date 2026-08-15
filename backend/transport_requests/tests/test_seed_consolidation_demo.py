from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from fleet.models import Driver, Vehicle
from fleet.serializers import driver_eligibility
from telemetry.models import TelemetryEvent
from transport_requests import dispatch, services
from transport_requests.models import (
    DispatchAssignment,
    DispatchPlan,
    DispatchPlanEvent,
    TransportRequest,
)


class SeedConsolidationDemoTests(TestCase):
    def setUp(self):
        self.operator = get_user_model().objects.create_superuser(
            username="consolidation-seed-admin", password="development-only"
        )
        self.vehicle = Vehicle.objects.create(
            device_id="DEV-LOG-001",
            plate_number="DVL-001",
            display_name="Supply Van 01",
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=3,
            payload_capacity_kg=Decimal("1200.00"),
            gvwr_kg=Decimal("3500.00"),
        )

    def seed(self, *, fresh=True):
        output = StringIO()
        origins = (
            [{"vehicle_id": self.vehicle.device_id, "latitude": 14.5, "longitude": 121.0}]
            if fresh
            else []
        )
        with patch(
            "transport_requests.management.commands.seed_consolidation_demo.matrix.eligible_vehicle_origins",
            return_value=origins,
        ):
            call_command("seed_consolidation_demo", stdout=output)
        return output.getvalue()

    def test_creates_truthful_deterministic_scenarios_without_operational_fakes(self):
        unrelated = TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.MANUAL_STAFF_ENTRY,
            external_reference="UNRELATED-MANUAL",
            request_type=TransportRequest.RequestType.GUEST_TRANSFER,
            request_category=TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            requester_name="Unrelated",
            pickup_name="Oxford Suites Makati",
            pickup_address="Makati",
            pickup_latitude="14.565200",
            pickup_longitude="121.028600",
            destination_name="NAIA",
            destination_address="Pasay",
            destination_latitude="14.508600",
            destination_longitude="121.019800",
            scheduled_pickup_at="2026-08-15T08:00:00Z",
            estimated_duration_minutes=60,
            required_vehicle_type=Vehicle.VehicleType.VAN,
            passenger_count=2,
            status=TransportRequest.Status.APPROVED,
            created_by=self.operator,
        )
        output = self.seed()
        drivers = Driver.objects.filter(driver_code__startswith="DEV-CONS-DRV-").order_by(
            "driver_code"
        )
        deliveries = TransportRequest.objects.filter(
            external_reference__startswith="DEV-CONS-REQ-"
        ).order_by("external_reference")
        self.assertEqual(drivers.count(), 3)
        self.assertEqual(
            [driver_eligibility(item)[0] for item in drivers],
            ["ELIGIBLE", "ELIGIBLE", "RESTRICTED"],
        )
        self.assertEqual(deliveries.count(), 4)
        self.assertFalse(deliveries.exclude(status=TransportRequest.Status.APPROVED).exists())
        self.assertFalse(
            deliveries.exclude(
                request_category=TransportRequest.RequestCategory.DELIVERY_LOGISTICS
            ).exists()
        )
        primary = list(deliveries[:2])
        self.assertTrue(all(item.estimated_weight_kg is not None for item in primary))
        self.assertTrue(all(item.pickup_latitude and item.destination_latitude for item in primary))
        self.assertTrue(all(item.scheduled_pickup_at for item in primary))
        self.assertLessEqual(
            sum(item.estimated_weight_kg for item in primary),
            self.vehicle.payload_capacity_kg,
        )
        self.assertTrue(
            all(item.required_vehicle_type == self.vehicle.vehicle_type for item in primary)
        )
        eligible_drivers = list(
            Driver.objects.filter(driver_code__in=("DEV-CONS-DRV-001", "DEV-CONS-DRV-002"))
        )
        for item in primary:
            self.assertFalse(services.allocation_conflicts(item, self.vehicle))
            self.assertTrue(
                all(not dispatch.driver_conflicts(item, driver) for driver in eligible_drivers)
            )
        overflow = deliveries.get(external_reference="DEV-CONS-REQ-003")
        self.assertGreater(
            sum(item.estimated_weight_kg for item in primary) + overflow.estimated_weight_kg,
            self.vehicle.payload_capacity_kg,
        )
        missing = deliveries.get(external_reference="DEV-CONS-REQ-004")
        self.assertIsNone(missing.estimated_weight_kg)
        self.assertIsNotNone(missing.load_quantity)
        passenger = TransportRequest.objects.get(external_reference="DEV-CONS-PAX-001")
        self.assertEqual(
            passenger.request_category,
            TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
        )
        self.assertEqual(TelemetryEvent.objects.count(), 0)
        self.assertEqual(DispatchAssignment.objects.count(), 0)
        self.assertEqual(DispatchPlan.objects.count(), 0)
        self.assertEqual(DispatchPlanEvent.objects.count(), 0)
        self.assertTrue(TransportRequest.objects.filter(pk=unrelated.pk).exists())
        self.assertIn("Selected real GIS Vehicle", output)
        for item in deliveries:
            self.assertIn(f"{item.external_reference} -> {item.request_number}", output)

    def test_rerun_is_idempotent_and_preserves_demo_history_and_manual_edits(self):
        self.seed()
        driver = Driver.objects.get(driver_code="DEV-CONS-DRV-001")
        driver.first_name = "Manually Edited"
        driver.save(update_fields=["first_name", "updated_at"])
        first = TransportRequest.objects.get(external_reference="DEV-CONS-REQ-001")
        plan = DispatchPlan.objects.create(
            vehicle=self.vehicle,
            driver=driver,
            confirmed_by=self.operator,
        )
        assignment = DispatchAssignment.objects.create(
            plan=plan,
            transport_request=first,
            vehicle=self.vehicle,
            driver=driver,
            selection_mode=DispatchAssignment.SelectionMode.OPTIMIZED,
            confirmed_by=self.operator,
        )
        first.assigned_vehicle = self.vehicle
        first.save(update_fields=["assigned_vehicle", "updated_at"])
        confirmed_schedule = first.scheduled_pickup_at
        original_count = TransportRequest.objects.count()
        second_output = self.seed()

        self.assertEqual(Driver.objects.filter(driver_code__startswith="DEV-CONS-DRV-").count(), 3)
        self.assertEqual(
            TransportRequest.objects.filter(external_reference__startswith="DEV-CONS-REQ-").count(),
            4,
        )
        self.assertEqual(TransportRequest.objects.count(), original_count)
        driver.refresh_from_db()
        first.refresh_from_db()
        self.assertEqual(driver.first_name, "Manually Edited")
        self.assertEqual(first.status, TransportRequest.Status.APPROVED)
        self.assertEqual(first.scheduled_pickup_at, confirmed_schedule)
        self.assertIn("Drivers: 0 created, 3 existing", second_output)
        self.assertEqual(TelemetryEvent.objects.count(), 0)
        self.assertTrue(DispatchAssignment.objects.filter(pk=assignment.pk).exists())
        self.assertTrue(DispatchPlan.objects.filter(pk=plan.pk).exists())

    def test_no_fresh_vehicle_reports_real_telemetry_blocker_without_creating_it(self):
        output = self.seed(fresh=False)
        self.assertIn("No fresh GIS-capable Vehicle is currently available", output)
        self.assertIn("Selected database-only Vehicle", output)
        self.assertEqual(TelemetryEvent.objects.count(), 0)
