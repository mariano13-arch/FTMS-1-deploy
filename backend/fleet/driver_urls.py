from django.urls import path

from .views import (
    DriverDetailView,
    DriverDocumentDetailView,
    DriverDocumentFileView,
    DriverDocumentListView,
    DriverListView,
    DriverPhotoView,
)

urlpatterns = [
    path("", DriverListView.as_view(), name="driver-list"),
    path("<int:driver_id>/", DriverDetailView.as_view(), name="driver-detail"),
    path("<int:driver_id>/photo/", DriverPhotoView.as_view(), name="driver-photo"),
    path(
        "<int:driver_id>/documents/",
        DriverDocumentListView.as_view(),
        name="driver-document-list",
    ),
    path(
        "<int:driver_id>/documents/<int:document_id>/",
        DriverDocumentDetailView.as_view(),
        name="driver-document-detail",
    ),
    path(
        "<int:driver_id>/documents/<int:document_id>/file/",
        DriverDocumentFileView.as_view(),
        name="driver-document-file",
    ),
]
