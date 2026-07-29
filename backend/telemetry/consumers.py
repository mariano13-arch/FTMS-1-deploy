from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from fleet.models import Vehicle
from telemetry.presentation import latest_status_data
from telemetry.realtime import vehicle_status_group


class VehicleStatusConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        device_id = self.scope["url_route"]["kwargs"]["device_id"]
        self.group_name = vehicle_status_group(device_id)
        self.group_joined = False
        try:
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            self.group_joined = True
            snapshot = await self._snapshot(device_id)
            if snapshot is None:
                await self.channel_layer.group_discard(
                    self.group_name, self.channel_name
                )
                self.group_joined = False
                await self.close(code=4404)
                return

            await self.accept()
            await self.send_json({"type": "vehicle.status.snapshot", "data": snapshot})
        except Exception:
            if self.group_joined:
                await self.channel_layer.group_discard(
                    self.group_name, self.channel_name
                )
                self.group_joined = False
            raise

    async def disconnect(self, close_code):
        if getattr(self, "group_joined", False):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            self.group_joined = False

    async def vehicle_status(self, event):
        await self.send_json(event["message"])

    @database_sync_to_async
    def _snapshot(self, device_id):
        try:
            vehicle = Vehicle.objects.get(device_id=device_id)
        except Vehicle.DoesNotExist:
            return None
        return latest_status_data(vehicle)
