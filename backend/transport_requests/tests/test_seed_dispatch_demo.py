from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from fleet.models import Driver, Vehicle, VehicleInspection
from fleet.serializers import driver_eligibility
from telemetry.models import TelemetryEvent
from transport_requests.models import DispatchAssignment, TransportRequest


class SeedDispatchDemoTests(TestCase):
    def setUp(self):
        self.operator = get_user_model().objects.create_superuser(
            username="seed-admin", password="development-only"
        )
        self.vehicle = Vehicle.objects.create(
            device_id="DEV-PAX-006",
            plate_number="DVP-006",
            display_name="Guest Van 01",
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=12,
        )
        VehicleInspection.objects.create(
            vehicle=self.vehicle,
            inspection_date=timezone.localdate(),
            inspection_type=VehicleInspection.InspectionType.PRE_TRIP,
            result=VehicleInspection.Result.PASSED,
            exterior_condition=VehicleInspection.Condition.OK,
            interior_condition=VehicleInspection.Condition.OK,
            tires_condition=VehicleInspection.Condition.OK,
            lights_condition=VehicleInspection.Condition.OK,
            brakes_condition=VehicleInspection.Condition.OK,
            fluids_condition=VehicleInspection.Condition.OK,
            safety_equipment_condition=VehicleInspection.Condition.OK,
            inspected_by=self.operator,
        )

    def seed(self):
        output = StringIO()
        call_command("seed_dispatch_demo", stdout=output)
        return output.getvalue()

    def test_seed_is_truthful_and_structurally_valid(self):
        unrelated = Driver.objects.create(
            driver_code="MANUAL-DRIVER", first_name="Manual", last_name="Record"
        )
        output = self.seed()
        drivers = Driver.objects.filter(driver_code__startswith="DEV-DRV-")
        requests = TransportRequest.objects.filter(external_reference__startswith="DEV-DISPATCH-")

        self.assertEqual(drivers.count(), 4)
        self.assertEqual(
            [driver_eligibility(driver)[0] for driver in drivers.order_by("driver_code")],
            ["ELIGIBLE", "ELIGIBLE", "RESTRICTED", "NOT_ELIGIBLE"],
        )
        self.assertEqual(requests.count(), 5)
        self.assertEqual(
            requests.filter(status=TransportRequest.Status.READY_FOR_DISPATCH).count(), 1
        )
        self.assertEqual(requests.filter(status=TransportRequest.Status.APPROVED).count(), 4)
        self.assertFalse(requests.filter(pickup_latitude__isnull=True).exists())
        self.assertFalse(requests.filter(destination_latitude__isnull=True).exists())
        self.assertFalse(requests.filter(passenger_count__lt=1).exists())
        self.assertEqual(TelemetryEvent.objects.count(), 0)
        self.assertEqual(DispatchAssignment.objects.count(), 1)
        self.assertTrue(Driver.objects.filter(pk=unrelated.pk).exists())
        self.assertIn("Drivers: 4 created", output)

    def test_rerun_is_idempotent_and_preserves_manual_edits(self):
        self.seed()
        driver = Driver.objects.get(driver_code="DEV-DRV-001")
        driver.first_name = "Manually Edited"
        driver.save(update_fields=["first_name", "updated_at"])
        output = self.seed()

        self.assertEqual(Driver.objects.filter(driver_code__startswith="DEV-DRV-").count(), 4)
        self.assertEqual(
            TransportRequest.objects.filter(external_reference__startswith="DEV-DISPATCH-").count(),
            5,
        )
        self.assertEqual(DispatchAssignment.objects.count(), 1)
        driver.refresh_from_db()
        self.assertEqual(driver.first_name, "Manually Edited")
        self.assertIn("Drivers: 0 created, 4 existing", output)
