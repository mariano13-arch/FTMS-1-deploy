from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.test import TransactionTestCase, override_settings

from accounts.models import StaffProfile
from fleet.models import Vehicle
from telemetry.consumers import VehicleStatusConsumer
from telemetry.models import TelemetryEvent
from telemetry.presentation import latest_status_data, vehicle_status_data
from telemetry.realtime import vehicle_status_group
from telemetry.routing import websocket_urlpatterns

CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
class VehicleStatusWebSocketTests(TransactionTestCase):
    async def communicator(self, path):
        communicator = WebsocketCommunicator(URLRouter(websocket_urlpatterns), path)
        communicator.scope["user"] = await self.create_user()
        return communicator

    async def test_anonymous_closes_with_4401(self):
        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns), "/ws/v1/vehicles/LILYGO-001/status/"
        )
        connected, close_code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)

    async def test_authenticated_profileless_user_closes_with_4403_before_lookup(self):
        user = await self.create_profileless_user()
        for device_id in ("LILYGO-001", "UNKNOWN"):
            communicator = WebsocketCommunicator(
                URLRouter(websocket_urlpatterns),
                f"/ws/v1/vehicles/{device_id}/status/",
            )
            communicator.scope["user"] = user
            connected, close_code = await communicator.connect()
            self.assertFalse(connected)
            self.assertEqual(close_code, 4403)

    async def test_known_vehicle_receives_null_snapshot(self):
        await self.create_vehicle()
        communicator = await self.communicator("/ws/v1/vehicles/LILYGO-001/status/")

        connected, _ = await communicator.connect()
        message = await communicator.receive_json_from()

        self.assertTrue(connected)
        self.assertEqual(message["type"], "vehicle.status.snapshot")
        self.assertIsNone(message["data"]["latest"])
        self.assertEqual(message["data"]["vehicle"]["device_id"], "LILYGO-001")
        await communicator.disconnect()

    async def test_connected_vehicle_receives_rest_shaped_update(self):
        vehicle = await self.create_vehicle()
        event = await self.create_event(vehicle)
        expected = await database_sync_to_async(latest_status_data)(vehicle)
        communicator = await self.communicator("/ws/v1/vehicles/LILYGO-001/status/")
        connected, _ = await communicator.connect()
        await communicator.receive_json_from()

        message = {"type": "vehicle.status.updated", "data": expected}
        await get_channel_layer().group_send(
            vehicle_status_group(vehicle.device_id),
            {"type": "vehicle.status", "message": message},
        )
        received = await communicator.receive_json_from()

        self.assertTrue(connected)
        self.assertEqual(received, message)
        self.assertEqual(received["data"]["latest"]["event_id"], event.event_id)
        await communicator.disconnect()

    async def test_unknown_vehicle_closes_with_4404(self):
        communicator = await self.communicator("/ws/v1/vehicles/UNKNOWN/status/")

        connected, close_code = await communicator.connect()

        self.assertFalse(connected)
        self.assertEqual(close_code, 4404)
        self.assertNotIn(vehicle_status_group("UNKNOWN"), get_channel_layer().groups)

    async def test_update_during_snapshot_window_is_queued_after_snapshot(self):
        vehicle = await self.create_vehicle()
        original = await self.create_event(vehicle)

        async def snapshot_with_concurrent_update(consumer, device_id):
            snapshot = await database_sync_to_async(latest_status_data)(vehicle)
            newer = await self.create_event(
                vehicle,
                event_id="connection-window-event",
                sequence_number=2,
                recorded_at=datetime(2026, 7, 29, 11, tzinfo=UTC),
            )
            update = {
                "type": "vehicle.status.updated",
                "data": await database_sync_to_async(vehicle_status_data)(
                    vehicle, newer
                ),
            }
            await get_channel_layer().group_send(
                vehicle_status_group(device_id),
                {"type": "vehicle.status", "message": update},
            )
            return snapshot

        communicator = await self.communicator("/ws/v1/vehicles/LILYGO-001/status/")
        with patch.object(
            VehicleStatusConsumer, "_snapshot", new=snapshot_with_concurrent_update
        ):
            connected, _ = await communicator.connect()
            snapshot = await communicator.receive_json_from()
            update = await communicator.receive_json_from()

        self.assertTrue(connected)
        self.assertEqual(snapshot["type"], "vehicle.status.snapshot")
        self.assertEqual(snapshot["data"]["latest"]["event_id"], original.event_id)
        self.assertEqual(update["type"], "vehicle.status.updated")
        self.assertEqual(
            update["data"]["latest"]["event_id"], "connection-window-event"
        )
        await communicator.disconnect()

    @database_sync_to_async
    def create_vehicle(self):
        return Vehicle.objects.create(
            device_id="LILYGO-001",
            plate_number="DEMO-001",
            display_name="Sprint 1 Demo Vehicle",
        )

    @database_sync_to_async
    def create_user(self):
        user = get_user_model().objects.create_user(
            username=f"dispatcher-{get_user_model().objects.count()}",
            password="Strong-test-password-42!", is_staff=True,
        )
        StaffProfile.objects.create(user=user, role=StaffProfile.Role.DISPATCHER)
        return user

    @database_sync_to_async
    def create_profileless_user(self):
        return get_user_model().objects.create_user(
            username="profileless", password="Strong-test-password-42!", is_staff=True
        )

    @database_sync_to_async
    def create_event(self, vehicle, **overrides):
        values = {
            "schema_version": "1.0",
            "event_id": "websocket-event",
            "sequence_number": 1,
            "vehicle": vehicle,
            "recorded_at": datetime(2026, 7, 29, 10, tzinfo=UTC),
            "location": Point(121.0196, 14.5186, srid=4326),
            "gnss_speed_kph": Decimal("38.20"),
            "rpm": None,
            "coolant_c": Decimal("88.00"),
            "engine_load_pct": Decimal("34.00"),
            "driving_event": "NORMAL",
        }
        values.update(overrides)
        return TelemetryEvent.objects.create(**values)
