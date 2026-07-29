from django.urls import path

from telemetry.consumers import VehicleStatusConsumer

websocket_urlpatterns = [
    path(
        "ws/v1/vehicles/<str:device_id>/status/",
        VehicleStatusConsumer.as_asgi(),
    ),
]
