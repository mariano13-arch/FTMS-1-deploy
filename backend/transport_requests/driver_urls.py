from django.urls import path

from .driver_views import (
    DriverTripAcceptView,
    DriverTripDetailView,
    DriverTripListView,
    DriverTripReceiptListCreateView,
    DriverTripReceiptOcrPreviewView,
    DriverTripRouteView,
    DriverTripTransitionView,
    DriverTripVehiclePositionView,
)

urlpatterns = [
    path("", DriverTripListView.as_view(), name="driver-trip-list"),
    path("<uuid:trip_id>/", DriverTripDetailView.as_view(), name="driver-trip-detail"),
    path("<uuid:trip_id>/accept/", DriverTripAcceptView.as_view(), name="driver-trip-accept"),
    path(
        "<uuid:trip_id>/receipts/",
        DriverTripReceiptListCreateView.as_view(),
        name="driver-trip-receipt-list",
    ),
    path(
        "<uuid:trip_id>/receipts/ocr-preview/",
        DriverTripReceiptOcrPreviewView.as_view(),
        name="driver-trip-receipt-ocr-preview",
    ),
    path("<uuid:trip_id>/route/", DriverTripRouteView.as_view(), name="driver-trip-route"),
    path(
        "<uuid:trip_id>/vehicle-position/",
        DriverTripVehiclePositionView.as_view(),
        name="driver-trip-vehicle-position",
    ),
    path(
        "<uuid:trip_id>/transition/",
        DriverTripTransitionView.as_view(),
        name="driver-trip-transition",
    ),
]
