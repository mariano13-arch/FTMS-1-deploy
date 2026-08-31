from django.urls import include, path

urlpatterns = [
    path("api/", include("health.urls")),
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/driver-auth/", include("accounts.driver_urls")),
    path("api/v1/driver-trips/", include("transport_requests.driver_urls")),
    path("api/v1/vehicles/", include("fleet.urls")),
    path("api/v1/drivers/", include("fleet.driver_urls")),
    path("api/v1/transport-requests/", include("transport_requests.urls")),
    path("api/v1/analytics/fuel/", include("ml.urls")),
    path("api/v1/analytics/maintenance/", include("ml.maintenance_urls")),
    path("api/v1/", include("telemetry.urls")),
]
