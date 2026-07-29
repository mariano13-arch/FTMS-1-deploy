from django.urls import include, path

urlpatterns = [
    path("api/", include("health.urls")),
    path("api/v1/", include("telemetry.urls")),
]
