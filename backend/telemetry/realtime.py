import hashlib
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from telemetry.presentation import vehicle_status_data

logger = logging.getLogger(__name__)


def vehicle_status_group(device_id):
    digest = hashlib.sha256(device_id.encode()).hexdigest()
    return f"vehicle-status-{digest}"


def broadcast_vehicle_status(event):
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        vehicle = event.vehicle
        message = {
            "type": "vehicle.status.updated",
            "data": vehicle_status_data(vehicle, event),
        }
        async_to_sync(channel_layer.group_send)(
            vehicle_status_group(vehicle.device_id),
            {
                "type": "vehicle.status",
                "message": message,
            },
        )
    except Exception:
        logger.exception(
            "Real-time delivery failed for event_id=%s; REST fallback remains available",
            event.event_id,
        )
