from django.urls import path

from .views import (
    DeactivateVehicleView,
    ReactivateVehicleView,
    VehicleDetailView,
    VehicleDocumentDetailView,
    VehicleDocumentFileView,
    VehicleDocumentListView,
    VehicleInspectionDefinitionView,
    VehicleInspectionDetailView,
    VehicleInspectionListView,
    VehicleListView,
    VehicleMaintenanceDetailView,
    VehicleMaintenanceListView,
    VehicleMaintenanceTransitionView,
)

urlpatterns = [
    path("maintenance/", VehicleMaintenanceListView.as_view(), name="vehicle-maintenance-list"),
    path(
        "maintenance/<int:record_id>/",
        VehicleMaintenanceDetailView.as_view(),
        name="vehicle-maintenance-detail",
    ),
    path(
        "maintenance/<int:record_id>/transition/",
        VehicleMaintenanceTransitionView.as_view(),
        name="vehicle-maintenance-transition",
    ),
    path(
        "inspection-definition/",
        VehicleInspectionDefinitionView.as_view(),
        name="vehicle-inspection-definition",
    ),
    path("", VehicleListView.as_view(), name="vehicle-list"),
    path("<str:device_id>/", VehicleDetailView.as_view(), name="vehicle-detail"),
    path("<str:device_id>/deactivate/", DeactivateVehicleView.as_view(), name="vehicle-deactivate"),
    path("<str:device_id>/reactivate/", ReactivateVehicleView.as_view(), name="vehicle-reactivate"),
    path(
        "<str:device_id>/inspections/",
        VehicleInspectionListView.as_view(),
        name="vehicle-inspection-list",
    ),
    path(
        "<str:device_id>/inspections/<int:inspection_id>/",
        VehicleInspectionDetailView.as_view(),
        name="vehicle-inspection-detail",
    ),
    path(
        "<str:device_id>/documents/",
        VehicleDocumentListView.as_view(),
        name="vehicle-document-list",
    ),
    path(
        "<str:device_id>/documents/<int:document_id>/",
        VehicleDocumentDetailView.as_view(),
        name="vehicle-document-detail",
    ),
    path(
        "<str:device_id>/documents/<int:document_id>/file/",
        VehicleDocumentFileView.as_view(),
        name="vehicle-document-file",
    ),
]
