from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Driver, NumberCodingRule, Vehicle, VehicleInspection
from telemetry.models import TelemetryEvent
from transport_requests import dispatch, routing
from transport_requests.models import (
    DispatchAssignment,
    DispatchAssignmentEvent,
    TransportRequest,
)


class DispatchBoardTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="operator", is_staff=True)
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.DISPATCHER)
        self.client.force_authenticate(self.user)
        today = timezone.localdate()
        self.driver = Driver.objects.create(
            driver_code="DRV-001",
            first_name="Juan",
            last_name="Dela Cruz",
            license_number="N01",
            license_expiry_date=today + timedelta(days=30),
            medical_certificate_expiry_date=today + timedelta(days=30),
        )
        self.vehicle = Vehicle.objects.create(
            device_id="VEH-001",
            plate_number="ABC-123",
            display_name="Guest Van",
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=8,
        )
        self.pass_inspection(self.vehicle)
        self.request = self.make_request("REQ-001")

    def pass_inspection(self, vehicle):
        return VehicleInspection.objects.create(
            vehicle=vehicle,
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
            inspected_by=self.user,
        )

    def make_request(self, reference, *, hours=2):
        return TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference=reference,
            request_type=TransportRequest.RequestType.GUEST_TRANSFER,
            request_category=TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            requester_name="Front Desk",
            pickup_name="Hotel",
            pickup_address="Makati",
            pickup_latitude="14.565200",
            pickup_longitude="121.028600",
            destination_name="Airport",
            destination_address="Pasay",
            destination_latitude="14.508600",
            destination_longitude="121.019800",
            scheduled_pickup_at=timezone.now() + timedelta(hours=hours),
            estimated_duration_minutes=60,
            required_vehicle_type=Vehicle.VehicleType.VAN,
            passenger_count=4,
            status=TransportRequest.Status.READY_FOR_DISPATCH,
            created_by=self.user,
        )

    def confirmation(self, **overrides):
        body = {
            "transport_request_id": str(self.request.pk),
            "vehicle_id": self.vehicle.pk,
            "driver_id": self.driver.pk,
            "selection_mode": "MANUAL",
            "override_reason": "Operational selection",
            **overrides,
        }
        return self.client.post(
            "/api/v1/transport-requests/dispatch-board/confirm/", body, format="json"
        )

    def test_board_requires_auth_and_exposes_real_candidates(self):
        response = self.client.get("/api/v1/transport-requests/dispatch-board/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["requests"][0]["id"], str(self.request.pk))
        self.assertEqual(response.json()["eligible_drivers"][0]["eligibility_status"], "ELIGIBLE")
        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.get("/api/v1/transport-requests/dispatch-board/").status_code, 401
        )

    def test_bulk_board_fingerprints_match_individual_fingerprints(self):
        second = self.make_request("REQ-002", hours=4)
        requests = list(
            TransportRequest.objects.filter(pk__in=[self.request.pk, second.pk])
            .select_related("flight_context")
        )
        fingerprints = dispatch.planning_fingerprints(requests)
        self.assertEqual(
            fingerprints[str(self.request.pk)],
            dispatch.planning_fingerprint(self.request.pk),
        )
        self.assertEqual(fingerprints[str(second.pk)], dispatch.planning_fingerprint(second.pk))
        board = self.client.get("/api/v1/transport-requests/dispatch-board/")
        self.assertEqual(board.status_code, 200)
        self.assertEqual(board.json()["recommendation_fingerprints"], fingerprints)

    def test_board_query_count_does_not_grow_per_request(self):
        for index in range(2, 7):
            self.make_request(f"REQ-{index:03d}", hours=index + 2)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/api/v1/transport-requests/dispatch-board/")
        self.assertEqual(response.status_code, 200)
        self.assertLess(len(queries), 35)

    def test_manual_confirmation_syncs_vehicle_and_keeps_immutable_history(self):
        response = self.confirmation()
        self.assertEqual(response.status_code, 201)
        assignment = DispatchAssignment.objects.get(transport_request=self.request)
        self.request.refresh_from_db()
        self.assertEqual(assignment.driver, self.driver)
        self.assertEqual(assignment.vehicle, self.vehicle)
        self.assertEqual(assignment.confirmed_by, self.user)
        self.assertEqual(
            assignment.execution_status, DispatchAssignment.ExecutionStatus.ASSIGNED
        )
        self.assertIsNone(assignment.execution_started_at)
        self.assertEqual(self.request.assigned_vehicle, self.vehicle)
        event = DispatchAssignmentEvent.objects.get(assignment=assignment)
        with self.assertRaises(ValueError):
            event.delete()
        old_endpoint = self.client.post(
            f"/api/v1/transport-requests/{self.request.pk}/assign-vehicle/",
            {"vehicle_device_id": self.vehicle.device_id},
            format="json",
        )
        self.assertEqual(old_endpoint.status_code, 400)
        refreshed = self.client.get("/api/v1/transport-requests/dispatch-board/")
        persisted = refreshed.json()["assignments"][0]
        self.assertNotIn(
            str(self.request.pk),
            {item["id"] for item in refreshed.json()["requests"]},
        )
        self.assertEqual(persisted["transport_request_id"], str(self.request.pk))
        self.assertEqual(persisted["driver"]["id"], self.driver.pk)
        self.assertEqual(persisted["vehicle"]["id"], self.vehicle.pk)

    def test_scheduled_pickup_excludes_off_shift_driver_and_blocks_manual_override(self):
        self.driver.work_shift = Driver.WorkShift.DAY
        self.driver.weekly_rest_days = ["TUESDAY", "THURSDAY"]
        self.driver.save(update_fields=["work_shift", "weekly_rest_days", "updated_at"])
        self.request.scheduled_pickup_at = datetime(
            2026, 9, 21, 20, 0, tzinfo=ZoneInfo("Asia/Manila")
        )
        self.request.save(update_fields=["scheduled_pickup_at", "updated_at"])

        board = self.client.get("/api/v1/transport-requests/dispatch-board/").json()
        self.assertEqual(board["manual_candidates"][str(self.request.pk)]["drivers"], [])
        response = self.confirmation(override_reason="Cannot bypass schedule")
        self.assertEqual(response.status_code, 400)
        self.assertIn("DRIVER_OFF_SHIFT", response.json()["driver"])

    def test_scheduled_pickup_rest_day_blocks_night_shift_after_midnight(self):
        self.driver.work_shift = Driver.WorkShift.NIGHT
        self.driver.weekly_rest_days = ["MONDAY", "THURSDAY"]
        self.driver.save(update_fields=["work_shift", "weekly_rest_days", "updated_at"])
        self.request.scheduled_pickup_at = datetime(
            2026, 9, 22, 2, 0, tzinfo=ZoneInfo("Asia/Manila")
        )
        self.request.save(update_fields=["scheduled_pickup_at", "updated_at"])

        response = self.confirmation(override_reason="Cannot bypass rest day")
        self.assertEqual(response.status_code, 400)
        self.assertIn("DRIVER_REST_DAY", response.json()["driver"])

    def test_operational_assignment_list_filters_links_and_paginates(self):
        self.assertEqual(self.confirmation().status_code, 201)
        active = self.client.get(
            "/api/v1/transport-requests/dispatch-assignments/?scope=active"
        )
        self.assertEqual(active.status_code, 200)
        self.assertEqual(active.json()["count"], 1)
        self.assertEqual(
            active.json()["results"][0]["transport_request"]["id"],
            str(self.request.pk),
        )
        assignment = DispatchAssignment.objects.get(transport_request=self.request)
        assignment.execution_status = DispatchAssignment.ExecutionStatus.COMPLETED
        assignment.completed_at = timezone.now()
        assignment.save(update_fields=["execution_status", "completed_at", "updated_at"])
        self.assertEqual(
            self.client.get(
                "/api/v1/transport-requests/dispatch-assignments/?scope=active"
            ).json()["count"],
            0,
        )
        completed = self.client.get(
            "/api/v1/transport-requests/dispatch-assignments/?scope=completed&page_size=1"
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.json()["results"][0]["execution_status"], "COMPLETED")
        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.get(
                "/api/v1/transport-requests/dispatch-assignments/?scope=active"
            ).status_code,
            401,
        )

    def test_non_dispatchable_and_unauthorized_confirmation_are_rejected(self):
        pending = self.make_request("REQ-PENDING", hours=4)
        pending.status = TransportRequest.Status.FOR_APPROVAL
        pending.save(update_fields=["status", "updated_at"])
        board = self.client.get("/api/v1/transport-requests/dispatch-board/")
        self.assertNotIn(
            str(pending.pk),
            {item["id"] for item in board.json()["requests"]},
        )
        self.assertEqual(
            self.confirmation(transport_request_id=str(pending.pk)).status_code,
            400,
        )

        unauthorized = get_user_model().objects.create_user(
            username="profileless", is_staff=True
        )
        self.client.force_authenticate(unauthorized)
        self.assertEqual(self.confirmation().status_code, 403)

    def test_optimizer_queue_contains_only_ready_unassigned_requests(self):
        for index, request_status in enumerate(
            (
                TransportRequest.Status.FOR_APPROVAL,
                TransportRequest.Status.APPROVED,
                TransportRequest.Status.REJECTED,
                TransportRequest.Status.CANCELLED,
            ),
            start=2,
        ):
            item = self.make_request(f"REQ-{request_status}", hours=index)
            item.status = request_status
            item.save(update_fields=["status", "updated_at"])

        response = self.client.get("/api/v1/transport-requests/dispatch-board/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()["requests"]],
            [str(self.request.pk)],
        )

    def test_recommendation_endpoint_does_not_operate_on_approved_request(self):
        self.request.status = TransportRequest.Status.APPROVED
        self.request.save(update_fields=["status", "updated_at"])

        response = self.client.post(
            "/api/v1/transport-requests/dispatch-board/recommendations/",
            {"request_ids": [str(self.request.pk)]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["requests_considered"], 0)
        self.assertEqual(response.json()["recommendations"], [])

    def test_restricted_driver_and_change_without_reason_are_rejected(self):
        restricted = Driver.objects.create(
            driver_code="DRV-RESTRICTED", first_name="No", last_name="Evidence"
        )
        self.assertEqual(self.confirmation(driver_id=restricted.pk).status_code, 400)
        self.assertEqual(self.confirmation().status_code, 201)
        other = Vehicle.objects.create(
            device_id="VEH-002",
            plate_number="DEF-456",
            display_name="Other Van",
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=8,
        )
        self.assertEqual(
            self.confirmation(vehicle_id=other.pk, override_reason="").status_code, 400
        )

    def test_assignment_cannot_be_changed_after_driver_execution_starts(self):
        self.assertEqual(self.confirmation().status_code, 201)
        assignment = DispatchAssignment.objects.get(transport_request=self.request)
        assignment.execution_status = DispatchAssignment.ExecutionStatus.EN_ROUTE_TO_PICKUP
        assignment.execution_started_at = timezone.now()
        assignment.save(
            update_fields=["execution_status", "execution_started_at", "updated_at"]
        )

        response = self.confirmation(override_reason="Late reassignment")

        self.assertEqual(response.status_code, 400)
        self.assertIn("execution_status", response.json())

    def test_signed_recommendation_requires_explicit_ready_transition(self):
        token = dispatch.recommendation_token(
            self.request.pk, self.vehicle.pk, self.driver.pk
        )
        optimized = self.confirmation(
            selection_mode="OPTIMIZED", override_reason="", recommendation_token=token
        )
        self.assertEqual(optimized.status_code, 201)
        self.assertEqual(DispatchAssignment.objects.count(), 1)

    def create_vehicle_position(self):
        return TelemetryEvent.objects.create(
            schema_version="1.0",
            event_id=f"dispatch-route-{TelemetryEvent.objects.count()}",
            sequence_number=TelemetryEvent.objects.count() + 1,
            vehicle=self.vehicle,
            recorded_at=timezone.now(),
            location=Point(121.021, 14.55, srid=4326),
            gnss_speed_kph=Decimal("20.00"),
            driving_event=TelemetryEvent.DrivingEvent.NORMAL,
        )

    @patch("transport_requests.active_routes.routing.get_route_between")
    @patch("transport_requests.active_routes.routing.get_route")
    def test_selected_recommendation_route_fetches_both_road_legs(
        self, request_route_mock, vehicle_route_mock
    ):
        event = self.create_vehicle_position()
        road_route = {
            "traffic_mode": "live",
            "distance_meters": 1000,
            "duration_seconds": 300,
            "traffic_delay_seconds": 20,
            "departure_time": "2026-09-23T08:00:00+08:00",
            "arrival_time": "2026-09-23T08:05:00+08:00",
            "geometry": {"type": "LineString", "coordinates": [[121.0, 14.5], [121.1, 14.6]]},
        }
        request_route_mock.return_value = road_route
        vehicle_route_mock.return_value = road_route
        token = dispatch.recommendation_token(self.request.pk, self.vehicle.pk, self.driver.pk)

        response = self.client.post(
            "/api/v1/transport-requests/dispatch-board/recommendation-route/",
            {
                "transport_request_id": str(self.request.pk),
                "vehicle_id": self.vehicle.pk,
                "driver_id": self.driver.pk,
                "recommendation_token": token,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json()["route"]["route"])
        self.assertIsNotNone(response.json()["route"]["planned_route"])
        request_route_mock.assert_called_once_with(self.request)
        vehicle_route_mock.assert_called_once_with(
            f"recommendation:{self.request.pk}:{self.vehicle.pk}:{event.pk}",
            [121.021, 14.55],
            [121.0286, 14.5652],
        )

    @patch(
        "transport_requests.active_routes.routing.get_route_between",
        side_effect=routing.RouteServiceError,
    )
    @patch(
        "transport_requests.active_routes.routing.get_route",
        side_effect=routing.RouteServiceError,
    )
    def test_recommendation_route_failure_has_no_fabricated_geometry(self, *_mocks):
        self.create_vehicle_position()
        token = dispatch.recommendation_token(self.request.pk, self.vehicle.pk, self.driver.pk)

        response = self.client.post(
            "/api/v1/transport-requests/dispatch-board/recommendation-route/",
            {
                "transport_request_id": str(self.request.pk),
                "vehicle_id": self.vehicle.pk,
                "driver_id": self.driver.pk,
                "recommendation_token": token,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["route"]["route_status"], "TEMPORARILY_UNAVAILABLE")
        self.assertIsNone(response.json()["route"]["route"])
        self.assertIsNone(response.json()["route"]["planned_route"])

    @patch("transport_requests.dispatch.matrix.eligible_vehicle_origins")
    @patch("transport_requests.dispatch.matrix.build_dispatch_matrix")
    @patch("transport_requests.dispatch.estimate_trip_fuel_cost")
    def test_recommendation_api_attaches_advisory_fuel_metadata_without_recomputing(
        self, fuel_mock, matrix_mock, origins_mock
    ):
        timestamp = timezone.now() - timedelta(minutes=5)
        effective_at = timezone.now() - timedelta(days=1)
        fuel_mock.return_value = SimpleNamespace(
            status="AVAILABLE",
            reason="PREFERRED_PARTNER_TRIP_FUEL_COST_ESTIMATED",
            fuel_rate_basis="CURRENT_AI",
            fuel_rate_lph=Decimal("4.2000"),
            travel_time_seconds=Decimal("2700"),
            estimated_fuel_liters=Decimal("3.1500"),
            fuel_type="GASOLINE",
            fuel_grade="PREMIUM_95",
            price_per_liter=Decimal("71.2500"),
            currency="PHP",
            price_provider="ShellPH",
            price_source_mode="MANUAL",
            price_effective_at=effective_at,
            estimated_fuel_cost_php=Decimal("224.44"),
            fuel_source_timestamp=timestamp,
            history_sample_count=0,
        )
        matrix_mock.return_value = {
            "vehicle_ids": [self.vehicle.device_id],
            "request_ids": [str(self.request.pk)],
            "durations_seconds": [[2700]],
            "distances_meters": [[1000]],
            "traffic_delays_seconds": [[20]],
            "cell_statuses": [["OK"]],
        }
        origins_mock.return_value = [
            {"vehicle_id": self.vehicle.device_id, "latitude": 14.5, "longitude": 121.0}
        ]
        fingerprint = dispatch.planning_fingerprint(self.request.pk)

        response = self.client.post(
            "/api/v1/transport-requests/dispatch-board/recommendations/",
            {"request_ids": [str(self.request.pk)]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        selected = response.json()["recommendations"][0]
        comparison = response.json()["candidate_comparison"][str(self.request.pk)][0]
        expected = selected["fuel_estimate"]
        self.assertEqual(expected, comparison["fuel_estimate"])
        self.assertEqual(expected["status"], "AVAILABLE")
        self.assertEqual(expected["fuel_rate_basis"], "CURRENT_AI")
        self.assertEqual(expected["fuel_rate_basis_label"], "Current AI")
        self.assertEqual(expected["fuel_rate_lph"], "4.2000")
        self.assertEqual(expected["estimated_fuel_liters"], "3.1500")
        self.assertEqual(expected["estimated_fuel_cost_php"], "224.44")
        self.assertEqual(expected["price_provider"], "ShellPH")
        self.assertEqual(expected["fuel_grade"], "PREMIUM_95")
        self.assertEqual(selected["planning_fingerprint"], fingerprint)
        self.assertEqual(
            selected["recommendation_token"],
            dispatch.recommendation_token(
                self.request.pk, self.vehicle.pk, self.driver.pk, fingerprint
            ),
        )
        fuel_mock.assert_called_once_with(self.vehicle, 2700)

    @patch("transport_requests.dispatch.matrix.eligible_vehicle_origins")
    @patch("transport_requests.dispatch.matrix.build_dispatch_matrix")
    @patch("transport_requests.dispatch.estimate_trip_fuel_cost")
    def test_unavailable_fuel_advisory_does_not_change_candidate_selection(
        self, fuel_mock, matrix_mock, origins_mock
    ):
        fuel_mock.return_value = SimpleNamespace(
            status="UNAVAILABLE",
            reason="FUEL_GRADE_NOT_RECORDED",
            fuel_rate_basis="HISTORICAL_AI_BASELINE",
            fuel_rate_lph=Decimal("4.1000"),
            travel_time_seconds=Decimal("100"),
            estimated_fuel_liters=Decimal("0.1139"),
            fuel_type="GASOLINE",
            fuel_grade="",
            price_per_liter=None,
            currency=None,
            price_provider=None,
            price_source_mode=None,
            price_effective_at=None,
            estimated_fuel_cost_php=None,
            fuel_source_timestamp=timezone.now(),
            history_sample_count=9,
        )
        matrix_mock.return_value = {
            "vehicle_ids": [self.vehicle.device_id],
            "request_ids": [str(self.request.pk)],
            "durations_seconds": [[100]],
            "distances_meters": [[1000]],
            "traffic_delays_seconds": [[10]],
            "cell_statuses": [["OK"]],
        }
        origins_mock.return_value = [
            {"vehicle_id": self.vehicle.device_id, "latitude": 14.5, "longitude": 121.0}
        ]

        response = self.client.post(
            "/api/v1/transport-requests/dispatch-board/recommendations/",
            {"request_ids": [str(self.request.pk)]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        selected = response.json()["recommendations"][0]
        advisory = selected["fuel_estimate"]
        self.assertEqual(selected["recommended_vehicle"]["id"], self.vehicle.pk)
        self.assertEqual(advisory["status"], "UNAVAILABLE")
        self.assertEqual(advisory["reason"], "FUEL_GRADE_NOT_RECORDED")
        self.assertEqual(advisory["fuel_rate_basis"], "HISTORICAL_AI_BASELINE")
        self.assertEqual(advisory["history_sample_count"], 9)
        self.assertIsNone(advisory["estimated_fuel_cost_php"])

    def test_fleet_reference_basis_has_professional_display_label(self):
        estimate = SimpleNamespace(
            status="UNAVAILABLE",
            reason="NO_VALID_PREFERRED_PARTNER_PRICE",
            fuel_rate_basis="FLEET_REFERENCE_BASELINE",
            fuel_rate_lph=Decimal("7.0000"),
            travel_time_seconds=Decimal("1800"),
            estimated_fuel_liters=Decimal("3.5000"),
            fuel_type="DIESEL",
            fuel_grade="REGULAR_DIESEL",
            price_per_liter=None,
            currency=None,
            price_provider=None,
            price_source_mode=None,
            price_effective_at=None,
            estimated_fuel_cost_php=None,
            fuel_source_timestamp=None,
            history_sample_count=0,
            fuel_rate_provenance="CAPSTONE_REFERENCE",
        )
        payload = dispatch._fuel_estimate_payload(estimate)
        self.assertEqual(
            payload["fuel_rate_basis_label"], "Fleet Reference Baseline"
        )
        self.assertNotIn("demo", payload["fuel_rate_basis_label"].lower())

    @patch("transport_requests.dispatch.matrix.eligible_vehicle_origins")
    @patch("transport_requests.dispatch.matrix.build_dispatch_matrix")
    def test_optimizer_executes_and_uses_tomtom_duration_deterministically(
        self, matrix_mock, origins_mock
    ):
        second_vehicle = Vehicle.objects.create(
            device_id="VEH-002",
            plate_number="DEF-456",
            display_name="Slower Van",
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=8,
        )
        self.pass_inspection(second_vehicle)
        matrix_mock.return_value = {
            "vehicle_ids": [self.vehicle.device_id, second_vehicle.device_id],
            "request_ids": [str(self.request.pk)],
            "durations_seconds": [[100], [500]],
            "distances_meters": [[1000], [2000]],
            "traffic_delays_seconds": [[10], [20]],
            "cell_statuses": [["OK"], ["OK"]],
        }
        origins_mock.return_value = [
            {"vehicle_id": self.vehicle.device_id, "latitude": 14.5, "longitude": 121.0},
            {"vehicle_id": second_vehicle.device_id, "latitude": 14.6, "longitude": 121.1},
        ]
        result = dispatch.recommendations()
        self.assertEqual(len(result["recommendations"]), 1)
        selected = result["recommendations"][0]
        self.assertEqual(selected["vehicle"], self.vehicle)
        self.assertEqual(selected["travel_time_seconds"], 100)
        self.assertIn("Driver eligibility is ELIGIBLE", selected["explanation"])
        self.assertEqual(selected["schedule_context"]["driver"]["status"], "AVAILABLE")
        self.assertEqual(selected["gis_preview"]["vehicle_location"]["vehicle_id"], "VEH-001")
        self.assertIsNone(selected["gis_preview"]["geometry"])
        comparison = result["candidate_comparison"][str(self.request.pk)]
        self.assertEqual(comparison[0]["result"], "RECOMMENDED")
        self.assertNotIn("safety_score", selected)

    @patch("transport_requests.dispatch.matrix.eligible_vehicle_origins")
    @patch("transport_requests.dispatch.matrix.build_dispatch_matrix")
    def test_number_coding_is_removed_before_matrix_and_explained(
        self, matrix_mock, origins_mock
    ):
        local_pickup = timezone.localtime(self.request.scheduled_pickup_at)
        NumberCodingRule.objects.create(
            authority="MMDA",
            jurisdiction="Metro Manila",
            weekday=local_pickup.weekday(),
            restricted_last_digits=[3],
            effective_from=local_pickup.date(),
            source_reference="Configured official source",
        )
        clear_vehicle = Vehicle.objects.create(
            device_id="VEH-CLEAR",
            plate_number="DEF-456",
            display_name="Clear Van",
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=8,
        )
        self.pass_inspection(clear_vehicle)
        origins_mock.return_value = [
            {"vehicle_id": clear_vehicle.device_id, "latitude": 14.6, "longitude": 121.1}
        ]
        matrix_mock.return_value = {
            "vehicle_ids": [clear_vehicle.device_id],
            "request_ids": [str(self.request.pk)],
            "durations_seconds": [[100]],
            "distances_meters": [[1000]],
            "traffic_delays_seconds": [[10]],
            "cell_statuses": [["OK"]],
        }

        result = dispatch.recommendations()

        matrix_mock.assert_called_once_with(
            [clear_vehicle.device_id], [self.request.pk], include_assigned=True
        )
        exclusion = next(
            item for item in result["excluded_candidates"][str(self.request.pk)]
            if item["code"] == self.vehicle.device_id
        )
        self.assertEqual(exclusion["reason"], "NUMBER_CODING_RESTRICTION")
        self.assertIn(
            "Number coding: clear for scheduled pickup",
            result["recommendations"][0]["explanation"],
        )

    def test_manual_override_shows_and_cannot_bypass_number_coding(self):
        local_pickup = timezone.localtime(self.request.scheduled_pickup_at)
        NumberCodingRule.objects.create(
            authority="MMDA",
            jurisdiction="Metro Manila",
            weekday=local_pickup.weekday(),
            restricted_last_digits=[3],
            effective_from=local_pickup.date(),
            source_reference="Configured official source",
        )

        board = self.client.get("/api/v1/transport-requests/dispatch-board/")

        vehicle = board.json()["manual_candidates"][str(self.request.pk)]["vehicles"][0]
        self.assertEqual(vehicle["number_coding"]["status"], "RESTRICTED")
        self.assertEqual(board.json()["summary"]["number_coding_blocked"], 1)
        response = self.confirmation(override_reason="Attempted manual override")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Number coding restriction", response.json()["vehicle"])

    def test_board_exposes_real_attention_and_persisted_audit_only(self):
        self.request.status = TransportRequest.Status.APPROVED
        self.request.save(update_fields=["status", "updated_at"])
        self.client.post(
            f"/api/v1/transport-requests/{self.request.pk}/prepare-dispatch/",
            {},
            format="json",
        )
        self.assertEqual(self.confirmation().status_code, 201)
        response = self.client.get("/api/v1/transport-requests/dispatch-board/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["ready_for_dispatch"], 1)
        events = payload["assignment_audit"][str(self.request.pk)]
        self.assertEqual(
            [event["kind"] for event in events],
            ["PREPARED_FOR_DISPATCH", "ASSIGNMENT_CONFIRMED"],
        )
        self.assertNotIn("RECOMMENDATION_GENERATED", [event["kind"] for event in events])

    def test_prepare_does_not_create_assignment(self):
        self.request.status = TransportRequest.Status.APPROVED
        self.request.save(update_fields=["status", "updated_at"])
        response = self.client.post(
            f"/api/v1/transport-requests/{self.request.pk}/prepare-dispatch/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "READY_FOR_DISPATCH")
        self.assertFalse(DispatchAssignment.objects.exists())
        board = self.client.get("/api/v1/transport-requests/dispatch-board/")
        self.assertIn(
            str(self.request.pk),
            {item["id"] for item in board.json()["requests"]},
        )

    def test_recommendation_token_rejects_changed_planning_inputs(self):
        token = dispatch.recommendation_token(
            self.request.pk, self.vehicle.pk, self.driver.pk
        )
        self.request.passenger_count = 5
        self.request.save(update_fields=["passenger_count", "updated_at"])
        response = self.confirmation(
            selection_mode="OPTIMIZED", override_reason="", recommendation_token=token
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("recommendation_token", response.json())
