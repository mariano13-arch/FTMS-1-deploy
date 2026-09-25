import json
import os
import subprocess
import sys
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Vehicle
from telemetry.models import TelemetryEvent
from transport_requests import matrix
from transport_requests.models import TransportRequest


class ResponseStub(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@override_settings(
    TOMTOM_API_KEY="matrix-test-key",
    TOMTOM_MATRIX_API_KEY="dedicated-matrix-test-key",
    DISPATCH_TELEMETRY_MAX_AGE_SECONDS=300,
    DISPATCH_SIMULATED_TELEMETRY_MAX_AGE_SECONDS=86400,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class DispatchMatrixTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="matrix-manager", is_staff=True)
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.FLEET_MANAGER)
        self.client.force_authenticate(self.user)
        self.vehicle_b = self.vehicle("VEH-B", 121.02, 14.52)
        self.vehicle_a = self.vehicle("VEH-A", 121.01, 14.51)
        self.request_b = self.transport_request("REQ-B", 121.12, 14.62)
        self.request_a = self.transport_request("REQ-A", 121.11, 14.61)

    def test_matrix_setting_falls_back_to_legacy_tomtom_key(self):
        environment = os.environ.copy()
        environment["DJANGO_SETTINGS_MODULE"] = "config.settings"
        environment["TOMTOM_API_KEY"] = "legacy-matrix-test-key"
        environment.pop("TOMTOM_MATRIX_API_KEY", None)
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from django.conf import settings; "
                    "raise SystemExit(0 if settings.TOMTOM_MATRIX_API_KEY == "
                    "'legacy-matrix-test-key' else 1)"
                ),
            ],
            capture_output=True,
            check=False,
            env=environment,
        )
        self.assertEqual(result.returncode, 0, "Matrix key fallback was not applied")

    def vehicle(self, device_id, longitude, latitude, *, active=True, telemetry=True):
        vehicle = Vehicle.objects.create(
            device_id=device_id, plate_number=device_id, display_name=device_id, is_active=active
        )
        if telemetry:
            self.telemetry(vehicle, longitude, latitude, 1)
        return vehicle

    def telemetry(self, vehicle, longitude, latitude, sequence, *, recorded_at=None):
        return TelemetryEvent.objects.create(
            schema_version="1.0",
            event_id=f"{vehicle.device_id}-{sequence}",
            sequence_number=sequence,
            vehicle=vehicle,
            recorded_at=recorded_at or timezone.now(),
            location=Point(longitude, latitude, srid=4326),
            gnss_speed_kph="10.00",
            driving_event=TelemetryEvent.DrivingEvent.NORMAL,
        )

    def simulated_position(self, vehicle, recorded_at):
        return TelemetryEvent.objects.create(
            schema_version="1.2",
            event_id=f"SIMULATED-{vehicle.device_id}",
            sequence_number=1,
            vehicle=vehicle,
            recorded_at=recorded_at,
            location=Point(121.02, 14.52, srid=4326),
            position_source=TelemetryEvent.PositionSource.SIMULATED_TEST,
            gnss_speed_kph=None,
            position_accuracy_m=None,
            obd_source=None,
        )

    def test_simulated_position_requires_debug_and_controlled_identifier(self):
        now = timezone.now()
        allowed = [
            self.vehicle(prefix, 0, 0, telemetry=False)
            for prefix in ("DEMO-V901", "FT-GT-901", "FT-ST-901")
        ]
        arbitrary = self.vehicle("OTHER-901", 0, 0, telemetry=False)
        for vehicle in [*allowed, arbitrary]:
            self.simulated_position(vehicle, now - timedelta(hours=23))
        identifiers = [vehicle.device_id for vehicle in [*allowed, arbitrary]]
        with override_settings(DEBUG=True), patch(
            "transport_requests.matrix.timezone.now", return_value=now
        ):
            origins = matrix.eligible_vehicle_origins(identifiers)
        self.assertEqual(
            [item["vehicle_id"] for item in origins],
            sorted(vehicle.device_id for vehicle in allowed),
        )
        with override_settings(DEBUG=False), patch(
            "transport_requests.matrix.timezone.now", return_value=now
        ):
            self.assertEqual(
                matrix.eligible_vehicle_origins(identifiers), []
            )

    def test_simulated_position_uses_24_hour_freshness_boundary(self):
        now = timezone.now()
        fresh = self.vehicle("FT-GT-902", 0, 0, telemetry=False)
        stale = self.vehicle("FT-ST-902", 0, 0, telemetry=False)
        self.simulated_position(fresh, now - timedelta(seconds=86399))
        self.simulated_position(stale, now - timedelta(seconds=86401))
        with override_settings(DEBUG=True), patch(
            "transport_requests.matrix.timezone.now", return_value=now
        ):
            origins = matrix.eligible_vehicle_origins([fresh.device_id, stale.device_id])
        self.assertEqual([item["vehicle_id"] for item in origins], [fresh.device_id])

    def test_real_position_sources_remain_stale_after_300_seconds(self):
        now = timezone.now()
        gnss = self.vehicle("REAL-GNSS", 0, 0, telemetry=False)
        cellular = self.vehicle("REAL-LBS", 0, 0, telemetry=False)
        self.telemetry(gnss, 121.02, 14.52, 1, recorded_at=now - timedelta(seconds=301))
        TelemetryEvent.objects.create(
            schema_version="1.2",
            event_id="CELLULAR-STALE",
            sequence_number=1,
            vehicle=cellular,
            recorded_at=now - timedelta(seconds=301),
            location=Point(121.02, 14.52, srid=4326),
            position_source=TelemetryEvent.PositionSource.CELLULAR_LBS,
            gnss_speed_kph=None,
            position_accuracy_m="50.00",
            obd_source=None,
        )
        with patch("transport_requests.matrix.timezone.now", return_value=now):
            self.assertEqual(
                matrix.eligible_vehicle_origins([gnss.device_id, cellular.device_id]), []
            )

    def transport_request(
        self,
        suffix,
        pickup_longitude,
        pickup_latitude,
        *,
        status=TransportRequest.Status.READY_FOR_DISPATCH,
        assigned_vehicle=None,
    ):
        return TransportRequest.objects.create(
            source_system="MANUAL_STAFF_ENTRY",
            request_type="GUEST_TRANSFER",
            external_reference=suffix,
            requester_name="Desk",
            pickup_name="Pickup",
            pickup_address="Pickup address",
            pickup_latitude=pickup_latitude,
            pickup_longitude=pickup_longitude,
            destination_name="Final destination",
            destination_address="Final address",
            destination_latitude=10.0,
            destination_longitude=100.0,
            scheduled_pickup_at=timezone.now() + timedelta(hours=2),
            passenger_count=2,
            created_by=self.user,
            status=status,
            assigned_vehicle=assigned_vehicle,
        )

    def payload(self):
        return {
            "data": [
                {
                    "originIndex": 1,
                    "destinationIndex": 1,
                    "routeSummary": {
                        "lengthInMeters": 4400,
                        "travelTimeInSeconds": 440,
                        "trafficDelayInSeconds": 44,
                        "departureTime": "now",
                        "arrivalTime": "later",
                    },
                },
                {
                    "originIndex": 0,
                    "destinationIndex": 0,
                    "routeSummary": {
                        "lengthInMeters": 1100,
                        "travelTimeInSeconds": 110,
                        "trafficDelayInSeconds": 11,
                        "departureTime": "now",
                        "arrivalTime": "later",
                    },
                },
                {
                    "originIndex": 0,
                    "destinationIndex": 1,
                    "detailedError": {
                        "code": "CELL_PROCESSING_ERROR",
                        "innerError": {"code": "NO_ROUTE_FOUND", "message": "private"},
                    },
                },
                {
                    "originIndex": 1,
                    "destinationIndex": 0,
                    "routeSummary": {
                        "lengthInMeters": 3300,
                        "travelTimeInSeconds": 330,
                        "trafficDelayInSeconds": 33,
                        "departureTime": "now",
                        "arrivalTime": "later",
                    },
                },
            ],
            "statistics": {"totalCount": 4, "successes": 3, "failures": 1},
        }

    def test_candidate_selection_uses_active_latest_telemetry_and_ready_unassigned_pickups(self):
        self.vehicle("INACTIVE", 121.3, 14.7, active=False)
        self.vehicle("NO-LOCATION", 121.3, 14.7, telemetry=False)
        self.telemetry(self.vehicle_a, 121.99, 14.99, 2)
        self.transport_request(
            "NOT-APPROVED", 121.5, 14.5, status=TransportRequest.Status.FOR_APPROVAL
        )
        self.transport_request("ASSIGNED", 121.6, 14.6, assigned_vehicle=self.vehicle_a)
        invalid = self.transport_request("INVALID-PICKUP", 121.7, 14.7)
        TransportRequest.objects.filter(pk=invalid.pk).update(pickup_latitude=99)
        origins = matrix.eligible_vehicle_origins()
        destinations = matrix.eligible_request_destinations()
        self.assertEqual([item["vehicle_id"] for item in origins], ["VEH-A", "VEH-B"])
        self.assertEqual((origins[0]["latitude"], origins[0]["longitude"]), (14.99, 121.99))
        self.assertEqual(
            [item["request_id"] for item in destinations],
            sorted([str(self.request_a.pk), str(self.request_b.pk)]),
        )
        self.assertTrue(
            all(
                item["latitude"] in {14.61, 14.62} and item["longitude"] in {121.11, 121.12}
                for item in destinations
            )
        )
        self.assertTrue(
            all(item["latitude"] != 10.0 and item["longitude"] != 100.0 for item in destinations)
        )

    def test_freshness_excludes_stale_and_missing_telemetry_without_fallback(self):
        now = timezone.now()
        fresh = self.vehicle("FRESH", 121.31, 14.71, telemetry=False)
        stale = self.vehicle("STALE", 121.32, 14.72, telemetry=False)
        missing = self.vehicle("MISSING", 121.33, 14.73, telemetry=False)
        self.telemetry(fresh, 121.31, 14.71, 1, recorded_at=now - timedelta(seconds=299))
        self.telemetry(stale, 121.32, 14.72, 1, recorded_at=now - timedelta(seconds=301))
        with patch("transport_requests.matrix.timezone.now", return_value=now):
            origins = matrix.eligible_vehicle_origins(
                [fresh.device_id, stale.device_id, missing.device_id]
            )
        self.assertEqual(origins, [{"vehicle_id": "FRESH", "latitude": 14.71, "longitude": 121.31}])

    def test_latest_record_controls_freshness_and_location(self):
        now = timezone.now()
        vehicle = self.vehicle("LATEST", 0, 0, telemetry=False)
        self.telemetry(vehicle, 120.1, 13.1, 1, recorded_at=now - timedelta(seconds=200))
        self.telemetry(vehicle, 121.2, 14.2, 2, recorded_at=now - timedelta(seconds=20))
        with patch("transport_requests.matrix.timezone.now", return_value=now):
            origins = matrix.eligible_vehicle_origins([vehicle.device_id])
        self.assertEqual(origins, [{"vehicle_id": "LATEST", "latitude": 14.2, "longitude": 121.2}])

    @override_settings(DISPATCH_TELEMETRY_MAX_AGE_SECONDS=30)
    def test_configured_freshness_threshold_and_boundary_are_deterministic(self):
        now = timezone.now()
        boundary = self.vehicle("BOUNDARY", 0, 0, telemetry=False)
        outside = self.vehicle("OUTSIDE", 0, 0, telemetry=False)
        self.telemetry(boundary, 121.4, 14.4, 1, recorded_at=now - timedelta(seconds=30))
        self.telemetry(
            outside, 121.5, 14.5, 1, recorded_at=now - timedelta(seconds=30, microseconds=1)
        )
        with patch("transport_requests.matrix.timezone.now", return_value=now):
            origins = matrix.eligible_vehicle_origins([boundary.device_id, outside.device_id])
        self.assertEqual(
            origins, [{"vehicle_id": "BOUNDARY", "latitude": 14.4, "longitude": 121.4}]
        )

    @patch("transport_requests.matrix._call_tomtom")
    def test_all_stale_telemetry_returns_controlled_error_before_tomtom(self, call_mock):
        now = timezone.now()
        TelemetryEvent.objects.update(recorded_at=now - timedelta(seconds=301))
        with patch("transport_requests.matrix.timezone.now", return_value=now):
            response = self.client.post(
                "/api/v1/transport-requests/dispatch-matrix/", {}, format="json"
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("No eligible vehicles", response.json()["detail"])
        call_mock.assert_not_called()

    def test_ready_zero_passenger_delivery_remains_matrix_eligible(self):
        delivery = self.transport_request("DELIVERY-ZERO", 121.21, 14.71)
        delivery.request_type = TransportRequest.RequestType.FOOD_DELIVERY
        delivery.request_category = TransportRequest.RequestCategory.DELIVERY_LOGISTICS
        delivery.passenger_count = 0
        delivery.load_description = "Meal trays"
        delivery.load_quantity = 8
        delivery.save(
            update_fields=[
                "request_type",
                "request_category",
                "passenger_count",
                "load_description",
                "load_quantity",
            ]
        )
        request_ids = {item["request_id"] for item in matrix.eligible_request_destinations()}
        self.assertIn(str(delivery.pk), request_ids)

    @patch("transport_requests.matrix.urlopen")
    def test_post_body_and_solver_mapping_are_normalized_with_partial_failure(self, urlopen_mock):
        urlopen_mock.return_value = ResponseStub(json.dumps(self.payload()).encode())
        result = matrix.build_dispatch_matrix()
        self.assertEqual(result["vehicle_ids"], ["VEH-A", "VEH-B"])
        expected_requests = sorted([str(self.request_a.pk), str(self.request_b.pk)])
        self.assertEqual(result["request_ids"], expected_requests)
        self.assertEqual(result["durations_seconds"], [[110, None], [330, 440]])
        self.assertEqual(result["distances_meters"], [[1100, None], [3300, 4400]])
        self.assertEqual(result["traffic_delays_seconds"], [[11, None], [33, 44]])
        self.assertEqual(result["cell_statuses"], [["OK", "NO_ROUTE"], ["OK", "OK"]])
        self.assertEqual(
            (result["vehicle_count"], result["request_count"], result["cell_count"]), (2, 2, 4)
        )
        outbound = urlopen_mock.call_args.args[0]
        body = json.loads(outbound.data)
        self.assertEqual(outbound.method, "POST")
        self.assertTrue(outbound.full_url.startswith(f"{matrix.MATRIX_URL}?key="))
        self.assertIn("key=dedicated-matrix-test-key", outbound.full_url)
        self.assertNotIn(
            "matrix-test-key",
            outbound.full_url.replace("dedicated-matrix-test-key", ""),
        )
        self.assertEqual(
            body["options"],
            {"departAt": "now", "traffic": "live", "routeType": "fastest", "travelMode": "car"},
        )
        self.assertEqual(body["origins"][0], {"point": {"latitude": 14.51, "longitude": 121.01}})
        self.assertNotIn("coordinates", body["origins"][0]["point"])
        self.assertEqual(
            body["destinations"][0]["point"]["latitude"],
            next(
                item["latitude"]
                for item in matrix.eligible_request_destinations()
                if item["request_id"] == expected_requests[0]
            ),
        )

    def test_malformed_duplicate_out_of_range_and_incomplete_results_are_rejected(self):
        origins = matrix.eligible_vehicle_origins()
        destinations = matrix.eligible_request_destinations()
        for payload in (
            {"unexpected": []},
            {"data": self.payload()["data"][:-1]},
            {"data": [{**cell, "originIndex": 5} for cell in self.payload()["data"]]},
            {"data": [self.payload()["data"][0]] * 4},
        ):
            with self.assertRaises(matrix.MatrixUpstreamError):
                matrix._normalize(payload, origins, destinations)

    @patch("transport_requests.matrix.urlopen")
    def test_429_timeout_and_connection_failures_are_safe_and_not_cached(self, urlopen_mock):
        urlopen_mock.side_effect = [
            HTTPError(matrix.MATRIX_URL, 429, "private", {}, None),
            TimeoutError(),
            URLError("private"),
        ]
        for _ in range(3):
            with self.assertRaises(matrix.MatrixUpstreamError):
                matrix.build_dispatch_matrix()
        self.assertEqual(urlopen_mock.call_count, 3)

    @patch("transport_requests.matrix.urlopen")
    def test_success_is_cached_and_coordinate_changes_invalidate_cache(self, urlopen_mock):
        urlopen_mock.return_value = ResponseStub(json.dumps(self.payload()).encode())
        matrix.build_dispatch_matrix()
        matrix.build_dispatch_matrix()
        self.assertEqual(urlopen_mock.call_count, 1)
        self.telemetry(self.vehicle_a, 121.77, 14.77, 3)
        urlopen_mock.return_value = ResponseStub(json.dumps(self.payload()).encode())
        matrix.build_dispatch_matrix()
        self.assertEqual(urlopen_mock.call_count, 2)
        self.request_a.pickup_latitude = 14.88
        self.request_a.save(update_fields=["pickup_latitude"])
        urlopen_mock.return_value = ResponseStub(json.dumps(self.payload()).encode())
        matrix.build_dispatch_matrix()
        self.assertEqual(urlopen_mock.call_count, 3)

    @patch("transport_requests.matrix._call_tomtom")
    def test_100_cell_limit_accepts_boundary_and_rejects_above_before_upstream(self, call_mock):
        call_mock.return_value = {"cell_count": 100}
        origins = [{"vehicle_id": str(i), "latitude": 14, "longitude": 121} for i in range(10)]
        destinations = [{"request_id": str(i), "latitude": 14, "longitude": 121} for i in range(10)]
        with (
            patch("transport_requests.matrix.eligible_vehicle_origins", return_value=origins),
            patch(
                "transport_requests.matrix.eligible_request_destinations", return_value=destinations
            ),
        ):
            self.assertEqual(matrix.build_dispatch_matrix()["cell_count"], 100)
        with (
            patch(
                "transport_requests.matrix.eligible_vehicle_origins",
                return_value=origins + [origins[0]],
            ),
            patch(
                "transport_requests.matrix.eligible_request_destinations", return_value=destinations
            ),
        ):
            with self.assertRaises(matrix.MatrixLimitError):
                matrix.build_dispatch_matrix()
        self.assertEqual(call_mock.call_count, 1)

    @patch("transport_requests.matrix.urlopen")
    def test_endpoint_auth_filters_unknown_coordinates_and_controlled_empty_states(
        self, urlopen_mock
    ):
        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.post(
                "/api/v1/transport-requests/dispatch-matrix/", {}, format="json"
            ).status_code,
            401,
        )
        self.client.force_authenticate(self.user)
        self.assertEqual(
            self.client.post(
                "/api/v1/transport-requests/dispatch-matrix/",
                {"origins": [{"latitude": 1}]},
                format="json",
            ).status_code,
            400,
        )
        no_vehicle = self.client.post(
            "/api/v1/transport-requests/dispatch-matrix/",
            {"vehicle_ids": ["UNKNOWN"]},
            format="json",
        )
        no_request = self.client.post(
            "/api/v1/transport-requests/dispatch-matrix/",
            {"request_ids": ["11111111-1111-4111-8111-111111111111"]},
            format="json",
        )
        self.assertEqual(no_vehicle.status_code, 400)
        self.assertIn("No eligible vehicles", no_vehicle.json()["detail"])
        self.assertEqual(no_request.status_code, 400)
        self.assertIn("No dispatch-eligible requests", no_request.json()["detail"])
        urlopen_mock.assert_not_called()

    def test_endpoint_reports_over_limit_without_calling_tomtom(self):
        origins = [{"vehicle_id": str(i), "latitude": 14, "longitude": 121} for i in range(11)]
        destinations = [{"request_id": str(i), "latitude": 14, "longitude": 121} for i in range(10)]
        with (
            patch("transport_requests.matrix.eligible_vehicle_origins", return_value=origins),
            patch(
                "transport_requests.matrix.eligible_request_destinations", return_value=destinations
            ),
            patch("transport_requests.matrix.urlopen") as urlopen_mock,
        ):
            response = self.client.post(
                "/api/v1/transport-requests/dispatch-matrix/", {}, format="json"
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("100-cell", response.json()["detail"])
        urlopen_mock.assert_not_called()

    @override_settings(TOMTOM_API_KEY="", TOMTOM_MATRIX_API_KEY="")
    def test_missing_matrix_key_is_safe_and_does_not_call_upstream(self):
        with patch("transport_requests.matrix.urlopen") as urlopen_mock:
            response = self.client.post(
                "/api/v1/transport-requests/dispatch-matrix/", {}, format="json"
            )
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("key", response.json()["detail"].lower())
        urlopen_mock.assert_not_called()
