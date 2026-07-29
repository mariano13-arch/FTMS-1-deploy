from django.urls import path

from .views import (
    DeactivateVehicleView,
    ReactivateVehicleView,
    VehicleDetailView,
    VehicleListView,
)

urlpatterns = [
    path("", VehicleListView.as_view(), name="vehicle-list"),
    path("<str:device_id>/", VehicleDetailView.as_view(), name="vehicle-detail"),
    path("<str:device_id>/deactivate/", DeactivateVehicleView.as_view(), name="vehicle-deactivate"),
    path("<str:device_id>/reactivate/", ReactivateVehicleView.as_view(), name="vehicle-reactivate"),
]
