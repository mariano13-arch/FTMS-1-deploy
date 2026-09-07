import json
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from django.test import TransactionTestCase
from django.utils import timezone

from fleet.models import Vehicle
from telemetry.models import TelemetryEvent
from telemetry.mqtt import handle_mqtt_message
from telemetry.realtime import broadcast_vehicle_status
from telemetry.services import IngestionStatus, _broadcast_if_latest, ingest_telemetry


class RealtimeIngestionTests(TransactionTestCase):
    def setUp(self):
        self.vehicle = Vehicle.objects.create(
            device_id="LILYGO-001",
            plate_number="DEMO-001",
            display_name="Sprint 1 Demo Vehicle",
        )
        self.payload = {
            "schema_version": "1.0",
            "event_id": "mqtt-event-1",
            "sequence_number": 201,
            "device_id": self.vehicle.device_id,
            "recorded_at": "2026-07-29T10:00:00Z",
            "latitude": 14.5186,
            "longitude": 121.0196,
            "gnss_speed_kph": 38.2,
            "rpm": None,
            "coolant_c": 0,
            "engine_load_pct": 0,
            "driving_event": "NORMAL",
        }

    def message(self, payload=None, raw_payload=None, **overrides):
        values = {
            "topic": "ftms/v1/telemetry/LILYGO-001",
            "payload": (
                raw_payload
                if raw_payload is not None
                else json.dumps(payload or self.payload).encode()
            ),
            "retain": False,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    @patch("telemetry.services.broadcast_vehicle_status")
    def test_new_mqtt_event_persists_postgis_values_and_broadcasts_once(self, broadcast):
        result = handle_mqtt_message(
            self.message(), "ftms/v1/telemetry"
        )

        self.assertEqual(result.status, IngestionStatus.CREATED)
        event = TelemetryEvent.objects.get()
        self.assertEqual(event.location.srid, 4326)
        self.assertAlmostEqual(event.location.x, 121.0196)
        self.assertAlmostEqual(event.location.y, 14.5186)
        self.assertIsNone(event.rpm)
        self.assertEqual(event.coolant_c, 0)
        self.assertEqual(event.engine_load_pct, 0)
        broadcast.assert_called_once_with(event)

    @patch("telemetry.services.broadcast_vehicle_status")
    def test_duplicate_and_conflict_do_not_add_rows_or_broadcast(self, broadcast):
        self.assertEqual(ingest_telemetry(self.payload).status, IngestionStatus.CREATED)
        broadcast.reset_mock()

        duplicate = handle_mqtt_message(self.message(), "ftms/v1/telemetry")
        conflict_payload = deepcopy(self.payload)
        conflict_payload["gnss_speed_kph"] = 99
        conflict = handle_mqtt_message(
            self.message(conflict_payload), "ftms/v1/telemetry"
        )

        self.assertEqual(duplicate.status, IngestionStatus.DUPLICATE)
        self.assertEqual(conflict.status, IngestionStatus.CONFLICT)
        self.assertEqual(TelemetryEvent.objects.count(), 1)
        self.assertEqual(float(TelemetryEvent.objects.get().gnss_speed_kph), 38.2)
        broadcast.assert_not_called()

    @patch("telemetry.services.broadcast_vehicle_status")
    def test_late_event_is_stored_without_broadcast(self, broadcast):
        ingest_telemetry(self.payload)
        broadcast.reset_mock()
        late = deepcopy(self.payload)
        late.update(
            event_id="late-event",
            sequence_number=202,
            recorded_at="2026-07-29T09:00:00Z",
        )

        result = ingest_telemetry(late)

        self.assertEqual(result.status, IngestionStatus.CREATED)
        self.assertEqual(TelemetryEvent.objects.count(), 2)
        broadcast.assert_not_called()

    def test_delivery_failure_does_not_rollback_created_event(self):
        layer = SimpleNamespace(group_send=AsyncMock(side_effect=RuntimeError("redis down")))
        with patch("telemetry.realtime.get_channel_layer", return_value=layer):
            result = ingest_telemetry(self.payload)

        self.assertEqual(result.status, IngestionStatus.CREATED)
        self.assertTrue(TelemetryEvent.objects.filter(event_id="mqtt-event-1").exists())

    def test_post_commit_presentation_failure_does_not_misreport_ingestion(self):
        with patch(
            "telemetry.realtime.vehicle_status_data",
            side_effect=RuntimeError("presentation unavailable"),
        ):
            result = ingest_telemetry(self.payload)

        self.assertEqual(result.status, IngestionStatus.CREATED)
        self.assertTrue(TelemetryEvent.objects.filter(event_id="mqtt-event-1").exists())

    def test_broadcast_drops_event_superseded_during_latest_check(self):
        first = ingest_telemetry(self.payload).event
        layer = SimpleNamespace(group_send=AsyncMock())

        def commit_newer_then_broadcast(checked_event):
            newer = deepcopy(self.payload)
            newer.update(
                event_id="newer-concurrent-event",
                sequence_number=202,
                recorded_at="2026-07-29T11:00:00Z",
            )
            TelemetryEvent.objects.create(**self.serializer_values(newer))
            broadcast_vehicle_status(checked_event)

        with (
            patch("telemetry.services.broadcast_vehicle_status") as broadcast,
            patch("telemetry.realtime.get_channel_layer", return_value=layer),
        ):
            broadcast.side_effect = commit_newer_then_broadcast
            _broadcast_if_latest(first.event_id)

        broadcast.assert_called_once()
        layer.group_send.assert_not_awaited()

    @patch("telemetry.services.broadcast_vehicle_status")
    def test_realtime_latest_selection_ignores_preserved_future_event(self, broadcast):
        current = ingest_telemetry(self.payload).event
        broadcast.reset_mock()
        future_values = self.serializer_values(self.payload)
        future_values.update(
            event_id="preserved-future-event",
            sequence_number=999,
            recorded_at=timezone.now() + timedelta(days=3650),
        )
        future = TelemetryEvent.objects.create(**future_values)

        _broadcast_if_latest(current.event_id)
        _broadcast_if_latest(future.event_id)

        broadcast.assert_called_once_with(current)
        self.assertTrue(TelemetryEvent.objects.filter(pk=future.pk).exists())

    def serializer_values(self, payload):
        from telemetry.serializers import TelemetryEventInputSerializer

        serializer = TelemetryEventInputSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        return serializer.create_model_values()

    def test_invalid_mqtt_messages_are_rejected_without_rows(self):
        invalid_payloads = [
            b"\xff",
            b"{",
            b"[]",
            json.dumps({**self.payload, "schema_version": "2.0"}).encode(),
            json.dumps({**self.payload, "extra": "no"}).encode(),
            json.dumps({**self.payload, "latitude": 91}).encode(),
            json.dumps({**self.payload, "gnss_speed_kph": float("nan")}).encode(),
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload[:20]):
                self.assertIsNone(
                    handle_mqtt_message(
                        self.message(raw_payload=payload),
                        "ftms/v1/telemetry",
                    )
                )
        self.assertIsNone(
            handle_mqtt_message(
                self.message(topic="ftms/v1/telemetry/OTHER"),
                "ftms/v1/telemetry",
            )
        )
        self.assertIsNone(
            handle_mqtt_message(self.message(retain=True), "ftms/v1/telemetry")
        )
        self.assertIsNone(
            handle_mqtt_message(
                self.message(raw_payload=b"x" * 65_537), "ftms/v1/telemetry"
            )
        )
        self.assertEqual(TelemetryEvent.objects.count(), 0)

    def test_safe_mqtt_logs_exclude_sensitive_payload_values(self):
        secret_payload = {
            **self.payload,
            "event_id": "safe-event",
            "latitude": 14.123456,
            "longitude": 121.654321,
            "extra": "postgres://user:password@database/ftms",
        }
        with self.assertLogs("telemetry.mqtt", level="WARNING") as logs:
            handle_mqtt_message(self.message(secret_payload), "ftms/v1/telemetry")

        rendered = " ".join(logs.output)
        for forbidden in (
            "14.123456",
            "121.654321",
            "password",
            "postgres://",
            '"extra"',
        ):
            self.assertNotIn(forbidden, rendered)

    def test_rest_and_mqtt_adapters_call_the_same_service(self):
        from rest_framework.test import APIClient

        service_result = SimpleNamespace(
            status=IngestionStatus.CONFLICT,
            event=SimpleNamespace(),
        )
        with patch("telemetry.views.ingest_telemetry", return_value=service_result) as rest:
            response = APIClient().post("/api/v1/telemetry/", self.payload, format="json")
        self.assertEqual(response.status_code, 409)
        rest.assert_called_once_with(self.payload)

        with patch("telemetry.mqtt.ingest_telemetry", return_value=service_result) as mqtt:
            handle_mqtt_message(self.message(), "ftms/v1/telemetry")
        mqtt.assert_called_once_with(self.payload)
