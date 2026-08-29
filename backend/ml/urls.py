from django.urls import path

from ml.views import (
    FuelDashboardView,
    FuelModelInfoView,
    FuelPredictionView,
    FuelReadinessView,
)

urlpatterns = [
    path("predict/", FuelPredictionView.as_view(), name="fuel-predict"),
    path("model-info/", FuelModelInfoView.as_view(), name="fuel-model-info"),
    path("readiness/", FuelReadinessView.as_view(), name="fuel-readiness"),
    path("dashboard/", FuelDashboardView.as_view(), name="fuel-dashboard"),
]
