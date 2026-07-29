# ruff: noqa: E501
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Vehicle
from telemetry.models import TelemetryEvent


class VehicleRegistryTests(TestCase):
    password = "A-strong-test-password-42!"

    def setUp(self):
        self.client = APIClient()
        self.vehicle = Vehicle.objects.create(
            device_id="LILYGO-001", plate_number="DEMO-001",
            display_name="Sprint 1 Demo Vehicle",
        )

    def user(self, role=None, superuser=False):
        user = get_user_model().objects.create_user(
            username=f"user-{get_user_model().objects.count()}",
            password=self.password, is_staff=True,
            is_superuser=superuser,
        )
        if role:
            StaffProfile.objects.create(user=user, role=role)
        return user

    def authenticate(self, user):
        self.assertTrue(
            self.client.login(username=user.username, password=self.password)
        )

    def payload(self):
        return {
            "device_id": "TEST-001", "plate_number": "test-001",
            "display_name": " Test Vehicle ", "vehicle_type": "VAN",
            "manufacturer": " Maker ", "model": " Model ", "model_year": 2026,
            "passenger_capacity": 12,
        }

    def test_anonymous_registry_and_latest_are_401(self):
        self.assertEqual(self.client.get("/api/v1/vehicles/").status_code, 401)
        self.assertEqual(
            self.client.get("/api/v1/vehicles/LILYGO-001/latest-status/").status_code,
            401,
        )

    def test_dispatcher_reads_but_cannot_write(self):
        self.authenticate(self.user(StaffProfile.Role.DISPATCHER))
        self.assertEqual(self.client.get("/api/v1/vehicles/").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/vehicles/", self.payload(), format="json").status_code, 403)
        self.assertEqual(self.client.patch("/api/v1/vehicles/LILYGO-001/", {"display_name": "No"}, format="json").status_code, 403)

    def test_manager_edits_but_cannot_create_or_change_status(self):
        self.authenticate(self.user(StaffProfile.Role.FLEET_MANAGER))
        self.assertEqual(self.client.patch("/api/v1/vehicles/LILYGO-001/", {"display_name": " Updated "}, format="json").status_code, 200)
        self.assertEqual(Vehicle.objects.get().display_name, "Updated")
        self.assertEqual(self.client.post("/api/v1/vehicles/", self.payload(), format="json").status_code, 403)
        self.assertEqual(self.client.post("/api/v1/vehicles/LILYGO-001/deactivate/", {}, format="json").status_code, 403)

    def test_superadmin_create_normalization_immutability_and_status(self):
        self.authenticate(self.user(superuser=True))
        response = self.client.post("/api/v1/vehicles/", self.payload(), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["plate_number"], "TEST-001")
        self.assertEqual(response.json()["display_name"], "Test Vehicle")
        self.assertEqual(self.client.patch("/api/v1/vehicles/TEST-001/", {"device_id": "OTHER"}, format="json").status_code, 400)
        self.assertFalse(self.client.post("/api/v1/vehicles/TEST-001/deactivate/", {}, format="json").json()["is_active"])
        self.assertTrue(self.client.post("/api/v1/vehicles/TEST-001/reactivate/", {}, format="json").json()["is_active"])

    def test_unknown_readonly_fields_methods_and_case_insensitive_plate(self):
        self.authenticate(self.user(superuser=True))
        for payload in (
            {**self.payload(), "unknown": True},
            {**self.payload(), "is_active": False},
            {**self.payload(), "created_at": "2026-01-01T00:00:00Z"},
            {**self.payload(), "updated_at": "2026-01-01T00:00:00Z"},
        ):
            self.assertEqual(self.client.post("/api/v1/vehicles/", payload, format="json").status_code, 400)
        duplicate = {**self.payload(), "device_id": "TEST-002", "plate_number": "demo-001"}
        self.assertEqual(self.client.post("/api/v1/vehicles/", duplicate, format="json").status_code, 400)
        self.assertEqual(self.client.put("/api/v1/vehicles/LILYGO-001/", {}, format="json").status_code, 405)
        self.assertEqual(self.client.delete("/api/v1/vehicles/LILYGO-001/").status_code, 405)
        for field in ("created_at", "updated_at", "device_id", "is_active"):
            self.assertEqual(
                self.client.patch(
                    "/api/v1/vehicles/LILYGO-001/", {field: "forbidden"}, format="json"
                ).status_code,
                400,
            )

    def test_incorrect_types_and_dynamic_model_year_bounds_return_400(self):
        self.authenticate(self.user(superuser=True))
        for field, value in (
            ("device_id", 123),
            ("plate_number", True),
            ("display_name", []),
            ("vehicle_type", {}),
            ("manufacturer", 12),
            ("model", False),
            ("model_year", "2026"),
            ("passenger_capacity", "12"),
            ("model_year", 1979),
            ("model_year", 9999),
        ):
            with self.subTest(field=field, value=value):
                response = self.client.post(
                    "/api/v1/vehicles/", {**self.payload(), field: value}, format="json"
                )
                self.assertEqual(response.status_code, 400)

    def test_deactivation_preserves_history_and_reactivation_restores_ingestion(self):
        self.authenticate(self.user(superuser=True))
        payload = {
            "schema_version": "1.0", "event_id": "registry-history",
            "sequence_number": 1, "device_id": "LILYGO-001",
            "recorded_at": "2026-07-30T00:00:00Z",
            "latitude": 14.5, "longitude": 121,
            "gnss_speed_kph": 20, "rpm": None, "coolant_c": None,
            "engine_load_pct": None, "driving_event": "NORMAL",
        }
        self.assertEqual(
            self.client.post("/api/v1/telemetry/", payload, format="json").status_code,
            201,
        )
        self.client.post("/api/v1/vehicles/LILYGO-001/deactivate/", {}, format="json")
        self.assertEqual(TelemetryEvent.objects.count(), 1)
        rejected = {**payload, "event_id": "inactive", "sequence_number": 2}
        self.assertEqual(
            self.client.post("/api/v1/telemetry/", rejected, format="json").status_code,
            400,
        )
        self.client.post("/api/v1/vehicles/LILYGO-001/reactivate/", {}, format="json")
        self.assertEqual(
            self.client.post("/api/v1/telemetry/", rejected, format="json").status_code,
            201,
        )

    def test_filters_search_pagination_and_invalid_values(self):
        self.authenticate(self.user(StaffProfile.Role.DISPATCHER))
        response = self.client.get("/api/v1/vehicles/?search=demo&is_active=true&vehicle_type=OTHER&page_size=100")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["device_id"], "LILYGO-001")
        for query in ("is_active=yes", "vehicle_type=BOAT", "unknown=x", "page_size=101"):
            self.assertEqual(self.client.get(f"/api/v1/vehicles/?{query}").status_code, 400)


class LatestStatusSessionAuthorizationTests(TestCase):
    def setUp(self):
        self.vehicle = Vehicle.objects.create(
            device_id="LILYGO-001", plate_number="DEMO-001",
            display_name="Sprint 1 Demo Vehicle",
        )

    def create_user(self, username, *, role=None, staff=True, superuser=False):
        user = get_user_model().objects.create_user(
            username=username, password="A-strong-test-password-42!",
            is_staff=staff, is_superuser=superuser,
        )
        if role:
            StaffProfile.objects.create(user=user, role=role)
        return user

    def session_client(self, user):
        client = APIClient()
        client.login(username=user.username, password="A-strong-test-password-42!")
        return client

    def test_anonymous_is_401(self):
        self.assertEqual(
            APIClient().get("/api/v1/vehicles/LILYGO-001/latest-status/").status_code,
            401,
        )

    def test_all_three_roles_are_allowed(self):
        users = [
            self.create_user("admin", superuser=True),
            self.create_user("manager", role=StaffProfile.Role.FLEET_MANAGER),
            self.create_user("dispatcher", role=StaffProfile.Role.DISPATCHER),
        ]
        for user in users:
            with self.subTest(username=user.username):
                self.assertEqual(
                    self.session_client(user).get(
                        "/api/v1/vehicles/LILYGO-001/latest-status/"
                    ).status_code,
                    200,
                )

    def test_nonstaff_and_profileless_staff_are_403_before_lookup(self):
        users = [
            self.create_user("nonstaff", staff=False),
            self.create_user("profileless"),
        ]
        for user in users:
            client = self.session_client(user)
            with self.subTest(username=user.username):
                self.assertEqual(
                    client.get("/api/v1/vehicles/LILYGO-001/latest-status/").status_code,
                    403,
                )
                self.assertEqual(
                    client.get("/api/v1/vehicles/UNKNOWN/latest-status/").status_code,
                    403,
                )

    def test_authorized_unknown_is_404(self):
        user = self.create_user("dispatcher", role=StaffProfile.Role.DISPATCHER)
        self.assertEqual(
            self.session_client(user).get(
                "/api/v1/vehicles/UNKNOWN/latest-status/"
            ).status_code,
            404,
        )
