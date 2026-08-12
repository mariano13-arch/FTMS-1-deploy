import json
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from transport_requests import routing
from transport_requests.models import TransportRequest


class ResponseStub(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@override_settings(
    TOMTOM_API_KEY="server-test-key",
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class TransportRequestRoutingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="route-manager", is_staff=True)
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.FLEET_MANAGER)
        self.item = TransportRequest.objects.create(
            source_system="MANUAL_STAFF_ENTRY",
            request_type="GUEST_TRANSFER",
            requester_name="Front Desk",
            pickup_name="NAIA",
            pickup_address="Pasay",
            pickup_latitude="14.508600",
            pickup_longitude="121.019800",
            destination_name="Oxford Suites",
            destination_address="Makati",
            destination_latitude="14.565200",
            destination_longitude="121.028600",
            scheduled_pickup_at=timezone.now() + timedelta(hours=1),
            passenger_count=2,
            created_by=self.user,
        )
        self.client.force_authenticate(self.user)

    def payload(self, legs=None):
        return {
            "routes": [
                {
                    "summary": {
                        "lengthInMeters": 12400,
                        "travelDurationInSeconds": 1860,
                        "trafficDelayDurationInSeconds": 360,
                        "departureDateTime": "2026-08-07T10:00:00+08:00",
                        "arrivalDateTime": "2026-08-07T10:31:00+08:00",
                    },
                    "legs": legs
                    or [
                        {
                            "path": {
                                "type": "LineString",
                                "coordinates": [[121.0198, 14.5086], [121.0286, 14.5652]],
                            }
                        }
                    ],
                }
            ]
        }

    @patch("transport_requests.routing.urlopen")
    def test_authenticated_route_normalizes_request_and_response(self, urlopen_mock):
        urlopen_mock.return_value = ResponseStub(json.dumps(self.payload()).encode())
        response = self.client.get(f"/api/v1/transport-requests/{self.item.pk}/route/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["distance_meters"], 12400)
        self.assertEqual(response.json()["duration_seconds"], 1860)
        self.assertEqual(response.json()["traffic_delay_seconds"], 360)
        self.assertEqual(response.json()["geometry"]["type"], "LineString")
        outbound = urlopen_mock.call_args.args[0]
        body = json.loads(outbound.data)
        self.assertEqual(
            body["routePlanningLocations"]["origin"]["coordinates"], [121.0198, 14.5086]
        )
        self.assertEqual(body["traffic"], "live")
        self.assertEqual(body["routeType"], "fast")
        self.assertEqual(body["travelMode"], "car")
        self.assertEqual(body["maxPathAlternativeRoutes"], 0)
        self.assertEqual(outbound.get_header("Tomtom-api-version"), "3")
        self.assertEqual(outbound.get_header("Attributes"), "routes(summary,legs.path)")

    def test_route_requires_staff_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.get(f"/api/v1/transport-requests/{self.item.pk}/route/").status_code, 401
        )

    @override_settings(TOMTOM_API_KEY="")
    def test_missing_server_key_is_safe(self):
        response = self.client.get(f"/api/v1/transport-requests/{self.item.pk}/route/")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("key", response.json()["detail"].lower())

    def test_missing_and_invalid_coordinates_are_rejected(self):
        with self.assertRaises(routing.RouteCoordinateError):
            routing._request_coordinates(
                SimpleNamespace(
                    pickup_longitude=None,
                    pickup_latitude=14,
                    destination_longitude=121,
                    destination_latitude=14,
                )
            )
        TransportRequest.objects.filter(pk=self.item.pk).update(pickup_latitude=99)
        self.assertEqual(
            self.client.get(f"/api/v1/transport-requests/{self.item.pk}/route/").status_code, 400
        )

    @patch(
        "transport_requests.routing.urlopen",
        side_effect=[TimeoutError(), URLError("private upstream detail")],
    )
    def test_timeout_or_upstream_failure_is_generic_and_not_cached(self, urlopen_mock):
        url = f"/api/v1/transport-requests/{self.item.pk}/route/"
        first = self.client.get(url)
        second = self.client.get(url)
        self.assertEqual(first.status_code, 502)
        self.assertEqual(second.status_code, 502)
        self.assertEqual(urlopen_mock.call_count, 2)
        self.assertEqual(first.json(), {"detail": "Route unavailable."})

    @patch("transport_requests.routing.urlopen")
    def test_http_429_malformed_and_no_route_are_safe(self, urlopen_mock):
        url = f"/api/v1/transport-requests/{self.item.pk}/route/"
        urlopen_mock.side_effect = HTTPError(routing.ROUTING_URL, 429, "secret", {}, None)
        self.assertEqual(self.client.get(url).status_code, 502)
        urlopen_mock.side_effect = None
        urlopen_mock.return_value = ResponseStub(b"not-json")
        self.assertEqual(self.client.get(url).status_code, 502)
        urlopen_mock.return_value = ResponseStub(b'{"routes": []}')
        self.assertEqual(self.client.get(url).status_code, 502)

    @patch("transport_requests.routing.urlopen")
    def test_multiple_legs_merge_duplicate_join_and_cache(self, urlopen_mock):
        legs = [
            {"path": {"type": "LineString", "coordinates": [[121.0, 14.5], [121.1, 14.6]]}},
            {"path": {"type": "LineString", "coordinates": [[121.1, 14.6], [121.2, 14.7]]}},
        ]
        urlopen_mock.return_value = ResponseStub(json.dumps(self.payload(legs)).encode())
        url = f"/api/v1/transport-requests/{self.item.pk}/route/"
        first = self.client.get(url)
        second = self.client.get(url)
        self.assertEqual(
            first.json()["geometry"]["coordinates"], [[121.0, 14.5], [121.1, 14.6], [121.2, 14.7]]
        )
        self.assertEqual(second.json(), first.json())
        self.assertEqual(urlopen_mock.call_count, 1)
