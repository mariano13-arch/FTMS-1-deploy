from django.urls import path

from .maintenance_views import ModelInfoView, PredictView, ReadinessView

urlpatterns = [
    path("model-info/", ModelInfoView.as_view()),
    path("readiness/", ReadinessView.as_view()),
    path("predict/", PredictView.as_view()),
]
