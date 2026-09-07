from django.urls import path

from .integration_views import (
    SourceTransportRequestCreateView,
    SourceTransportRequestResultView,
)

urlpatterns = [
    path(
        "transport-requests/",
        SourceTransportRequestCreateView.as_view(),
        name="source-transport-request-create",
    ),
    path(
        "transport-requests/<path:external_reference>/",
        SourceTransportRequestResultView.as_view(),
        name="source-transport-request-result",
    ),
]
