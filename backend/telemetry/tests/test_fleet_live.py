from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Driver, Vehicle
from telemetry import demo
from telemetry.models import TelemetryEvent
from transport_requests.models import DispatchAssignment, TransportRequest
from transport_requests import routing
from transport_requests import matrix


class FleetLiveApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="dispatcher", password="Strong-test-password-42!", is_staff=True
        )
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.DISPATCHER)
        self.client.force_authenticate(self.user)
        self.live = Vehicle.objects.create(
            device_id="LIVE-001", plate_number="LIVE-001", display_name="Live Shuttle"
        )
        self.missing = Vehicle.objects.create(
            device_id="MISSING-001", plate_number="MISS-001", display_name="No Telemetry Van"
        )
        self.offline = Vehicle.objects.create(
            device_id="OFFLINE-001",
            plate_number="OFF-001",
            display_name="Inactive Sedan",
            is_active=False,
        )

    def test_demo_states_use_only_the_four_supported_fleet_labels(self):
        expected = {
            "DEMO-001": "stale",
            "DEMO-002": "no_telemetry",
            "DEMO-004": "offline",
            "DEMO-006": "live",
        }

        self.assertEqual(
            {device_id: demo.state(SimpleNamespace(device_id=device_id)) for device_id in expected},
            expected,
        )

    def telemetry(
        self,
        vehicle,
        recorded_at,
        *,
        event_id=None,
        sequence_number=1,
        longitude=121.02,
        latitude=14.56,
        driving_event=TelemetryEvent.DrivingEvent.NORMAL,
        position_source=TelemetryEvent.PositionSource.GNSS,
        position_accuracy_m=None,
        gnss_speed_kph=22,
        rpm=1200,
        coolant_c=82,
        engine_load_pct=30,
        obd_source=None,
    ):
        return TelemetryEvent.objects.create(
            schema_version="1.0", event_id=event_id or f"event-{vehicle.device_id}",
            sequence_number=sequence_number, vehicle=vehicle, recorded_at=recorded_at,
            location=Point(longitude, latitude, srid=4326),
            position_source=position_source, position_accuracy_m=position_accuracy_m,
            gnss_speed_kph=gnss_speed_kph, rpm=rpm, coolant_c=coolant_c,
            engine_load_pct=engine_load_pct, obd_source=obd_source,
            driving_event=driving_event,
        )

    def test_lists_only_authoritative_positions_with_honest_states(self):
        now = timezone.now()
        self.telemetry(self.live, now)
        self.telemetry(self.offline, now)

        response = self.client.get("/api/v1/fleet-live/vehicles/")

        self.assertEqual(response.status_code, 200)
        vehicles = {item["device_id"]: item for item in response.json()["vehicles"]}
        self.assertEqual(vehicles["LIVE-001"]["telemetry_state"], "live")
        self.assertEqual(vehicles["LIVE-001"]["telemetry"]["latitude"], 14.56)
        self.assertEqual(vehicles["MISSING-001"]["telemetry_state"], "no_telemetry")
        self.assertIsNone(vehicles["MISSING-001"]["telemetry"])
        self.assertEqual(vehicles["OFFLINE-001"]["telemetry_state"], "offline")
        self.assertEqual(
            response.json()["capabilities"],
            {
                "telemetry_trail": True,
                "safety_events": True,
                "geofence": True,
                "demo_telemetry": True,
            },
        )
        self.assertEqual(
            response.json()["demo_telemetry"],
            {"enabled": False, "active": False, "simulated_vehicle_count": 0},
        )
        self.assertEqual(vehicles["LIVE-001"]["telemetry"]["telemetry_source"], "real")
        self.assertFalse(vehicles["LIVE-001"]["telemetry"]["is_demo_telemetry"])

    def test_exposes_cellular_position_source_and_accuracy(self):
        self.telemetry(
            self.live,
            timezone.now(),
            position_source=TelemetryEvent.PositionSource.CELLULAR_LBS,
            position_accuracy_m=550,
            gnss_speed_kph=None,
        )
        response = self.client.get("/api/v1/fleet-live/vehicles/")
        telemetry = response.json()["vehicles"][0]["telemetry"]
        self.assertEqual(telemetry["position_source"], "CELLULAR_LBS")
        self.assertEqual(telemetry["position_accuracy_m"], 550.0)
        self.assertIsNone(telemetry["speed_kph"])

    def test_persisted_simulated_position_is_labeled_demo_not_real(self):
        self.telemetry(
            self.live,
            timezone.now(),
            position_source=TelemetryEvent.PositionSource.SIMULATED_TEST,
            position_accuracy_m=None,
            gnss_speed_kph=None,
            rpm=None,
            coolant_c=None,
            engine_load_pct=None,
        )
        response = self.client.get("/api/v1/fleet-live/vehicles/")
        telemetry = next(
            item["telemetry"]
            for item in response.json()["vehicles"]
            if item["device_id"] == self.live.device_id
        )
        self.assertEqual(telemetry["position_source"], "SIMULATED_TEST")
        self.assertEqual(telemetry["telemetry_source"], "demo")
        self.assertTrue(telemetry["is_demo_telemetry"])
        self.assertIsNone(telemetry["speed_kph"])

    def test_exposes_actual_obd_values_and_provenance(self):
        self.telemetry(
            self.live,
            timezone.now(),
            rpm=2345,
            coolant_c=91,
            engine_load_pct=47,
            obd_source=TelemetryEvent.ObdSource.SIMULATED_TEST,
        )
        response = self.client.get("/api/v1/fleet-live/vehicles/")
        telemetry = response.json()["vehicles"][0]["telemetry"]
        self.assertEqual(telemetry["rpm"], 2345)
        self.assertEqual(telemetry["coolant_c"], 91.0)
        self.assertEqual(telemetry["engine_load_pct"], 47.0)
        self.assertEqual(telemetry["obd_source"], "SIMULATED_TEST")

    @override_settings(
        FTMS_DEMO_TELEMETRY_ENABLED=True,
        FTMS_DEMO_TELEMETRY_CENTER_LATITUDE="14.5652",
        FTMS_DEMO_TELEMETRY_CENTER_LONGITUDE="121.0286",
        FTMS_DEMO_TELEMETRY_RADIUS_METERS="1200",
    )
    def test_demo_overlay_is_explicit_non_persistent_and_never_replaces_real_data(self):
        now = timezone.now()
        real = self.telemetry(self.live, now)

        response = self.client.get("/api/v1/fleet-live/vehicles/")

        self.assertEqual(response.status_code, 200)
        vehicles = {item["device_id"]: item for item in response.json()["vehicles"]}
        self.assertEqual(
            response.json()["demo_telemetry"],
            {"enabled": True, "active": True, "simulated_vehicle_count": 2},
        )
        self.assertEqual(vehicles["LIVE-001"]["telemetry_state"], "live")
        self.assertEqual(vehicles["LIVE-001"]["telemetry"]["telemetry_source"], "real")
        self.assertEqual(vehicles["LIVE-001"]["telemetry"]["latitude"], real.location.y)
        self.assertEqual(vehicles["MISSING-001"]["telemetry_state"], "live")
        self.assertEqual(vehicles["MISSING-001"]["telemetry"]["telemetry_source"], "demo")
        self.assertTrue(vehicles["MISSING-001"]["telemetry"]["is_demo_telemetry"])
        self.assertLessEqual(
            datetime.fromisoformat(
                vehicles["MISSING-001"]["telemetry"]["recorded_at"].replace("Z", "+00:00")
            ),
            timezone.now(),
        )
        self.assertEqual(vehicles["OFFLINE-001"]["telemetry_state"], "offline")
        self.assertEqual(vehicles["OFFLINE-001"]["telemetry"]["telemetry_source"], "demo")
        self.assertEqual(vehicles["OFFLINE-001"]["telemetry"]["speed_kph"], 0)
        self.assertFalse(TelemetryEvent.objects.filter(vehicle=self.missing).exists())

    @override_settings(
        FTMS_DEMO_TELEMETRY_ENABLED=True,
        FTMS_DEMO_TELEMETRY_CENTER_LATITUDE="",
        FTMS_DEMO_TELEMETRY_CENTER_LONGITUDE="",
    )
    def test_misconfigured_demo_mode_does_not_generate_locations(self):
        response = self.client.get("/api/v1/fleet-live/vehicles/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["demo_telemetry"]["enabled"])
        self.assertFalse(response.json()["demo_telemetry"]["active"])
        self.assertIn("configuration_error", response.json()["demo_telemetry"])
        vehicle = next(
            item for item in response.json()["vehicles"] if item["device_id"] == "MISSING-001"
        )
        self.assertEqual(vehicle["telemetry_state"], "no_telemetry")
        self.assertIsNone(vehicle["telemetry"])

    def test_stale_position_and_existing_assignment_context_are_exposed(self):
        self.telemetry(self.live, timezone.now() - timedelta(hours=1))
        driver = Driver.objects.create(driver_code="DRV-001", first_name="Ana", last_name="Santos")
        item = TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference="HMS-LIVE-1",
            request_type=TransportRequest.RequestType.GUEST_TRANSFER,
            request_category=TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            requester_name="Front Desk", pickup_name="Hotel", pickup_address="Makati",
            pickup_latitude="14.560000", pickup_longitude="121.020000",
            destination_name="Airport", destination_address="Pasay",
            destination_latitude="14.508600", destination_longitude="121.019800",
            scheduled_pickup_at=timezone.now() + timedelta(hours=1), passenger_count=2,
            status=TransportRequest.Status.READY_FOR_DISPATCH, assigned_vehicle=self.live,
            created_by=self.user, approved_by=self.user, approved_at=timezone.now(),
        )
        DispatchAssignment.objects.create(
            transport_request=item, vehicle=self.live, driver=driver,
            selection_mode=DispatchAssignment.SelectionMode.OPTIMIZED, confirmed_by=self.user,
            accepted_at=timezone.now(), accepted_by=self.user,
            execution_status=DispatchAssignment.ExecutionStatus.EN_ROUTE_TO_PICKUP,
        )

        vehicle = self.client.get("/api/v1/fleet-live/vehicles/").json()["vehicles"][0]

        self.assertEqual(vehicle["telemetry_state"], "stale")
        self.assertEqual(vehicle["active_assignment"]["request_number"], item.request_number)
        self.assertEqual(vehicle["active_assignment"]["driver_name"], "Ana Santos")
        self.assertEqual(vehicle["active_assignment"]["execution_status"], "EN_ROUTE_TO_PICKUP")

    def make_assignment(
        self,
        *,
        vehicle=None,
        request_status=TransportRequest.Status.READY_FOR_DISPATCH,
        execution_status=DispatchAssignment.ExecutionStatus.EN_ROUTE_TO_PICKUP,
        accepted=True,
    ):
        vehicle = vehicle or self.live
        driver = Driver.objects.create(
            driver_code=f"DRV-LIVE-{Driver.objects.count() + 1:03d}",
            first_name="Active",
            last_name="Driver",
        )
        item = TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference=f"HMS-ACTIVE-{TransportRequest.objects.count() + 1}",
            request_type=TransportRequest.RequestType.GUEST_TRANSFER,
            request_category=TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            requester_name="Front Desk",
            pickup_name="Hotel",
            pickup_address="Makati",
            pickup_latitude="14.560000",
            pickup_longitude="121.020000",
            destination_name="Airport",
            destination_address="Pasay",
            destination_latitude="14.508600",
            destination_longitude="121.019800",
            scheduled_pickup_at=timezone.now() + timedelta(hours=1),
            passenger_count=2,
            status=request_status,
            assigned_vehicle=vehicle,
            created_by=self.user,
        )
        return DispatchAssignment.objects.create(
            transport_request=item,
            vehicle=vehicle,
            driver=driver,
            selection_mode=DispatchAssignment.SelectionMode.OPTIMIZED,
            confirmed_by=self.user,
            accepted_at=timezone.now() if accepted else None,
            accepted_by=self.user if accepted else None,
            execution_status=execution_status,
        )

    def live_vehicle_payload(self):
        response = self.client.get("/api/v1/fleet-live/vehicles/")
        self.assertEqual(response.status_code, 200)
        return next(
            vehicle
            for vehicle in response.json()["vehicles"]
            if vehicle["device_id"] == self.live.device_id
        )

    def route_result(self):
        return {
            "geometry": {"type": "LineString", "coordinates": [[121.05, 14.58], [121.02, 14.56]]},
            "distance_meters": 4200,
            "duration_seconds": 720,
            "traffic_delay_seconds": 60,
            "departure_time": "2026-09-21T00:00:00Z",
            "arrival_time": "2026-09-21T00:12:00Z",
            "traffic_mode": "live",
        }

    def test_staff_active_route_uses_canonical_phase_origins_and_targets(self):
        assignment = self.make_assignment()
        self.telemetry(self.live, timezone.now(), longitude=121.05, latitude=14.58)
        url = f"/api/v1/fleet-live/assignments/{assignment.pk}/route/"

        with patch("transport_requests.routing.get_route_between", return_value=self.route_result()) as get_route:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["route"]["phase"], "TO_PICKUP")
            self.assertEqual(response.json()["route"]["position_state"], "CURRENT")
            self.assertEqual(response.json()["route"]["route_basis"], "CURRENT_VEHICLE_POSITION")
            self.assertEqual(response.json()["route"]["route"]["distance_meters"], 4200)
            self.assertEqual(response.json()["route"]["planned_route_status"], "AVAILABLE")
            self.assertEqual(
                [call.args[1:] for call in get_route.call_args_list],
                [
                    ([121.02, 14.56], [121.0198, 14.5086]),
                    ([121.05, 14.58], [121.02, 14.56]),
                ],
            )

            assignment.execution_status = DispatchAssignment.ExecutionStatus.AT_PICKUP
            assignment.save(update_fields=["execution_status", "updated_at"])
            self.client.get(url)
            self.assertEqual(get_route.call_args.args[1:], ([121.02, 14.56], [121.0198, 14.5086]))

            assignment.execution_status = DispatchAssignment.ExecutionStatus.IN_TRANSIT
            assignment.save(update_fields=["execution_status", "updated_at"])
            self.client.get(url)
            self.assertEqual(get_route.call_args.args[1:], ([121.05, 14.58], [121.0198, 14.5086]))

    def test_pre_pickup_route_legs_fail_independently_without_fallback(self):
        assignment = self.make_assignment()
        self.telemetry(self.live, timezone.now(), longitude=121.05, latitude=14.58)
        url = f"/api/v1/fleet-live/assignments/{assignment.pk}/route/"

        def active_fails(identity, _origin, _target):
            if str(identity).startswith("driver:"):
                raise routing.RouteServiceError
            return self.route_result()

        with patch("transport_requests.routing.get_route_between", side_effect=active_fails):
            route = self.client.get(url).json()["route"]
        self.assertEqual(route["route_status"], "TEMPORARILY_UNAVAILABLE")
        self.assertIsNone(route["route"])
        self.assertEqual(route["planned_route_status"], "AVAILABLE")
        self.assertIsNotNone(route["planned_route"])

        def planned_fails(identity, _origin, _target):
            if str(identity) == str(assignment.transport_request_id):
                raise routing.RouteServiceError
            return self.route_result()

        with patch("transport_requests.routing.get_route_between", side_effect=planned_fails):
            route = self.client.get(url).json()["route"]
        self.assertEqual(route["route_status"], "AVAILABLE")
        self.assertIsNotNone(route["route"])
        self.assertEqual(route["planned_route_status"], "TEMPORARILY_UNAVAILABLE")
        self.assertIsNone(route["planned_route"])

    def test_stale_position_routes_from_last_known_coordinates_without_dispatch_eligibility(self):
        assignment = self.make_assignment()
        event = self.telemetry(
            self.live,
            timezone.now() - timedelta(seconds=301),
            longitude=121.05,
            latitude=14.58,
        )
        self.assertFalse(matrix.dispatch_position_is_eligible(self.live, event))
        url = f"/api/v1/fleet-live/assignments/{assignment.pk}/route/"

        with patch("transport_requests.routing.get_route_between", return_value=self.route_result()) as get_route:
            response = self.client.get(url)
            active_route = response.json()["route"]
            self.assertEqual(active_route["position_state"], "STALE")
            self.assertTrue(active_route["vehicle_position"]["is_stale"])
            self.assertEqual(active_route["route_basis"], "LAST_KNOWN_VEHICLE_POSITION")
            self.assertGreaterEqual(active_route["position_age_seconds"], 301)
            self.assertEqual(get_route.call_args.args[1:], ([121.05, 14.58], [121.02, 14.56]))

            assignment.execution_status = DispatchAssignment.ExecutionStatus.IN_TRANSIT
            assignment.save(update_fields=["execution_status", "updated_at"])
            response = self.client.get(url)
            self.assertEqual(response.json()["route"]["route_basis"], "LAST_KNOWN_VEHICLE_POSITION")
            self.assertEqual(get_route.call_args.args[1:], ([121.05, 14.58], [121.0198, 14.5086]))

    def test_arrived_completed_and_provider_failure_never_return_fake_routes(self):
        assignment = self.make_assignment()
        self.telemetry(self.live, timezone.now(), longitude=121.05, latitude=14.58)
        url = f"/api/v1/fleet-live/assignments/{assignment.pk}/route/"

        with patch("transport_requests.routing.get_route_between", side_effect=routing.RouteServiceError):
            response = self.client.get(url)
            self.assertEqual(response.json()["route"]["route_status"], "TEMPORARILY_UNAVAILABLE")
            self.assertIsNone(response.json()["route"]["route"])

        for execution_status in (
            DispatchAssignment.ExecutionStatus.AT_DESTINATION,
            DispatchAssignment.ExecutionStatus.COMPLETED,
        ):
            assignment.execution_status = execution_status
            assignment.save(update_fields=["execution_status", "updated_at"])
            with patch("transport_requests.routing.get_route_between") as get_route:
                response = self.client.get(url)
                self.assertEqual(response.json()["route"]["route_status"], "NOT_ACTIVE")
                self.assertIsNone(response.json()["route"]["route"])
                self.assertIsNone(response.json()["route"]["planned_route"])
                get_route.assert_not_called()

    def test_active_route_endpoint_requires_staff_authentication(self):
        assignment = self.make_assignment()
        self.client.force_authenticate(user=None)
        response = self.client.get(f"/api/v1/fleet-live/assignments/{assignment.pk}/route/")
        self.assertIn(response.status_code, {401, 403})

    def test_only_accepted_released_in_progress_assignment_is_active(self):
        assignment = self.make_assignment(
            execution_status=DispatchAssignment.ExecutionStatus.ASSIGNED
        )
        self.assertIsNone(self.live_vehicle_payload()["active_assignment"])

        assignment.execution_status = DispatchAssignment.ExecutionStatus.EN_ROUTE_TO_PICKUP
        assignment.accepted_at = None
        assignment.accepted_by = None
        assignment.save(
            update_fields=["execution_status", "accepted_at", "accepted_by", "updated_at"]
        )
        self.assertIsNone(self.live_vehicle_payload()["active_assignment"])

        assignment.accepted_at = timezone.now()
        assignment.accepted_by = self.user
        assignment.save(update_fields=["accepted_at", "accepted_by", "updated_at"])

        for execution_status in (
            DispatchAssignment.ExecutionStatus.EN_ROUTE_TO_PICKUP,
            DispatchAssignment.ExecutionStatus.AT_PICKUP,
            DispatchAssignment.ExecutionStatus.IN_TRANSIT,
            DispatchAssignment.ExecutionStatus.AT_DESTINATION,
        ):
            assignment.execution_status = execution_status
            assignment.save(update_fields=["execution_status", "updated_at"])
            self.assertEqual(
                self.live_vehicle_payload()["active_assignment"]["assignment_id"],
                assignment.pk,
            )

        assignment.transport_request.status = TransportRequest.Status.APPROVED
        assignment.transport_request.save(update_fields=["status", "updated_at"])
        self.assertIsNone(self.live_vehicle_payload()["active_assignment"])

        assignment.transport_request.status = TransportRequest.Status.READY_FOR_DISPATCH
        assignment.transport_request.save(update_fields=["status", "updated_at"])

        assignment.execution_status = DispatchAssignment.ExecutionStatus.COMPLETED
        assignment.save(update_fields=["execution_status", "updated_at"])
        self.assertIsNone(self.live_vehicle_payload()["active_assignment"])

    def test_active_assignment_uses_only_its_assigned_vehicle_telemetry(self):
        assignment = self.make_assignment()
        other_event = self.telemetry(
            self.missing,
            timezone.now(),
            longitude=120.75,
            latitude=14.25,
        )

        assigned_vehicle = self.live_vehicle_payload()
        self.assertEqual(
            assigned_vehicle["active_assignment"]["assignment_id"], assignment.pk
        )
        self.assertEqual(assigned_vehicle["telemetry_state"], "no_telemetry")
        self.assertIsNone(assigned_vehicle["telemetry"])

        self.telemetry(
            self.live,
            timezone.now() + timedelta(seconds=1),
            event_id="assigned-older",
            sequence_number=1,
            longitude=121.04,
            latitude=14.57,
        )
        own_event = self.telemetry(
            self.live,
            timezone.now() + timedelta(seconds=2),
            event_id="assigned-latest",
            sequence_number=2,
            longitude=121.05,
            latitude=14.58,
        )
        assigned_vehicle = self.live_vehicle_payload()
        self.assertEqual(assigned_vehicle["telemetry"]["latitude"], own_event.location.y)
        self.assertNotEqual(
            assigned_vehicle["telemetry"]["latitude"], other_event.location.y
        )

    def test_invalid_latest_coordinates_are_not_exposed_as_position(self):
        self.make_assignment()
        self.telemetry(
            self.live,
            timezone.now(),
            longitude=181,
            latitude=91,
        )

        vehicle = self.live_vehicle_payload()
        self.assertEqual(vehicle["telemetry_state"], "no_telemetry")
        self.assertIsNone(vehicle["telemetry"])
        self.assertIsNotNone(vehicle["active_assignment"])

    @override_settings(FTMS_TELEMETRY_CLOCK_SKEW_SECONDS=300)
    def test_future_event_cannot_override_current_event_and_rows_are_preserved(self):
        recorded_at = timezone.now()
        self.telemetry(
            self.live,
            recorded_at,
            event_id="current-lower-sequence",
            sequence_number=1,
            latitude=14.51,
        )
        selected = self.telemetry(
            self.live,
            recorded_at,
            event_id="current-higher-sequence",
            sequence_number=2,
            latitude=14.52,
        )
        future = self.telemetry(
            self.live,
            recorded_at + timedelta(days=3650),
            event_id="preserved-future-event",
            sequence_number=999,
            latitude=15.99,
        )

        vehicle = self.live_vehicle_payload()

        self.assertEqual(vehicle["telemetry"]["latitude"], selected.location.y)
        self.assertNotEqual(vehicle["telemetry"]["latitude"], future.location.y)
        self.assertEqual(TelemetryEvent.objects.filter(vehicle=self.live).count(), 3)
        self.assertTrue(TelemetryEvent.objects.filter(pk=future.pk).exists())

        latest = self.client.get(f"/api/v1/vehicles/{self.live.device_id}/latest-status/")
        self.assertEqual(latest.status_code, 200)
        self.assertEqual(latest.json()["latest"]["event_id"], selected.event_id)
    @override_settings(
        FTMS_DEMO_TELEMETRY_ENABLED=True,
        FTMS_DEMO_TELEMETRY_CENTER_LATITUDE="14.5652",
        FTMS_DEMO_TELEMETRY_CENTER_LONGITUDE="121.0286",
        FTMS_DEMO_TELEMETRY_RADIUS_METERS="1200",
    )
    def test_active_assignment_never_uses_demo_telemetry_as_fallback(self):
        self.make_assignment()

        vehicle = self.live_vehicle_payload()

        self.assertEqual(vehicle["telemetry_state"], "no_telemetry")
        self.assertIsNone(vehicle["telemetry"])
        self.assertIsNotNone(vehicle["active_assignment"])

    def test_endpoint_requires_staff_authentication(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get("/api/v1/fleet-live/vehicles/").status_code, 401)

    def test_returns_recent_real_trail_in_chronological_order(self):
        now = timezone.now()
        self.telemetry(
            self.live, now - timedelta(minutes=2), event_id="trail-1",
            sequence_number=1, longitude=121.01, latitude=14.51,
        )
        self.telemetry(
            self.live, now - timedelta(minutes=1), event_id="trail-2",
            sequence_number=2, longitude=121.02, latitude=14.52,
        )

        response = self.client.get(f"/api/v1/fleet-live/vehicles/{self.live.pk}/trail/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["device_id"], "LIVE-001")
        self.assertEqual(
            [point["event_id"] for point in response.json()["points"]],
            ["trail-1", "trail-2"],
        )
        self.assertEqual(response.json()["points"][1]["latitude"], 14.52)

    @override_settings(FTMS_TELEMETRY_CLOCK_SKEW_SECONDS=300)
    def test_precise_trail_excludes_lbs_and_future_events_without_deleting_them(self):
        now = timezone.now()
        gnss = self.telemetry(
            self.live, now - timedelta(minutes=1), event_id="recent-gnss",
            sequence_number=1, longitude=121.01, latitude=14.51,
        )
        lbs = self.telemetry(
            self.live, now, event_id="current-lbs", sequence_number=2,
            position_source=TelemetryEvent.PositionSource.CELLULAR_LBS,
            position_accuracy_m=550, gnss_speed_kph=None,
        )
        future = self.telemetry(
            self.live, now + timedelta(days=3650), event_id="future-gnss",
            sequence_number=3,
        )

        response = self.client.get(f"/api/v1/fleet-live/vehicles/{self.live.pk}/trail/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [point["event_id"] for point in response.json()["points"]],
            [gnss.event_id],
        )
        self.assertEqual(
            TelemetryEvent.objects.filter(pk__in=[lbs.pk, future.pk]).count(), 2
        )

    def test_returns_all_persisted_non_normal_safety_events_as_map_pins(self):
        now = timezone.now()
        self.telemetry(
            self.live, now, event_id="brake-1",
            driving_event=TelemetryEvent.DrivingEvent.HARSH_BRAKING,
        )
        self.telemetry(
            self.missing, now, event_id="acceleration-1",
            driving_event=TelemetryEvent.DrivingEvent.HARSH_ACCELERATION,
        )
        self.telemetry(
            self.offline,
            now,
            event_id="turn-1",
            sequence_number=2,
            driving_event=TelemetryEvent.DrivingEvent.SHARP_TURN,
        )
        self.telemetry(
            self.offline,
            now - timedelta(seconds=1),
            event_id="normal-1",
            driving_event=TelemetryEvent.DrivingEvent.NORMAL,
        )

        response = self.client.get("/api/v1/fleet-live/safety-events/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["events"]), 3)
        self.assertEqual(
            {event["event_id"] for event in response.json()["events"]},
            {"brake-1", "acceleration-1", "turn-1"},
        )
        self.assertNotIn("normal-1", {event["event_id"] for event in response.json()["events"]})

    def test_safety_events_are_newest_first_paginated_and_filterable(self):
        now = timezone.now()
        self.telemetry(self.live, now - timedelta(minutes=2), event_id="brake-filter", driving_event=TelemetryEvent.DrivingEvent.HARSH_BRAKING)
        self.telemetry(self.live, now - timedelta(minutes=1), event_id="turn-filter", sequence_number=2, driving_event=TelemetryEvent.DrivingEvent.SHARP_TURN)
        response = self.client.get(
            "/api/v1/fleet-live/safety-events/",
            {"event_type": "SHARP_TURN", "vehicle": self.live.pk, "page_size": 1},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["event_id"], "turn-filter")
        self.assertEqual(response.json()["events"], response.json()["results"])
        self.assertIn("received_at", response.json()["results"][0])
        search_response = self.client.get(
            "/api/v1/fleet-live/safety-events/", {"search": self.live.device_id}
        )
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.json()["count"], 2)

    def test_trail_and_safety_event_endpoints_require_staff_authentication(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.get(f"/api/v1/fleet-live/vehicles/{self.live.pk}/trail/").status_code,
            401,
        )
        self.assertEqual(self.client.get("/api/v1/fleet-live/safety-events/").status_code, 401)
