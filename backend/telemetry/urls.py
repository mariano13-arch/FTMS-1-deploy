from django.urls import path

from telemetry.views import (
    FleetLiveSafetyEventListView,
    FleetLiveVehicleListView,
    FleetLiveVehicleTrailView,
    GeofenceDetailView,
    GeofenceListCreateView,
    LatestVehicleStatusView,
    TelemetryEventCreateView,
)

urlpatterns = [
    path("telemetry/", TelemetryEventCreateView.as_view(), name="telemetry-create"),
    path("fleet-live/vehicles/", FleetLiveVehicleListView.as_view(), name="fleet-live-vehicles"),
    path(
        "fleet-live/vehicles/<int:vehicle_id>/trail/",
        FleetLiveVehicleTrailView.as_view(),
        name="fleet-live-vehicle-trail",
    ),
    path(
        "fleet-live/safety-events/",
        FleetLiveSafetyEventListView.as_view(),
        name="fleet-live-safety-events",
    ),
    path(
        "fleet-live/geofences/",
        GeofenceListCreateView.as_view(),
        name="fleet-live-geofences",
    ),
    path(
        "fleet-live/geofences/<uuid:geofence_id>/",
        GeofenceDetailView.as_view(),
        name="fleet-live-geofence-detail",
    ),
    path(
        "vehicles/<str:device_id>/latest-status/",
        LatestVehicleStatusView.as_view(),
        name="vehicle-latest-status",
    ),
]
