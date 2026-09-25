from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Driver, Vehicle
from transport_requests.models import DispatchAssignment, TransportRequest


class FleetAssignmentReportTests(TestCase):
    endpoint = "/api/v1/reports/fleet-assignments/"

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="fleet-reporter", is_staff=True)
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.FLEET_MANAGER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.vehicle = Vehicle.objects.create(
            device_id="VEH-1",
            plate_number="RPT-1",
            display_name="=Alpha Van",
            vehicle_type=Vehicle.VehicleType.VAN,
            fuel_type=Vehicle.FuelType.GASOLINE,
            fuel_grade=Vehicle.FuelGrade.UNLEADED_91,
        )
        self.zero_vehicle = Vehicle.objects.create(
            device_id="VEH-2",
            plate_number="RPT-2",
            display_name="Zero SUV",
            vehicle_type=Vehicle.VehicleType.SUV,
            is_active=False,
        )
        self.driver = Driver.objects.create(
            driver_code="DRV-1",
            first_name="=Maria",
            last_name="Reyes",
            email="secret@example.com",
            contact_number="SECRET",
            license_number="PRIVATE",
        )
        self.zero_driver = Driver.objects.create(
            driver_code="DRV-2",
            first_name="No",
            last_name="Trips",
            employment_status=Driver.EmploymentStatus.ON_LEAVE,
        )
        self.moment = datetime(2026, 9, 20, 4, tzinfo=dt_timezone.utc)

    def assignment(self, suffix, *, vehicle=None, driver=None, **values):
        request = TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference=f"FA-{suffix}",
            request_type=TransportRequest.RequestType.GUEST_TRANSFER,
            request_category=TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            requester_name="Private",
            requester_contact="SECRET",
            pickup_name="Hotel",
            pickup_address="PRIVATE",
            pickup_latitude="14.5",
            pickup_longitude="121",
            destination_name="Airport",
            destination_address="PRIVATE",
            destination_latitude="14.4",
            destination_longitude="121",
            scheduled_pickup_at=self.moment,
            passenger_count=1,
            status=TransportRequest.Status.READY_FOR_DISPATCH,
            assigned_vehicle=vehicle or self.vehicle,
            created_by=self.user,
        )
        defaults = {
            "transport_request": request,
            "vehicle": vehicle or self.vehicle,
            "driver": driver or self.driver,
            "selection_mode": DispatchAssignment.SelectionMode.OPTIMIZED,
            "confirmed_by": self.user,
            "confirmed_at": self.moment,
        }
        defaults.update(values)
        return DispatchAssignment.objects.create(**defaults)

    def get(self, **params):
        return self.client.get(
            self.endpoint, {"date_from": "2026-09-20", "date_to": "2026-09-20", **params}
        )

    def test_authoritative_kpis_boundaries_trend_and_breakdowns(self):
        self.assignment("CURRENT")
        self.assignment(
            "DONE",
            execution_status=DispatchAssignment.ExecutionStatus.COMPLETED,
            completed_at=self.moment + timedelta(hours=2),
        )
        self.assignment(
            "OUTSIDE",
            confirmed_at=self.moment - timedelta(days=2),
            execution_status=DispatchAssignment.ExecutionStatus.COMPLETED,
            completed_at=self.moment - timedelta(days=2),
        )
        data = self.get().json()
        self.assertEqual(
            data["summary"],
            {
                "active_vehicles": 1,
                "active_drivers": 1,
                "assignments_confirmed": 2,
                "completed_trips": 1,
                "currently_assigned_vehicles": 1,
            },
        )
        self.assertEqual(data["trend"], [{"date": "2026-09-20", "count": 2}])
        self.assertEqual(data["breakdowns"]["by_vehicle"][0]["count"], 2)
        self.assertEqual(data["breakdowns"]["by_driver"][0]["count"], 2)
        self.assertEqual(data["breakdowns"]["by_vehicle_type"][0]["value"], "VAN")
        self.assertTrue({"utilization", "safety_score", "telemetry"}.isdisjoint(data))

    def test_zero_rows_current_and_latest_are_honest_and_private(self):
        current = self.assignment("CURRENT")
        latest = self.assignment(
            "LATEST",
            confirmed_at=self.moment + timedelta(hours=1),
            execution_status=DispatchAssignment.ExecutionStatus.COMPLETED,
            completed_at=self.moment + timedelta(hours=2),
        )
        data = self.get().json()
        vehicles = {row["identifier"]: row for row in data["vehicles"]["results"]}
        drivers = {row["driver_code"]: row for row in data["drivers"]["results"]}
        self.assertEqual(vehicles["VEH-1"]["current_assignment"]["id"], current.pk)
        self.assertEqual(vehicles["VEH-1"]["latest_assignment"]["id"], latest.pk)
        self.assertEqual(vehicles["VEH-1"]["fuel_type"], "GASOLINE")
        self.assertEqual(vehicles["VEH-1"]["fuel_grade"], "UNLEADED_91")
        self.assertEqual(vehicles["VEH-2"]["assignments"], 0)
        self.assertEqual(drivers["DRV-2"]["assignments"], 0)
        self.assertTrue(
            {
                "email",
                "contact_number",
                "license_number",
                "medical_certificate_expiry_date",
            }.isdisjoint(drivers["DRV-1"])
        )

    def test_filters_independent_pagination_and_limits(self):
        self.assignment("ONE")
        data = self.get(
            vehicle_search="Alpha",
            vehicle_type="VAN",
            vehicle_active="true",
            driver_search="Maria",
            employment_status="ACTIVE",
        ).json()
        self.assertEqual(data["vehicles"]["count"], 1)
        self.assertEqual(data["drivers"]["count"], 1)
        self.assertEqual(data["vehicles"]["page_size"], 15)
        self.assertEqual(data["drivers"]["page_size"], 15)
        self.assertEqual(self.get(page_size=101).status_code, 400)

    def test_csv_exports_filtered_rows_and_is_formula_safe(self):
        self.assignment("ONE")
        vehicle = self.client.get(
            "/api/v1/reports/fleet-assignments/vehicles/csv/",
            {"date_from": "2026-09-20", "date_to": "2026-09-20", "vehicle_type": "VAN"},
        )
        driver = self.client.get(
            "/api/v1/reports/fleet-assignments/drivers/csv/",
            {"date_from": "2026-09-20", "date_to": "2026-09-20", "employment_status": "ACTIVE"},
        )
        vehicle_body = b"".join(vehicle.streaming_content).decode()
        driver_body = b"".join(driver.streaming_content).decode()
        self.assertIn("'=Alpha Van", vehicle_body)
        self.assertIn("Gasoline", vehicle_body)
        self.assertIn("Unleaded 91", vehicle_body)
        self.assertNotIn("VEH-2", vehicle_body)
        self.assertIn("'=Maria Reyes", driver_body)
        self.assertNotIn("secret@example.com", driver_body)
        self.assertNotIn("SECRET", driver_body)
