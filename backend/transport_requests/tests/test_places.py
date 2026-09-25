import json
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from transport_requests import places


class ResponseStub(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@override_settings(TOMTOM_API_KEY="server-places-test-key")
class TransportRequestPlacesTests(TestCase):
    session_id = "f12632e2-c497-4e6a-9d36-164d5e601aec"

    def setUp(self):
        self.client = APIClient()
        user = get_user_model().objects.create_user(username="places-manager", is_staff=True)
        StaffProfile.objects.create(user=user, role=StaffProfile.Role.FLEET_MANAGER)
        self.client.force_authenticate(user)

    def suggestion_payload(self):
        return {
            "results": [
                {
                    "id": "oxford/id",
                    "type": "POI",
                    "poi": {"name": "Oxford Suites Makati"},
                    "address": {"freeformAddress": "Poblacion, Makati"},
                    "position": {"lat": 14.5652, "lon": 121.0286},
                },
                {"id": "ignored", "type": "Category", "poi": {"name": "Hotels"}},
            ]
        }

    @patch("transport_requests.places.urlopen")
    def test_authenticated_suggest_normalizes_and_fixes_request_scope(self, urlopen_mock):
        urlopen_mock.return_value = ResponseStub(json.dumps(self.suggestion_payload()).encode())
        response = self.client.post(
            "/api/v1/transport-requests/places/suggest/",
            {"query": " Oxford Sui ", "session_id": self.session_id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "results": [
                    {
                        "id": "oxford/id",
                        "type": "poi",
                        "title": "Oxford Suites Makati",
                        "subtitles": ["Poblacion, Makati"],
                    }
                ]
            },
        )
        outbound = urlopen_mock.call_args.args[0]
        self.assertIn("/search/2/search/Oxford%20Sui.json?", outbound.full_url)
        self.assertIn("countrySet=PH", outbound.full_url)
        self.assertIn("view=Unified", outbound.full_url)
        self.assertIn("language=en-US", outbound.full_url)

    def test_permission_short_query_and_invalid_session_do_not_call_tomtom(self):
        with patch("transport_requests.places.urlopen") as urlopen_mock:
            short = self.client.post(
                "/api/v1/transport-requests/places/suggest/",
                {"query": "ab", "session_id": self.session_id},
                format="json",
            )
            invalid = self.client.post(
                "/api/v1/transport-requests/places/suggest/",
                {"query": "Oxford", "session_id": "not-a-uuid"},
                format="json",
            )
            self.assertEqual(short.status_code, 400)
            self.assertEqual(invalid.status_code, 400)
            urlopen_mock.assert_not_called()
        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.post(
                "/api/v1/transport-requests/places/suggest/", {}, format="json"
            ).status_code,
            401,
        )

    @patch("transport_requests.places.urlopen")
    def test_empty_suggestions(self, urlopen_mock):
        urlopen_mock.return_value = ResponseStub(b'{"results": []}')
        response = self.client.post(
            "/api/v1/transport-requests/places/suggest/",
            {"query": "unknown", "session_id": self.session_id},
            format="json",
        )
        self.assertEqual(response.json(), {"results": []})

    @patch("transport_requests.places.urlopen")
    def test_details_normalizes_coordinates_address_and_type_mapping(self, urlopen_mock):
        urlopen_mock.return_value = ResponseStub(json.dumps(self.suggestion_payload()).encode())
        self.client.post(
            "/api/v1/transport-requests/places/suggest/",
            {"query": "Oxford", "session_id": self.session_id},
            format="json",
        )
        response = self.client.get(
            f"/api/v1/transport-requests/places/details/poi/oxford%2Fid/?session_id={self.session_id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["latitude"], 14.5652)
        self.assertEqual(response.json()["longitude"], 121.0286)
        self.assertEqual(response.json()["display_address"], "Poblacion, Makati")
        self.assertEqual(urlopen_mock.call_count, 1)

    def test_invalid_details_type_rejected_without_upstream_call(self):
        with patch("transport_requests.places.urlopen") as urlopen_mock:
            response = self.client.get(
                f"/api/v1/transport-requests/places/details/discoverAction/id/?session_id={self.session_id}"
            )
            self.assertEqual(response.status_code, 400)
            urlopen_mock.assert_not_called()

    @patch("transport_requests.places.urlopen")
    def test_timeout_429_malformed_and_missing_coordinates_are_safe(self, urlopen_mock):
        suggest_url = "/api/v1/transport-requests/places/suggest/"
        body = {"query": "Oxford", "session_id": self.session_id}
        urlopen_mock.side_effect = TimeoutError()
        self.assertEqual(self.client.post(suggest_url, body, format="json").status_code, 503)
        urlopen_mock.side_effect = URLError("private connection detail")
        self.assertEqual(self.client.post(suggest_url, body, format="json").status_code, 503)
        urlopen_mock.side_effect = HTTPError(places.SEARCH_URL, 429, "private", {}, None)
        self.assertEqual(self.client.post(suggest_url, body, format="json").status_code, 503)
        urlopen_mock.side_effect = None
        urlopen_mock.return_value = ResponseStub(b"not-json")
        self.assertEqual(self.client.post(suggest_url, body, format="json").status_code, 502)
        response = self.client.get(
            f"/api/v1/transport-requests/places/details/poi/x/?session_id={self.session_id}"
        )
        self.assertEqual(response.status_code, 404)

    @override_settings(TOMTOM_API_KEY="", TOMTOM_SEARCH_API_KEY="")
    def test_missing_key_is_safe(self):
        response = self.client.post(
            "/api/v1/transport-requests/places/suggest/",
            {"query": "Oxford", "session_id": self.session_id},
            format="json",
        )
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("key", response.json()["detail"].lower())
