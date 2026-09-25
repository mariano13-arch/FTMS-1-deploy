from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Driver, Vehicle
from telemetry.models import DriverSafetyEvent, TelemetryEvent
from transport_requests.models import DispatchAssignment, TransportRequest


class DriverSafetyCalibrationReportTests(TestCase):
    endpoint = "/api/v1/reports/driver-safety-calibration/"

    def setUp(self):
        self.now = timezone.now()
        self.user = get_user_model().objects.create_user(
            username="calibration-manager", is_staff=True
        )
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.FLEET_MANAGER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.counter = 0

    def make_driver(self):
        self.counter += 1
        driver = Driver.objects.create(
            driver_code=f"CAL-DRIVER-{self.counter}",
            first_name="Calibration",
            last_name=str(self.counter),
        )
        vehicle = Vehicle.objects.create(
            device_id=f"CAL-VEHICLE-{self.counter}",
            plate_number=f"CAL-{self.counter}",
            display_name=f"Calibration Vehicle {self.counter}",
        )
        return driver, vehicle

    def make_assignment(
        self,
        driver,
        vehicle,
        *,
        minutes=20,
        execution_status=DispatchAssignment.ExecutionStatus.COMPLETED,
        request_status=TransportRequest.Status.READY_FOR_DISPATCH,
        completed=True,
    ):
        self.counter += 1
        start = self.now - timedelta(days=1, hours=self.counter)
        end = start + timedelta(minutes=minutes) if completed else None
        request = TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.MANUAL_STAFF_ENTRY,
            external_reference=f"CAL-REQUEST-{self.counter}",
            request_type=TransportRequest.RequestType.GUEST_TRANSFER,
            request_category=TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            requester_name="Calibration",
            pickup_name="Pickup",
            pickup_address="Pickup address",
            pickup_latitude="14.500000",
            pickup_longitude="121.000000",
            destination_name="Destination",
            destination_address="Destination address",
            destination_latitude="14.600000",
            destination_longitude="121.100000",
            scheduled_pickup_at=self.now,
            passenger_count=1,
            status=request_status,
            assigned_vehicle=vehicle,
            created_by=self.user,
        )
        return DispatchAssignment.objects.create(
            transport_request=request,
            vehicle=vehicle,
            driver=driver,
            selection_mode=DispatchAssignment.SelectionMode.MANUAL,
            override_reason="Calibration test",
            confirmed_by=self.user,
            execution_status=execution_status,
            execution_started_at=start,
            completed_at=end,
        )

    def make_eligible(self, driver, vehicle, *, minutes=20):
        return [
            self.make_assignment(driver, vehicle, minutes=minutes) for _ in range(3)
        ]

    def make_event(self, assignment, event_type):
        self.counter += 1
        telemetry = TelemetryEvent.objects.create(
            schema_version="1.2",
            event_id=f"calibration-event-{self.counter}",
            sequence_number=self.counter,
            vehicle=assignment.vehicle,
            recorded_at=assignment.execution_started_at,
            location=Point(121.0, 14.5, srid=4326),
            position_source=TelemetryEvent.PositionSource.GNSS,
            position_accuracy_m=None,
            gnss_speed_kph=30,
            rpm=None,
            coolant_c=None,
            engine_load_pct=None,
            obd_source=None,
            driving_event=event_type,
        )
        return DriverSafetyEvent.objects.create(
            telemetry_event=telemetry,
            assignment=assignment,
            driver=assignment.driver,
            vehicle=assignment.vehicle,
            event_type=event_type,
            occurred_at=telemetry.recorded_at,
        )

    def summary(self, **params):
        response = self.client.get(self.endpoint, params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_empty_database_returns_zero_counts_and_null_distribution(self):
        data = self.summary()

        self.assertEqual(data["meta"]["period"], "ALL_TIME")
        self.assertEqual(data["summary"]["total_drivers"], 0)
        self.assertEqual(data["summary"]["exposure_eligible_drivers"], 0)
        self.assertEqual(data["summary"]["total_attributed_eligible_harsh_events"], 0)
        self.assertEqual(
            data["summary"]["events_per_driving_hour"],
            {"minimum": None, "median": None, "mean": None, "maximum": None},
        )

    def test_ineligible_driver_is_excluded(self):
        driver, vehicle = self.make_driver()
        self.make_assignment(driver, vehicle, minutes=30)
        self.make_assignment(driver, vehicle, minutes=30)

        summary = self.summary()["summary"]

        self.assertEqual(summary["total_drivers"], 1)
        self.assertEqual(summary["exposure_eligible_drivers"], 0)
        self.assertEqual(summary["total_eligible_completed_trips"], 0)

    def test_eligible_zero_event_driver_is_included(self):
        driver, vehicle = self.make_driver()
        self.make_eligible(driver, vehicle)

        summary = self.summary()["summary"]

        self.assertEqual(summary["exposure_eligible_drivers"], 1)
        self.assertEqual(summary["eligible_drivers_with_zero_harsh_events"], 1)
        self.assertEqual(summary["eligible_drivers_with_harsh_events"], 0)
        self.assertEqual(summary["total_eligible_completed_trips"], 3)
        self.assertEqual(summary["total_eligible_driving_hours"], 1.0)

    def test_eligible_harsh_event_driver_is_counted(self):
        driver, vehicle = self.make_driver()
        assignments = self.make_eligible(driver, vehicle)
        self.make_event(assignments[0], TelemetryEvent.DrivingEvent.HARSH_BRAKING)

        data = self.summary(
            date_from=(self.now - timedelta(days=10)).date(),
            date_to=(self.now + timedelta(days=1)).date(),
        )
        summary = data["summary"]

        self.assertEqual(data["meta"]["period"], "FILTERED")
        self.assertEqual(summary["eligible_drivers_with_harsh_events"], 1)
        self.assertEqual(summary["total_attributed_eligible_harsh_events"], 1)

    def test_event_type_totals_are_factual_counts(self):
        driver, vehicle = self.make_driver()
        assignments = self.make_eligible(driver, vehicle)
        for event_type in (
            TelemetryEvent.DrivingEvent.HARSH_ACCELERATION,
            TelemetryEvent.DrivingEvent.HARSH_BRAKING,
            TelemetryEvent.DrivingEvent.SHARP_TURN,
        ):
            self.make_event(assignments[0], event_type)

        counts = self.summary()["summary"]["event_type_counts"]

        self.assertEqual(
            counts,
            {"HARSH_ACCELERATION": 1, "HARSH_BRAKING": 1, "SHARP_TURN": 1},
        )

    def test_events_per_hour_distribution(self):
        zero_driver, zero_vehicle = self.make_driver()
        self.make_eligible(zero_driver, zero_vehicle)
        event_driver, event_vehicle = self.make_driver()
        assignments = self.make_eligible(event_driver, event_vehicle, minutes=40)
        for _ in range(4):
            self.make_event(assignments[0], TelemetryEvent.DrivingEvent.SHARP_TURN)

        distribution = self.summary()["summary"]["events_per_driving_hour"]

        self.assertEqual(
            distribution,
            {"minimum": 0.0, "median": 1.0, "mean": 1.0, "maximum": 2.0},
        )

    def test_other_driver_and_ineligible_assignment_events_are_excluded(self):
        eligible_driver, eligible_vehicle = self.make_driver()
        eligible = self.make_eligible(eligible_driver, eligible_vehicle)
        self.make_event(eligible[0], TelemetryEvent.DrivingEvent.HARSH_BRAKING)
        other_driver, other_vehicle = self.make_driver()
        other_assignment = self.make_assignment(other_driver, other_vehicle, minutes=60)
        self.make_event(
            other_assignment, TelemetryEvent.DrivingEvent.HARSH_ACCELERATION
        )

        summary = self.summary()["summary"]

        self.assertEqual(summary["exposure_eligible_drivers"], 1)
        self.assertEqual(summary["total_attributed_eligible_harsh_events"], 1)
        self.assertEqual(summary["event_type_counts"]["HARSH_ACCELERATION"], 0)

    def test_cancelled_and_incomplete_exposure_is_excluded(self):
        driver, vehicle = self.make_driver()
        self.make_assignment(driver, vehicle, minutes=30)
        self.make_assignment(driver, vehicle, minutes=30)
        self.make_assignment(
            driver,
            vehicle,
            minutes=60,
            request_status=TransportRequest.Status.CANCELLED,
        )
        self.make_assignment(
            driver,
            vehicle,
            execution_status=DispatchAssignment.ExecutionStatus.IN_TRANSIT,
            completed=False,
        )

        summary = self.summary()["summary"]

        self.assertEqual(summary["exposure_eligible_drivers"], 0)
        self.assertEqual(summary["total_eligible_completed_trips"], 0)
