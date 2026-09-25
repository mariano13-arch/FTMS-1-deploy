from django.urls import path

from telemetry.views import (
    ActiveAttentionListView,
    FleetLiveSafetyEventListView,
    FleetLiveAssignmentRouteView,
    FleetLiveVehicleListView,
    FleetLiveVehicleTrailView,
    GeofenceDetailView,
    GeofenceEventListView,
    GeofenceListCreateView,
    LatestVehicleStatusView,
    TelemetryDeviceCreateView,
    TelemetryDeviceDetailView,
    TelemetryDevicePairView,
    TelemetryDeviceUnpairView,
    TelemetryEventCreateView,
    VehicleEmergencySOSView,
)

urlpatterns = [
    path("alerts/active-attention/", ActiveAttentionListView.as_view(), name="active-attention"),
    path("telemetry/", TelemetryEventCreateView.as_view(), name="telemetry-create"),
    path("sos/", VehicleEmergencySOSView.as_view(), name="vehicle-emergency-sos"),
    path(
        "telemetry-devices/",
        TelemetryDeviceCreateView.as_view(),
        name="telemetry-device-create",
    ),
    path(
        "telemetry-devices/<str:device_id>/",
        TelemetryDeviceDetailView.as_view(),
        name="telemetry-device-detail",
    ),
    path(
        "telemetry-devices/<str:device_id>/pair/",
        TelemetryDevicePairView.as_view(),
        name="telemetry-device-pair",
    ),
    path(
        "telemetry-devices/<str:device_id>/unpair/",
        TelemetryDeviceUnpairView.as_view(),
        name="telemetry-device-unpair",
    ),
    path("fleet-live/vehicles/", FleetLiveVehicleListView.as_view(), name="fleet-live-vehicles"),
    path(
        "fleet-live/assignments/<int:assignment_id>/route/",
        FleetLiveAssignmentRouteView.as_view(),
        name="fleet-live-assignment-route",
    ),
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
        "fleet-live/geofence-events/",
        GeofenceEventListView.as_view(),
        name="fleet-live-geofence-events",
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
