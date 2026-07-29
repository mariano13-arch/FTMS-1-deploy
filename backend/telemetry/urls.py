from django.urls import path

from telemetry.views import LatestVehicleStatusView, TelemetryEventCreateView

urlpatterns = [
    path("telemetry/", TelemetryEventCreateView.as_view(), name="telemetry-create"),
    path(
        "vehicles/<str:device_id>/latest-status/",
        LatestVehicleStatusView.as_view(),
        name="vehicle-latest-status",
    ),
]
