from django.urls import path

from .views import (
    ApproveView,
    AssignVehicleView,
    CalendarView,
    CancelView,
    PrepareDispatchView,
    RejectView,
    RequestMoreDetailsView,
    ResubmitView,
    SummaryView,
    TransportRequestDetailView,
    TransportRequestListView,
)

urlpatterns = [
    path("", TransportRequestListView.as_view(), name="transport-request-list"),
    path("summary/", SummaryView.as_view(), name="transport-request-summary"),
    path("calendar/", CalendarView.as_view(), name="transport-request-calendar"),
    path(
        "<uuid:request_id>/", TransportRequestDetailView.as_view(),
        name="transport-request-detail",
    ),
    path("<uuid:request_id>/approve/", ApproveView.as_view()),
    path("<uuid:request_id>/reject/", RejectView.as_view()),
    path("<uuid:request_id>/request-more-details/", RequestMoreDetailsView.as_view()),
    path("<uuid:request_id>/resubmit/", ResubmitView.as_view()),
    path("<uuid:request_id>/assign-vehicle/", AssignVehicleView.as_view()),
    path("<uuid:request_id>/prepare-dispatch/", PrepareDispatchView.as_view()),
    path("<uuid:request_id>/cancel/", CancelView.as_view()),
]
