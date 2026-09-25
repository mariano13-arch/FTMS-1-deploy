from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point, Polygon
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Driver, DriverSafetyDemoEvent, DriverSafetyDemoProfile, Vehicle
from telemetry.models import (
    DriverSafetyEvent,
    Geofence,
    GeofenceEvent,
    TelemetryDeviceBinding,
    TelemetryEvent,
    VehicleEmergencySOS,
)
from transport_requests.models import DispatchAssignment, TransportRequest


class SafetyGeofenceReportTests(TestCase):
    endpoint = "/api/v1/reports/safety-geofence/"

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="safety-reporter", is_staff=True)
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.FLEET_MANAGER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.vehicle = Vehicle.objects.create(
            device_id="SAFE-1", plate_number="SAFE-1", display_name="=Safety Van"
        )
        self.driver = Driver.objects.create(
            driver_code="SAFE-DRV", first_name="Safe", last_name="Driver"
        )
        request = TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference="SAFE-REPORT",
            request_type=TransportRequest.RequestType.GUEST_TRANSFER,
            request_category=TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            requester_name="Reporter",
            pickup_name="Hotel",
            pickup_address="Address",
            pickup_latitude="14.5",
            pickup_longitude="121",
            destination_name="Airport",
            destination_address="Address",
            destination_latitude="14.4",
            destination_longitude="121",
            scheduled_pickup_at=datetime(2026, 9, 20, 4, tzinfo=dt_timezone.utc),
            passenger_count=1,
            status=TransportRequest.Status.READY_FOR_DISPATCH,
            assigned_vehicle=self.vehicle,
            created_by=self.user,
        )
        self.assignment = DispatchAssignment.objects.create(
            transport_request=request,
            vehicle=self.vehicle,
            driver=self.driver,
            selection_mode=DispatchAssignment.SelectionMode.MANUAL,
            override_reason="Report fixture",
            confirmed_by=self.user,
            confirmed_at=datetime(2026, 9, 20, 3, tzinfo=dt_timezone.utc),
        )
        self.device = TelemetryDeviceBinding.objects.get(
            vehicle=self.vehicle, unpaired_at__isnull=True
        ).device
        self.moment = datetime(2026, 9, 19, 16, tzinfo=dt_timezone.utc)
        boundary = Polygon(
            (
                (121.00, 14.50),
                (121.02, 14.50),
                (121.02, 14.52),
                (121.00, 14.52),
                (121.00, 14.50),
            ),
            srid=4326,
        )
        self.restricted = Geofence.objects.create(
            name="=Restricted Yard",
            category=Geofence.Category.RESTRICTED,
            shape_type=Geofence.ShapeType.POLYGON,
            boundary=boundary,
            center=Point(121.01, 14.51, srid=4326),
            created_by=self.user,
        )
        self.hotel = Geofence.objects.create(
            name="Hotel",
            category=Geofence.Category.HOTEL,
            shape_type=Geofence.ShapeType.POLYGON,
            boundary=boundary,
            center=Point(121.01, 14.51, srid=4326),
            created_by=self.user,
        )

    def telemetry(self, suffix, driving_event, **values):
        operational = values.pop("operational", True)
        defaults = {
            "schema_version": "1.2",
            "event_id": f"event-{suffix}",
            "sequence_number": int(suffix) if suffix.isdigit() else 100,
            "device": self.device,
            "vehicle": self.vehicle,
            "recorded_at": self.moment,
            "location": Point(121.01, 14.51, srid=4326),
            "position_source": TelemetryEvent.PositionSource.GNSS,
            "gnss_speed_kph": 30,
            "rpm": 1800,
            "coolant_c": 88,
            "engine_load_pct": 40,
            "obd_source": TelemetryEvent.ObdSource.PHYSICAL_OBD,
            "driving_event": driving_event,
        }
        defaults.update(values)
        event = TelemetryEvent.objects.create(**defaults)
        if operational and driving_event in {
            TelemetryEvent.DrivingEvent.HARSH_BRAKING,
            TelemetryEvent.DrivingEvent.HARSH_ACCELERATION,
            TelemetryEvent.DrivingEvent.SHARP_TURN,
        }:
            DriverSafetyEvent.objects.get_or_create(
                telemetry_event=event,
                defaults={
                    "assignment": self.assignment,
                    "driver": self.driver,
                    "vehicle": self.vehicle,
                    "event_type": driving_event,
                    "occurred_at": event.recorded_at,
                },
            )
        return event

    def geofence_event(self, telemetry, geofence, event_type):
        return GeofenceEvent.objects.create(
            geofence=geofence,
            vehicle=self.vehicle,
            telemetry_event=telemetry,
            event_type=event_type,
            occurred_at=telemetry.recorded_at,
            location=telemetry.location,
        )

    def get(self, **params):
        return self.client.get(
            self.endpoint,
            {"date_from": "2026-09-20", "date_to": "2026-09-20", **params},
        )

    def test_authoritative_safety_counts_date_trend_and_provenance(self):
        self.telemetry("1", TelemetryEvent.DrivingEvent.NORMAL)
        self.telemetry("2", TelemetryEvent.DrivingEvent.HARSH_BRAKING)
        self.telemetry("3", TelemetryEvent.DrivingEvent.HARSH_ACCELERATION)
        self.telemetry(
            "4",
            TelemetryEvent.DrivingEvent.SHARP_TURN,
            position_source=TelemetryEvent.PositionSource.SIMULATED_TEST,
            gnss_speed_kph=None,
            rpm=None,
            coolant_c=None,
            engine_load_pct=None,
            obd_source=None,
            operational=False,
        )
        self.telemetry(
            "5",
            TelemetryEvent.DrivingEvent.HARSH_BRAKING,
            recorded_at=self.moment - timedelta(seconds=1),
        )
        data = self.get().json()
        self.assertEqual(data["summary"]["safety_events"], 2)
        self.assertEqual(data["summary"]["harsh_braking"], 1)
        self.assertEqual(data["summary"]["harsh_acceleration"], 1)
        self.assertEqual(data["summary"]["sharp_turns"], 0)
        self.assertEqual(data["safety_trend"], [{"date": "2026-09-20", "count": 2}])
        sources = {row["value"]: row["count"] for row in data["breakdowns"]["position_sources"]}
        self.assertEqual(sources["GNSS"], 2)
        self.assertEqual(sources["SIMULATED_TEST"], 0)
        self.assertNotIn("NORMAL", {row["event_type"] for row in data["safety_events"]["results"]})

    def test_geofence_kpis_require_exact_restricted_enter_derivation(self):
        first = self.telemetry("10", TelemetryEvent.DrivingEvent.NORMAL)
        second = self.telemetry("11", TelemetryEvent.DrivingEvent.NORMAL)
        third = self.telemetry("12", TelemetryEvent.DrivingEvent.NORMAL)
        restricted_enter = self.geofence_event(
            first, self.restricted, GeofenceEvent.EventType.ENTER
        )
        self.geofence_event(second, self.restricted, GeofenceEvent.EventType.EXIT)
        self.geofence_event(third, self.hotel, GeofenceEvent.EventType.ENTER)
        data = self.get().json()
        self.assertEqual(data["summary"]["geofence_activity"], 3)
        self.assertEqual(data["summary"]["restricted_entries"], 1)
        events = {row["id"]: row for row in data["geofence_activity"]["results"]}
        self.assertEqual(
            events[restricted_enter.pk]["display_classification"], "Restricted Zone Entry"
        )
        ordinary = [row for row in events.values() if row["geofence"]["category"] == "HOTEL"][0]
        self.assertEqual(ordinary["display_classification"], "Enter")
        breakdown = {row["value"]: row["count"] for row in data["breakdowns"]["geofence_events"]}
        self.assertEqual(breakdown, {"ENTER": 2, "EXIT": 1})
        self.assertEqual(data["geofence_trend"][0]["enter"], 2)
        self.assertEqual(data["geofence_trend"][0]["exit"], 1)

    def test_filters_pagination_privacy_and_no_invented_fields(self):
        safety = self.telemetry("20", TelemetryEvent.DrivingEvent.HARSH_BRAKING)
        self.geofence_event(safety, self.restricted, GeofenceEvent.EventType.ENTER)
        data = self.get(
            safety_event_type="HARSH_BRAKING",
            safety_vehicle=self.vehicle.pk,
            position_source="GNSS",
            obd_source="PHYSICAL_OBD",
            safety_search="SAFE-1",
            geofence_event_type="ENTER",
            category="RESTRICTED",
            geofence=self.restricted.pk,
            geofence_vehicle=self.vehicle.pk,
            geofence_position_source="GNSS",
            geofence_search="Restricted",
        ).json()
        self.assertEqual(data["safety_events"]["count"], 1)
        self.assertEqual(data["geofence_activity"]["count"], 1)
        self.assertEqual(data["safety_events"]["page_size"], 15)
        self.assertEqual(data["geofence_activity"]["page_size"], 15)
        safety_row = data["safety_events"]["results"][0]
        self.assertEqual(safety_row["driver"]["code"], "SAFE-DRV")
        self.assertEqual(
            safety_row["assignment"]["request_number"],
            self.assignment.transport_request.request_number,
        )
        self.assertTrue(
            {"severity", "acknowledged", "resolved", "latitude", "longitude"}.isdisjoint(safety_row)
        )
        self.assertEqual(self.get(page_size=101).status_code, 400)

    def test_csv_is_filtered_formula_safe_and_location_minimized(self):
        safety = self.telemetry("30", TelemetryEvent.DrivingEvent.HARSH_BRAKING)
        self.telemetry("31", TelemetryEvent.DrivingEvent.NORMAL)
        self.geofence_event(safety, self.restricted, GeofenceEvent.EventType.ENTER)
        params = {"date_from": "2026-09-20", "date_to": "2026-09-20"}
        safety_response = self.client.get("/api/v1/reports/safety-geofence/safety/csv/", params)
        geofence_response = self.client.get(
            "/api/v1/reports/safety-geofence/geofence/csv/",
            {**params, "category": "RESTRICTED"},
        )
        safety_body = b"".join(safety_response.streaming_content).decode()
        geofence_body = b"".join(geofence_response.streaming_content).decode()
        self.assertIn("Harsh Braking", safety_body)
        self.assertNotIn("Normal", safety_body)
        self.assertIn("'=Safety Van", safety_body)
        self.assertIn("'=Restricted Yard", geofence_body)
        self.assertIn("Restricted Zone Entry", geofence_body)
        self.assertNotIn("121.01", safety_body + geofence_body)
        self.assertIn("Operational", safety_body)

    def test_demo_rows_and_raw_telemetry_do_not_contaminate_operational_safety(self):
        raw = self.telemetry("40", TelemetryEvent.DrivingEvent.HARSH_BRAKING, operational=False)
        profile = DriverSafetyDemoProfile.objects.create(
            driver=self.driver,
            safety_score=90,
            completed_trip_count=2,
            driving_hours="1.0",
            safety_event_count=1,
            source=DriverSafetyDemoProfile.Source.DEMO_SEED,
            generated_at=self.moment,
        )
        DriverSafetyDemoEvent.objects.create(
            profile=profile, sequence=1, event_type="HARSH_BRAKING", occurred_at=self.moment
        )
        self.assertIsNotNone(raw.pk)
        data = self.get().json()
        self.assertEqual(data["summary"]["safety_events"], 0)
        self.assertEqual(data["safety_events"]["count"], 0)

    def test_sos_is_factual_and_has_no_location(self):
        active = VehicleEmergencySOS.objects.create(
            device=self.device,
            vehicle=self.vehicle,
            driver=self.driver,
            status=VehicleEmergencySOS.Status.ACTIVE,
            source=VehicleEmergencySOS.Source.PHYSICAL_BUTTON,
            activated_at=self.moment,
        )
        data = self.get().json()
        self.assertEqual(data["summary"]["sos_activations"], 1)
        self.assertEqual(data["summary"]["active_sos"], 1)
        row = data["sos_activity"]["results"][0]
        self.assertEqual(row["id"], active.pk)
        self.assertIsNone(row["location"])
        self.assertEqual(row["location_label"], "Location not stored")
        csv_response = self.client.get(
            "/api/v1/reports/safety-geofence/sos/csv/",
            {"date_from": "2026-09-20", "date_to": "2026-09-20"},
        )
        self.assertIn("Location not stored", b"".join(csv_response.streaming_content).decode())
