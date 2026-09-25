from django.urls import path

from .reports import (
    DeviceTelemetryCsvView,
    DeviceTelemetryReportView,
    DispatchTripReportCsvView,
    DispatchTripReportView,
    DriverSafetyCalibrationReportView,
    FleetAssignmentCsvView,
    FleetAssignmentReportView,
    FuelReferenceCsvView,
    FuelReferenceReportView,
    InspectionMaintenanceCsvView,
    InspectionMaintenanceReportView,
    SafetyGeofenceCsvView,
    SafetyGeofenceReportView,
    TransportRequestReportCsvView,
    TransportRequestReportPdfView,
    TransportRequestReportView,
    TransportRequestReportXlsxView,
)

urlpatterns = [
    path("fuel-reference/", FuelReferenceReportView.as_view(), name="report-fuel-reference"),
    path(
        "fuel-reference/<str:kind>/csv/",
        FuelReferenceCsvView.as_view(),
        name="report-fuel-reference-csv",
    ),
    path(
        "driver-safety-calibration/",
        DriverSafetyCalibrationReportView.as_view(),
        name="report-driver-safety-calibration",
    ),
    path(
        "device-telemetry/",
        DeviceTelemetryReportView.as_view(),
        name="report-device-telemetry",
    ),
    path(
        "device-telemetry/<str:kind>/csv/",
        DeviceTelemetryCsvView.as_view(),
        name="report-device-telemetry-csv",
    ),
    path("safety-geofence/", SafetyGeofenceReportView.as_view(), name="report-safety-geofence"),
    path(
        "safety-geofence/<str:kind>/csv/",
        SafetyGeofenceCsvView.as_view(),
        name="report-safety-geofence-csv",
    ),
    path(
        "fleet-assignments/", FleetAssignmentReportView.as_view(), name="report-fleet-assignments"
    ),
    path(
        "fleet-assignments/<str:kind>/csv/",
        FleetAssignmentCsvView.as_view(),
        name="report-fleet-assignments-csv",
    ),
    path(
        "inspection-maintenance/",
        InspectionMaintenanceReportView.as_view(),
        name="report-inspection-maintenance",
    ),
    path(
        "inspection-maintenance/<str:kind>/csv/",
        InspectionMaintenanceCsvView.as_view(),
        name="report-inspection-maintenance-csv",
    ),
    path("dispatch-trips/", DispatchTripReportView.as_view(), name="report-dispatch-trips"),
    path(
        "dispatch-trips/csv/", DispatchTripReportCsvView.as_view(), name="report-dispatch-trips-csv"
    ),
    path(
        "transport-requests/",
        TransportRequestReportView.as_view(),
        name="report-transport-requests",
    ),
    path(
        "transport-requests/csv/",
        TransportRequestReportCsvView.as_view(),
        name="report-transport-requests-csv",
    ),
    path(
        "transport-requests/xlsx/",
        TransportRequestReportXlsxView.as_view(),
        name="report-transport-requests-xlsx",
    ),
    path(
        "transport-requests/pdf/",
        TransportRequestReportPdfView.as_view(),
        name="report-transport-requests-pdf",
    ),
]
