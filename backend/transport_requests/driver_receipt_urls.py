from django.urls import path

from .driver_views import DriverReceiptDetailView, DriverReceiptImageView

urlpatterns = [
    path("<int:receipt_id>/", DriverReceiptDetailView.as_view(), name="driver-receipt-detail"),
    path(
        "<int:receipt_id>/image/",
        DriverReceiptImageView.as_view(),
        name="driver-receipt-image",
    ),
]
