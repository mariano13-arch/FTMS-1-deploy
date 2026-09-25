from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.test import TestCase
from django.utils import timezone

from fleet.models import Driver, Vehicle
from telemetry.models import DriverSafetyEvent, TelemetryEvent
from telemetry.safety import attribute_driver_safety_event
from telemetry.services import IngestionStatus, ingest_telemetry
from transport_requests.models import DispatchAssignment, TransportRequest


class DriverSafetyAttributionTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.user = get_user_model().objects.create_user(username="safety-operator")
        self.driver = Driver.objects.create(
            driver_code="SAFETY-DRIVER-1", first_name="Ana", last_name="Reyes"
        )
        self.vehicle = self.make_vehicle("SAFETY-VEHICLE-1")
        self.assignment = self.make_assignment(
            "SAFETY-TRIP-1", self.vehicle, self.driver, self.now - timedelta(hours=1)
        )

    def make_vehicle(self, device_id):
        return Vehicle.objects.create(
            device_id=device_id,
            plate_number=device_id,
            display_name=device_id,
        )

    def make_assignment(self, reference, vehicle, driver, started_at):
        request = TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.MANUAL_STAFF_ENTRY,
            external_reference=reference,
            request_type=TransportRequest.RequestType.GUEST_TRANSFER,
            request_category=TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            requester_name="Safety test",
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
            status=TransportRequest.Status.READY_FOR_DISPATCH,
            assigned_vehicle=vehicle,
            created_by=self.user,
        )
        return DispatchAssignment.objects.create(
            transport_request=request,
            vehicle=vehicle,
            driver=driver,
            selection_mode=DispatchAssignment.SelectionMode.MANUAL,
            override_reason="Safety attribution test",
            confirmed_by=self.user,
            accepted_at=started_at,
            execution_status=DispatchAssignment.ExecutionStatus.IN_TRANSIT,
            execution_started_at=started_at,
        )

    def make_event(self, event_id, *, vehicle=None, recorded_at=None, driving_event=None):
        return TelemetryEvent.objects.create(
            schema_version="1.2",
            event_id=event_id,
            sequence_number=1,
            vehicle=vehicle or self.vehicle,
            recorded_at=recorded_at or self.now,
            location=Point(121.0, 14.5, srid=4326),
            position_source=TelemetryEvent.PositionSource.GNSS,
            position_accuracy_m=None,
            gnss_speed_kph=30,
            rpm=None,
            coolant_c=None,
            engine_load_pct=None,
            obd_source=None,
            driving_event=(
                TelemetryEvent.DrivingEvent.HARSH_BRAKING
                if driving_event is None
                else driving_event
            ),
        )

    def test_harsh_event_during_assignment_is_attributed(self):
        event = self.make_event("safety-during")

        result = attribute_driver_safety_event(event)

        self.assertEqual(result.driver, self.driver)
        self.assertEqual(result.vehicle, self.vehicle)
        self.assertEqual(result.assignment, self.assignment)
        self.assertEqual(result.event_type, TelemetryEvent.DrivingEvent.HARSH_BRAKING)
        self.assertEqual(result.occurred_at, event.recorded_at)

    def test_event_before_assignment_is_not_attributed(self):
        event = self.make_event(
            "safety-before", recorded_at=self.assignment.execution_started_at - timedelta(seconds=1)
        )

        self.assertIsNone(attribute_driver_safety_event(event))
        self.assertFalse(DriverSafetyEvent.objects.exists())

    def test_event_after_completed_assignment_is_not_attributed(self):
        self.assignment.execution_status = DispatchAssignment.ExecutionStatus.COMPLETED
        self.assignment.completed_at = self.now - timedelta(seconds=1)
        self.assignment.save(update_fields=["execution_status", "completed_at", "updated_at"])
        event = self.make_event("safety-after")

        self.assertIsNone(attribute_driver_safety_event(event))
        self.assertFalse(DriverSafetyEvent.objects.exists())

    def test_null_driving_event_creates_no_safety_event(self):
        event = self.make_event("safety-null", driving_event=None)
        event.driving_event = None
        event.save(update_fields=["driving_event"])

        self.assertIsNone(attribute_driver_safety_event(event))
        self.assertFalse(DriverSafetyEvent.objects.exists())

    def test_processing_same_telemetry_twice_is_idempotent(self):
        payload = {
            "schema_version": "1.2",
            "event_id": "safety-idempotent",
            "sequence_number": 2,
            "device_id": self.vehicle.device_id,
            "recorded_at": self.now.isoformat(),
            "latitude": 14.5,
            "longitude": 121.0,
            "position_source": "GNSS",
            "position_accuracy_m": None,
            "gnss_speed_kph": 30,
            "rpm": None,
            "coolant_c": None,
            "engine_load_pct": None,
            "obd_source": None,
            "driving_event": "HARSH_ACCELERATION",
        }

        first = ingest_telemetry(payload)
        second = ingest_telemetry(payload)

        self.assertEqual(first.status, IngestionStatus.CREATED)
        self.assertEqual(second.status, IngestionStatus.DUPLICATE)
        self.assertEqual(DriverSafetyEvent.objects.count(), 1)

    def test_assignment_for_another_vehicle_is_never_used(self):
        other_vehicle = self.make_vehicle("SAFETY-VEHICLE-2")
        event = self.make_event("safety-other-vehicle", vehicle=other_vehicle)

        self.assertIsNone(attribute_driver_safety_event(event))
        self.assertFalse(DriverSafetyEvent.objects.exists())

    def test_multiple_matching_assignments_remain_unattributed(self):
        other_driver = Driver.objects.create(
            driver_code="SAFETY-DRIVER-2", first_name="Ben", last_name="Santos"
        )
        self.make_assignment(
            "SAFETY-TRIP-2",
            self.vehicle,
            other_driver,
            self.now - timedelta(minutes=30),
        )
        event = self.make_event("safety-ambiguous")

        self.assertIsNone(attribute_driver_safety_event(event))
        self.assertFalse(DriverSafetyEvent.objects.exists())
