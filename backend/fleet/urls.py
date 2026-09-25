from django.urls import path

from .views import (
    DeactivateVehicleView,
    FuelPriceImportView,
    NumberCodingRuleDetailView,
    NumberCodingRuleListView,
    NumberCodingSuspensionDetailView,
    NumberCodingSuspensionListView,
    PartnerFuelPriceSettingsView,
    ReactivateVehicleView,
    VehicleCodingExemptionDetailView,
    VehicleCodingExemptionListView,
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
    VehiclePhotoView,
)

urlpatterns = [
    path(
        "partner-fuel-prices/",
        PartnerFuelPriceSettingsView.as_view(),
        name="partner-fuel-price-settings",
    ),
    path(
        "partner-fuel-prices/import/",
        FuelPriceImportView.as_view(),
        name="partner-fuel-price-import",
    ),
    path("number-coding/rules/", NumberCodingRuleListView.as_view(), name="number-coding-rules"),
    path(
        "number-coding/rules/<int:record_id>/",
        NumberCodingRuleDetailView.as_view(),
        name="number-coding-rule-detail",
    ),
    path(
        "number-coding/suspensions/",
        NumberCodingSuspensionListView.as_view(),
        name="number-coding-suspensions",
    ),
    path(
        "number-coding/suspensions/<int:record_id>/",
        NumberCodingSuspensionDetailView.as_view(),
        name="number-coding-suspension-detail",
    ),
    path(
        "number-coding/exemptions/",
        VehicleCodingExemptionListView.as_view(),
        name="number-coding-exemptions",
    ),
    path(
        "number-coding/exemptions/<int:record_id>/",
        VehicleCodingExemptionDetailView.as_view(),
        name="number-coding-exemption-detail",
    ),
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
    path("<str:device_id>/photo/", VehiclePhotoView.as_view(), name="vehicle-photo"),
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
