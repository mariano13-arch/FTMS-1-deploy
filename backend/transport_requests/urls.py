from django.urls import path

from .views import (
    ApproveView,
    AssignVehicleView,
    CalendarView,
    CancelView,
    ConsolidationConfirmationView,
    ConsolidationPrepareView,
    ConsolidationRecommendationView,
    DispatchBoardView,
    DispatchConfirmationView,
    DispatchMatrixView,
    DispatchRecommendationView,
    PlaceDetailsView,
    PlaceSuggestView,
    PrepareDispatchView,
    RejectView,
    RequestMoreDetailsView,
    ResubmitView,
    SummaryView,
    TransportRequestDetailView,
    TransportRequestListView,
    TransportRequestRouteView,
)

urlpatterns = [
    path("dispatch-board/", DispatchBoardView.as_view(), name="dispatch-board"),
    path(
        "dispatch-board/recommendations/",
        DispatchRecommendationView.as_view(),
        name="dispatch-recommendations",
    ),
    path(
        "dispatch-board/confirm/",
        DispatchConfirmationView.as_view(),
        name="dispatch-confirmation",
    ),
    path(
        "dispatch-board/consolidation-recommendations/",
        ConsolidationRecommendationView.as_view(),
        name="dispatch-consolidation-recommendations",
    ),
    path(
        "dispatch-board/consolidations/confirm/",
        ConsolidationConfirmationView.as_view(),
        name="dispatch-consolidation-confirm",
    ),
    path(
        "dispatch-board/consolidations/<int:plan_id>/prepare/",
        ConsolidationPrepareView.as_view(),
        name="dispatch-consolidation-prepare",
    ),
    path("", TransportRequestListView.as_view(), name="transport-request-list"),
    path("summary/", SummaryView.as_view(), name="transport-request-summary"),
    path("calendar/", CalendarView.as_view(), name="transport-request-calendar"),
    path(
        "dispatch-matrix/", DispatchMatrixView.as_view(), name="transport-request-dispatch-matrix"
    ),
    path("places/suggest/", PlaceSuggestView.as_view(), name="transport-request-place-suggest"),
    path(
        "places/details/<str:place_type>/<path:place_id>/",
        PlaceDetailsView.as_view(),
        name="transport-request-place-details",
    ),
    path(
        "<uuid:request_id>/",
        TransportRequestDetailView.as_view(),
        name="transport-request-detail",
    ),
    path(
        "<uuid:request_id>/route/",
        TransportRequestRouteView.as_view(),
        name="transport-request-route",
    ),
    path("<uuid:request_id>/approve/", ApproveView.as_view()),
    path("<uuid:request_id>/reject/", RejectView.as_view()),
    path("<uuid:request_id>/request-more-details/", RequestMoreDetailsView.as_view()),
    path("<uuid:request_id>/resubmit/", ResubmitView.as_view()),
    path("<uuid:request_id>/assign-vehicle/", AssignVehicleView.as_view()),
    path("<uuid:request_id>/prepare-dispatch/", PrepareDispatchView.as_view()),
    path("<uuid:request_id>/cancel/", CancelView.as_view()),
]
