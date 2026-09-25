from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.test import TestCase
from django.utils import timezone

from fleet.models import Driver, Vehicle
from fleet.safety import safety_metrics_for_drivers
from fleet.serializers import DriverSerializer
from telemetry.models import DriverSafetyEvent, TelemetryEvent
from transport_requests.models import DispatchAssignment, TransportRequest


class DriverSafetyMetricsTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.user = get_user_model().objects.create_user(username="metrics-operator")
        self.driver = Driver.objects.create(
            driver_code="METRICS-DRIVER-1", first_name="Ana", last_name="Reyes"
        )
        self.other_driver = Driver.objects.create(
            driver_code="METRICS-DRIVER-2", first_name="Ben", last_name="Santos"
        )
        self.vehicle = Vehicle.objects.create(
            device_id="METRICS-VEHICLE-1",
            plate_number="METRICS-1",
            display_name="Metrics Vehicle",
        )
        self.counter = 0

    def make_assignment(
        self,
        *,
        driver=None,
        minutes=20,
        execution_status=DispatchAssignment.ExecutionStatus.COMPLETED,
        request_status=TransportRequest.Status.READY_FOR_DISPATCH,
        started=True,
        completed=True,
        valid_order=True,
    ):
        self.counter += 1
        driver = driver or self.driver
        start = self.now - timedelta(hours=self.counter + 1) if started else None
        end = start + timedelta(minutes=minutes) if start and completed else None
        if start and end and not valid_order:
            end = start - timedelta(minutes=1)
        request = TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.MANUAL_STAFF_ENTRY,
            external_reference=f"METRICS-{self.counter}",
            request_type=TransportRequest.RequestType.GUEST_TRANSFER,
            request_category=TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            requester_name="Metrics test",
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
            assigned_vehicle=self.vehicle,
            created_by=self.user,
        )
        return DispatchAssignment.objects.create(
            transport_request=request,
            vehicle=self.vehicle,
            driver=driver,
            selection_mode=DispatchAssignment.SelectionMode.MANUAL,
            override_reason="Safety metrics test",
            confirmed_by=self.user,
            execution_status=execution_status,
            execution_started_at=start,
            completed_at=end,
        )

    def make_safety_event(self, assignment, event_type):
        self.counter += 1
        occurred_at = assignment.execution_started_at or self.now
        telemetry = TelemetryEvent.objects.create(
            schema_version="1.2",
            event_id=f"metrics-event-{self.counter}",
            sequence_number=self.counter,
            vehicle=assignment.vehicle,
            recorded_at=occurred_at,
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
            occurred_at=occurred_at,
        )

    def metrics(self, driver=None):
        driver = driver or self.driver
        return safety_metrics_for_drivers([driver.pk])[driver.pk]

    def test_below_three_completed_trips_is_not_score_eligible(self):
        self.make_assignment(minutes=30)
        self.make_assignment(minutes=30)

        metrics = self.metrics()

        self.assertEqual(metrics.completed_trip_count, 2)
        self.assertEqual(metrics.total_driving_seconds, 3600)
        self.assertFalse(metrics.score_eligible)

    def test_three_trips_under_one_hour_is_not_score_eligible(self):
        for _ in range(3):
            self.make_assignment(minutes=19)

        metrics = self.metrics()

        self.assertEqual(metrics.completed_trip_count, 3)
        self.assertEqual(metrics.total_driving_seconds, 3420)
        self.assertFalse(metrics.score_eligible)

    def test_three_trips_and_one_hour_is_exposure_eligible_but_not_scored(self):
        for _ in range(3):
            self.make_assignment(minutes=20)

        metrics = self.metrics()
        data = DriverSerializer(
            self.driver, context={"safety_metrics": {self.driver.pk: metrics}}
        ).data

        self.assertTrue(metrics.score_eligible)
        self.assertEqual(metrics.total_driving_hours, 1.0)
        self.assertTrue(data["safety_score_eligible"])
        self.assertIsNone(data["safety_score"])
        self.assertEqual(data["safety_score_status"], "NOT_SCORED")

    def test_active_assignment_is_excluded(self):
        self.make_assignment(
            execution_status=DispatchAssignment.ExecutionStatus.IN_TRANSIT,
            completed=False,
        )

        self.assertEqual(self.metrics().completed_trip_count, 0)

    def test_cancelled_and_incomplete_assignments_are_excluded(self):
        self.make_assignment(request_status=TransportRequest.Status.CANCELLED)
        self.make_assignment(
            execution_status=DispatchAssignment.ExecutionStatus.ASSIGNED,
            completed=False,
        )

        self.assertEqual(self.metrics().completed_trip_count, 0)

    def test_missing_or_invalid_execution_timestamps_are_excluded(self):
        self.make_assignment(started=False, completed=False)
        self.make_assignment(completed=False)
        self.make_assignment(valid_order=False)

        self.assertEqual(self.metrics().completed_trip_count, 0)
        self.assertEqual(self.metrics().total_driving_seconds, 0)

    def test_events_count_only_for_eligible_completed_assignments(self):
        eligible = self.make_assignment(minutes=60)
        active = self.make_assignment(
            execution_status=DispatchAssignment.ExecutionStatus.IN_TRANSIT,
            completed=False,
        )
        self.make_safety_event(eligible, TelemetryEvent.DrivingEvent.HARSH_BRAKING)
        self.make_safety_event(active, TelemetryEvent.DrivingEvent.SHARP_TURN)

        metrics = self.metrics()

        self.assertEqual(metrics.attributed_harsh_event_count, 1)
        self.assertEqual(metrics.harsh_braking_count, 1)
        self.assertEqual(metrics.sharp_turn_count, 0)

    def test_event_counts_are_separated_by_type(self):
        assignment = self.make_assignment(minutes=60)
        self.make_safety_event(
            assignment, TelemetryEvent.DrivingEvent.HARSH_ACCELERATION
        )
        self.make_safety_event(assignment, TelemetryEvent.DrivingEvent.HARSH_BRAKING)
        self.make_safety_event(assignment, TelemetryEvent.DrivingEvent.SHARP_TURN)

        metrics = self.metrics()

        self.assertEqual(metrics.attributed_harsh_event_count, 3)
        self.assertEqual(metrics.harsh_acceleration_count, 1)
        self.assertEqual(metrics.harsh_braking_count, 1)
        self.assertEqual(metrics.sharp_turn_count, 1)

    def test_events_per_driving_hour_is_calculated(self):
        assignment = self.make_assignment(minutes=90)
        for event_type in (
            TelemetryEvent.DrivingEvent.HARSH_ACCELERATION,
            TelemetryEvent.DrivingEvent.HARSH_BRAKING,
            TelemetryEvent.DrivingEvent.SHARP_TURN,
        ):
            self.make_safety_event(assignment, event_type)

        metrics = self.metrics()

        self.assertEqual(metrics.total_driving_seconds, 5400)
        self.assertAlmostEqual(metrics.harsh_events_per_driving_hour, 2.0)

    def test_another_drivers_events_are_never_counted(self):
        own_assignment = self.make_assignment(minutes=60)
        other_assignment = self.make_assignment(driver=self.other_driver, minutes=60)
        self.make_safety_event(
            own_assignment, TelemetryEvent.DrivingEvent.HARSH_BRAKING
        )
        self.make_safety_event(
            other_assignment, TelemetryEvent.DrivingEvent.HARSH_ACCELERATION
        )

        own = self.metrics()
        other = self.metrics(self.other_driver)

        self.assertEqual(own.attributed_harsh_event_count, 1)
        self.assertEqual(own.harsh_acceleration_count, 0)
        self.assertEqual(other.attributed_harsh_event_count, 1)
        self.assertEqual(other.harsh_acceleration_count, 1)
