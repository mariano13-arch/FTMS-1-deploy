from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Vehicle
from telemetry.models import TelemetryEvent


class TelemetryApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="dispatcher", password="Strong-test-password-42!", is_staff=True
        )
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.DISPATCHER)
        self.client.force_authenticate(self.user)
        self.vehicle = Vehicle.objects.create(
            device_id="LILYGO-001",
            plate_number="DEMO-001",
            display_name="Sprint 1 Demo Vehicle",
        )
        self.payload = {
            "schema_version": "1.0",
            "event_id": "evt-000311",
            "sequence_number": 311,
            "device_id": "LILYGO-001",
            "recorded_at": "2026-07-29T09:18:20+08:00",
            "latitude": 14.5186,
            "longitude": 121.0196,
            "gnss_speed_kph": 38.2,
            "rpm": 1750,
            "coolant_c": 88,
            "engine_load_pct": 34,
            "driving_event": "NORMAL",
        }

    def post(self, payload=None):
        return self.client.post("/api/v1/telemetry/", payload or self.payload, format="json")

    def test_valid_event_is_persisted_in_postgis(self):
        response = self.post()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "created")
        self.assertFalse(response.json()["duplicate"])
        self.assertNotIn("created", response.json())
        event = TelemetryEvent.objects.get()
        self.assertEqual(event.location.srid, 4326)
        self.assertAlmostEqual(event.location.y, 14.5186)
        self.assertAlmostEqual(event.location.x, 121.0196)
        self.assertEqual(event.position_source, TelemetryEvent.PositionSource.GNSS)
        self.assertIsNone(event.position_accuracy_m)

    def test_accepts_source_aware_gnss_v1_1(self):
        payload = {**self.payload, "schema_version": "1.1", "position_source": "GNSS",
                   "position_accuracy_m": None}
        response = self.post(payload)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(TelemetryEvent.objects.get().position_source, "GNSS")

    def test_accepts_cellular_lbs_v1_1_without_gnss_speed(self):
        payload = {**self.payload, "schema_version": "1.1",
                   "position_source": "CELLULAR_LBS", "position_accuracy_m": 550,
                   "gnss_speed_kph": None}
        response = self.post(payload)
        self.assertEqual(response.status_code, 201)
        event = TelemetryEvent.objects.get()
        self.assertEqual(event.position_source, "CELLULAR_LBS")
        self.assertEqual(event.position_accuracy_m, Decimal("550.00"))
        self.assertIsNone(event.gnss_speed_kph)

    def test_accepts_v1_2_simulated_test_obd_provenance(self):
        payload = {
            **self.payload,
            "schema_version": "1.2",
            "position_source": "GNSS",
            "position_accuracy_m": None,
            "obd_source": "SIMULATED_TEST",
        }
        self.assertEqual(self.post(payload).status_code, 201)
        event = TelemetryEvent.objects.get()
        self.assertEqual(event.obd_source, TelemetryEvent.ObdSource.SIMULATED_TEST)
        self.assertEqual(event.rpm, 1750)

    def test_accepts_v1_2_physical_obd_provenance(self):
        payload = {
            **self.payload,
            "schema_version": "1.2",
            "position_source": "GNSS",
            "position_accuracy_m": None,
            "obd_source": "PHYSICAL_OBD",
        }
        self.assertEqual(self.post(payload).status_code, 201)
        self.assertEqual(TelemetryEvent.objects.get().obd_source, "PHYSICAL_OBD")

    def test_v1_2_rejects_obd_values_without_provenance(self):
        payload = {
            **self.payload,
            "schema_version": "1.2",
            "position_source": "GNSS",
            "position_accuracy_m": None,
        }
        self.assertEqual(self.post(payload).status_code, 400)
        self.assertFalse(TelemetryEvent.objects.exists())

    def test_v1_2_allows_null_obd_values_and_null_provenance(self):
        payload = {
            **self.payload,
            "schema_version": "1.2",
            "position_source": "CELLULAR_LBS",
            "position_accuracy_m": 550,
            "gnss_speed_kph": None,
            "rpm": None,
            "coolant_c": None,
            "engine_load_pct": None,
            "driving_event": None,
            "obd_source": None,
        }
        self.assertEqual(self.post(payload).status_code, 201)
        event = TelemetryEvent.objects.get()
        self.assertIsNone(event.obd_source)
        self.assertIsNone(event.rpm)

    def test_rejects_cellular_lbs_with_gnss_speed(self):
        payload = {**self.payload, "schema_version": "1.1",
                   "position_source": "CELLULAR_LBS", "position_accuracy_m": 550}
        self.assertEqual(self.post(payload).status_code, 400)
        self.assertFalse(TelemetryEvent.objects.exists())

    def test_rejects_cellular_lbs_without_accuracy(self):
        payload = {**self.payload, "schema_version": "1.1",
                   "position_source": "CELLULAR_LBS", "gnss_speed_kph": None}
        self.assertEqual(self.post(payload).status_code, 400)
        self.assertFalse(TelemetryEvent.objects.exists())

    def test_model_validation_enforces_position_source_semantics(self):
        self.post()
        event = TelemetryEvent.objects.get()
        event.position_source = TelemetryEvent.PositionSource.CELLULAR_LBS
        event.position_accuracy_m = None
        with self.assertRaises(ValidationError):
            event.full_clean()

        event.position_accuracy_m = Decimal("100.00")
        event.gnss_speed_kph = None
        event.full_clean()

        event.position_source = TelemetryEvent.PositionSource.GNSS
        with self.assertRaises(ValidationError):
            event.full_clean()

    def test_exact_duplicate_is_idempotent(self):
        self.post()
        response = self.post()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "duplicate")
        self.assertTrue(response.json()["duplicate"])
        self.assertNotIn("created", response.json())
        self.assertEqual(TelemetryEvent.objects.count(), 1)

    def test_equivalent_numeric_and_timezone_values_are_duplicate(self):
        self.post()
        duplicate = deepcopy(self.payload)
        duplicate.update(
            {
                "recorded_at": "2026-07-29T01:18:20Z",
                "latitude": "14.518600",
                "longitude": "121.019600",
                "gnss_speed_kph": "38.20",
                "coolant_c": "88.00",
                "engine_load_pct": "34.00",
            }
        )

        response = self.post(duplicate)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["duplicate"])

    def test_conflicting_event_id_returns_409_without_modification(self):
        self.post()
        conflict = deepcopy(self.payload)
        conflict["gnss_speed_kph"] = 40

        response = self.post(conflict)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(),
            {"detail": "event_id already exists with different telemetry data."},
        )
        self.assertEqual(TelemetryEvent.objects.get().gnss_speed_kph, Decimal("38.20"))

    def test_nullable_obd_values_remain_null(self):
        payload = deepcopy(self.payload)
        payload.update({"rpm": None, "coolant_c": None, "engine_load_pct": None})

        response = self.post(payload)

        self.assertEqual(response.status_code, 201)
        event = TelemetryEvent.objects.get()
        self.assertIsNone(event.rpm)
        self.assertIsNone(event.coolant_c)
        self.assertIsNone(event.engine_load_pct)

    def test_legitimate_numeric_zero_remains_zero(self):
        payload = deepcopy(self.payload)
        payload.update(
            {
                "gnss_speed_kph": 0,
                "rpm": 0,
                "coolant_c": 0,
                "engine_load_pct": 0,
            }
        )

        response = self.post(payload)

        self.assertEqual(response.status_code, 201)
        event = TelemetryEvent.objects.get()
        self.assertEqual(event.gnss_speed_kph, Decimal("0.00"))
        self.assertEqual(event.rpm, 0)
        self.assertEqual(event.coolant_c, Decimal("0.00"))
        self.assertEqual(event.engine_load_pct, Decimal("0.00"))
        self.assertEqual(response.json()["event"]["rpm"], 0)

    def test_received_at_is_server_generated_and_persisted(self):
        before = datetime.now(UTC)
        response = self.post()
        after = datetime.now(UTC)

        event = TelemetryEvent.objects.get()
        self.assertLessEqual(before, event.received_at)
        self.assertLessEqual(event.received_at, after)
        self.assertEqual(
            response.json()["event"]["received_at"],
            event.received_at.isoformat().replace("+00:00", "Z"),
        )

    def test_offset_recorded_at_is_stored_and_returned_in_utc(self):
        response = self.post()

        event = TelemetryEvent.objects.get()
        self.assertEqual(event.recorded_at, datetime(2026, 7, 29, 1, 18, 20, tzinfo=UTC))
        self.assertEqual(response.json()["event"]["recorded_at"], "2026-07-29T01:18:20Z")

    def test_rejects_unsupported_schema_version(self):
        payload = deepcopy(self.payload)
        payload["schema_version"] = "2.0"
        response = self.post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(TelemetryEvent.objects.count(), 0)

    def test_safe_validation_error_excludes_internal_details(self):
        payload = deepcopy(self.payload)
        payload["device_id"] = "UNKNOWN"

        response = self.post(payload)

        rendered = response.content.decode().lower()
        for forbidden in (
            "database_url",
            "postgres",
            "password",
            "select ",
            "traceback",
            "programmingerror",
            "psycopg",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, rendered)

    def test_rejects_unknown_device(self):
        payload = deepcopy(self.payload)
        payload["device_id"] = "UNKNOWN"
        self.assertEqual(self.post(payload).status_code, 400)

    def test_rejects_inactive_vehicle(self):
        self.vehicle.is_active = False
        self.vehicle.save()
        self.assertEqual(self.post().status_code, 400)

    def test_rejects_naive_recorded_at(self):
        payload = deepcopy(self.payload)
        payload["recorded_at"] = "2026-07-29T01:18:20"
        self.assertEqual(self.post(payload).status_code, 400)

    @override_settings(FTMS_TELEMETRY_CLOCK_SKEW_SECONDS=300)
    def test_accepts_current_recorded_at(self):
        now = datetime(2026, 7, 29, 1, 18, 20, tzinfo=UTC)
        payload = deepcopy(self.payload)
        payload["recorded_at"] = now.isoformat()

        with patch("telemetry.serializers.timezone.now", return_value=now):
            response = self.post(payload)

        self.assertEqual(response.status_code, 201)

    @override_settings(FTMS_TELEMETRY_CLOCK_SKEW_SECONDS=300)
    def test_accepts_recorded_at_within_clock_skew(self):
        now = datetime(2026, 7, 29, 1, 18, 20, tzinfo=UTC)
        payload = deepcopy(self.payload)
        payload["recorded_at"] = (now + timedelta(seconds=299)).isoformat()

        with patch("telemetry.serializers.timezone.now", return_value=now):
            response = self.post(payload)

        self.assertEqual(response.status_code, 201)

    @override_settings(FTMS_TELEMETRY_CLOCK_SKEW_SECONDS=300)
    def test_rejects_recorded_at_beyond_clock_skew(self):
        now = datetime(2026, 7, 29, 1, 18, 20, tzinfo=UTC)
        payload = deepcopy(self.payload)
        payload["recorded_at"] = (now + timedelta(seconds=301)).isoformat()

        with patch("telemetry.serializers.timezone.now", return_value=now):
            response = self.post(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["recorded_at"],
            ["Timestamp cannot be more than 300 seconds in the future."],
        )
        self.assertFalse(TelemetryEvent.objects.exists())

    def test_missing_recorded_at_remains_required(self):
        payload = deepcopy(self.payload)
        payload.pop("recorded_at")

        response = self.post(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["recorded_at"], ["This field is required."])

    def test_rejects_coordinate_out_of_range(self):
        payload = deepcopy(self.payload)
        payload["latitude"] = 91
        self.assertEqual(self.post(payload).status_code, 400)

    def test_rejects_telemetry_ranges(self):
        for field, value in (
            ("sequence_number", -1),
            ("gnss_speed_kph", 301),
            ("rpm", 12001),
            ("engine_load_pct", 101),
        ):
            with self.subTest(field=field):
                payload = deepcopy(self.payload)
                payload[field] = value
                self.assertEqual(self.post(payload).status_code, 400)

    def test_rejects_unknown_driving_event(self):
        payload = deepcopy(self.payload)
        payload["driving_event"] = "SPEEDING"
        self.assertEqual(self.post(payload).status_code, 400)

    def test_v1_0_rejects_null_driving_event(self):
        payload = deepcopy(self.payload)
        payload["driving_event"] = None
        self.assertEqual(self.post(payload).status_code, 400)
        self.assertFalse(TelemetryEvent.objects.exists())

    def test_v1_0_accepts_existing_driving_event(self):
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(TelemetryEvent.objects.get().driving_event, "NORMAL")

    def test_v1_1_accepts_null_driving_event(self):
        payload = {
            **self.payload,
            "schema_version": "1.1",
            "position_source": "GNSS",
            "position_accuracy_m": None,
            "driving_event": None,
        }
        self.assertEqual(self.post(payload).status_code, 201)
        self.assertIsNone(TelemetryEvent.objects.get().driving_event)

    def test_v1_1_accepts_valid_driving_event(self):
        payload = {
            **self.payload,
            "schema_version": "1.1",
            "position_source": "GNSS",
            "position_accuracy_m": None,
        }
        self.assertEqual(self.post(payload).status_code, 201)
        self.assertEqual(TelemetryEvent.objects.get().driving_event, "NORMAL")

    def test_v1_1_location_only_lbs_with_null_driving_event_is_idempotent(self):
        payload = {
            **self.payload,
            "schema_version": "1.1",
            "position_source": "CELLULAR_LBS",
            "position_accuracy_m": 550,
            "gnss_speed_kph": None,
            "rpm": None,
            "coolant_c": None,
            "engine_load_pct": None,
            "driving_event": None,
        }
        self.assertEqual(self.post(payload).status_code, 201)
        duplicate = self.post(payload)
        self.assertEqual(duplicate.status_code, 200)
        self.assertTrue(duplicate.json()["duplicate"])
        self.assertIsNone(TelemetryEvent.objects.get().driving_event)

        conflict = {**payload, "driving_event": "NORMAL"}
        self.assertEqual(self.post(conflict).status_code, 409)
        self.assertIsNone(TelemetryEvent.objects.get().driving_event)

    def test_ingestion_only_allows_post(self):
        self.assertEqual(self.client.get("/api/v1/telemetry/").status_code, 405)
        self.assertEqual(self.client.put("/api/v1/telemetry/", {}, format="json").status_code, 405)
        self.assertEqual(
            self.client.delete("/api/v1/telemetry/").status_code,
            405,
        )

    def test_database_enforces_event_id_uniqueness(self):
        self.create_event(event_id="same")
        with self.assertRaises(IntegrityError):
            self.create_event(event_id="same")

    def test_latest_status_returns_null_before_first_event(self):
        response = self.client.get("/api/v1/vehicles/LILYGO-001/latest-status/")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["latest"])
        self.assertEqual(
            response.json()["vehicle"],
            {
                "device_id": "LILYGO-001",
                "plate_number": "DEMO-001",
                "display_name": "Sprint 1 Demo Vehicle",
            },
        )
        self.assertEqual(set(response.json()), {"vehicle", "latest"})

    def test_latest_status_returns_404_for_unknown_vehicle(self):
        response = self.client.get("/api/v1/vehicles/UNKNOWN/latest-status/")
        self.assertEqual(response.status_code, 404)

    def test_latest_status_uses_recorded_time_not_arrival_order(self):
        newer = self.create_event(
            event_id="newer",
            sequence_number=1,
            recorded_at=datetime(2026, 7, 29, 2, tzinfo=UTC),
        )
        self.create_event(
            event_id="late-arrival",
            sequence_number=2,
            recorded_at=datetime(2026, 7, 29, 1, tzinfo=UTC),
        )

        response = self.client.get("/api/v1/vehicles/LILYGO-001/latest-status/")

        self.assertEqual(response.json()["latest"]["event_id"], newer.event_id)

    def test_latest_status_breaks_recorded_time_tie_by_sequence(self):
        recorded_at = datetime(2026, 7, 29, 1, tzinfo=UTC)
        self.create_event(event_id="lower", sequence_number=9, recorded_at=recorded_at)
        higher = self.create_event(event_id="higher", sequence_number=10, recorded_at=recorded_at)

        response = self.client.get("/api/v1/vehicles/LILYGO-001/latest-status/")

        self.assertEqual(response.json()["latest"]["event_id"], higher.event_id)

    def create_event(self, **overrides):
        values = {
            "schema_version": "1.0",
            "event_id": "event",
            "sequence_number": 1,
            "vehicle": self.vehicle,
            "recorded_at": datetime.now(UTC) - timedelta(seconds=1),
            "location": Point(121.0196, 14.5186, srid=4326),
            "gnss_speed_kph": Decimal("38.20"),
            "rpm": 1750,
            "coolant_c": Decimal("88.00"),
            "engine_load_pct": Decimal("34.00"),
            "driving_event": "NORMAL",
        }
        values.update(overrides)
        return TelemetryEvent.objects.create(**values)
