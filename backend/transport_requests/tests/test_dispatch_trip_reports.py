from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Driver, Vehicle
from transport_requests.models import DispatchAssignment, TransportRequest


class DispatchTripReportTests(TestCase):
    endpoint = "/api/v1/reports/dispatch-trips/"
    csv_endpoint = "/api/v1/reports/dispatch-trips/csv/"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="report-dispatcher", is_staff=True
        )
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.DISPATCHER)
        self.driver = Driver.objects.create(
            driver_code="DRV-RPT-1", first_name="Maria", last_name="Reyes"
        )
        self.vehicle = Vehicle.objects.create(
            device_id="RPT-VEH-1",
            plate_number="RPT-1",
            display_name="Report Van",
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=8,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.moment = datetime(2026, 9, 20, 4, tzinfo=dt_timezone.utc)

    def assignment(self, suffix, status=DispatchAssignment.ExecutionStatus.ASSIGNED, **values):
        request = TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference=f"RPT-{suffix}",
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
            assigned_vehicle=self.vehicle,
            created_by=self.user,
        )
        defaults = {
            "transport_request": request,
            "vehicle": self.vehicle,
            "driver": self.driver,
            "selection_mode": DispatchAssignment.SelectionMode.OPTIMIZED,
            "confirmed_by": self.user,
            "confirmed_at": self.moment,
            "execution_status": status,
        }
        defaults.update(values)
        return DispatchAssignment.objects.create(**defaults)

    def get(self, **params):
        return self.client.get(
            self.endpoint, {"date_from": "2026-09-20", "date_to": "2026-09-20", **params}
        )

    def test_authorization_and_authoritative_kpis(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.endpoint).status_code, 401)
        self.client.force_authenticate(self.user)
        self.assignment("ASSIGNED")
        for index, status in enumerate(
            ("EN_ROUTE_TO_PICKUP", "AT_PICKUP", "IN_TRANSIT", "AT_DESTINATION")
        ):
            self.assignment(str(index), status=status, accepted_at=self.moment + timedelta(hours=1))
        self.assignment(
            "DONE",
            status="COMPLETED",
            execution_started_at=self.moment + timedelta(hours=1),
            completed_at=self.moment + timedelta(hours=3),
        )
        data = self.get().json()["summary"]
        self.assertEqual(data["assignments_confirmed"], 6)
        self.assertEqual(data["driver_acceptances"], 4)
        self.assertEqual(data["trips_in_progress"], 4)
        self.assertEqual(data["completed_trips"], 1)
        self.assertEqual(data["average_execution_duration_seconds"], 7200)

    def test_empty_average_boundaries_trend_and_breakdowns(self):
        self.assignment("FIRST", confirmed_at=datetime(2026, 9, 19, 16, tzinfo=dt_timezone.utc))
        self.assignment(
            "NEXT",
            confirmed_at=datetime(2026, 9, 20, 16, tzinfo=dt_timezone.utc),
            selection_mode="MANUAL",
            override_reason="Required",
        )
        data = self.get().json()
        self.assertEqual(data["summary"]["assignments_confirmed"], 1)
        self.assertIsNone(data["summary"]["average_execution_duration_seconds"])
        self.assertEqual(data["trend"], [{"date": "2026-09-20", "count": 1}])
        statuses = {row["value"]: row["count"] for row in data["breakdowns"]["by_execution_status"]}
        modes = {row["value"]: row["count"] for row in data["breakdowns"]["by_selection_mode"]}
        self.assertEqual(statuses["ASSIGNED"], 1)
        self.assertEqual(modes["OPTIMIZED"], 1)
        self.assertEqual(modes["MANUAL"], 0)

    def test_filters_search_pagination_and_safe_details(self):
        for index in range(16):
            self.assignment(str(index))
        data = self.get(
            search="RPT-VEH",
            vehicle=self.vehicle.pk,
            driver=self.driver.pk,
            execution_status="ASSIGNED",
            selection_mode="OPTIMIZED",
        ).json()
        self.assertEqual(data["details"]["count"], 16)
        self.assertEqual(len(data["details"]["results"]), 15)
        self.assertEqual(self.get(page=2).json()["details"]["page"], 2)
        self.assertEqual(self.get(page_size=101).status_code, 400)
        row = data["details"]["results"][0]
        self.assertTrue(
            {
                "contact_number",
                "email",
                "license_number",
                "requester_contact",
                "distance",
                "eta_accuracy",
                "lateness",
            }.isdisjoint(row)
        )
        self.assertIn("execution_duration", row["durations"])

    def test_csv_filters_all_rows_and_prevents_formula_injection(self):
        for index in range(16):
            self.assignment(str(index))
        dangerous = self.assignment("DANGER")
        TransportRequest.objects.filter(pk=dangerous.transport_request_id).update(
            request_number="=FORMULA"
        )
        response = self.client.get(
            self.csv_endpoint,
            {"date_from": "2026-09-20", "date_to": "2026-09-20", "selection_mode": "OPTIMIZED"},
        )
        body = b"".join(response.streaming_content).decode()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(body.strip().splitlines()), 18)
        self.assertIn("'=FORMULA", body)
        self.assertNotIn("SECRET", body)
        self.assertNotIn("PRIVATE", body)
