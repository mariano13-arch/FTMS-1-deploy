from django.urls import path

from .views import (
    CsrfView,
    DriverLoginView,
    DriverLogoutView,
    DriverMeView,
    DriverPasswordSetupView,
)

urlpatterns = [
    path("csrf/", CsrfView.as_view(), name="driver-auth-csrf"),
    path("login/", DriverLoginView.as_view(), name="driver-auth-login"),
    path("me/", DriverMeView.as_view(), name="driver-auth-me"),
    path("logout/", DriverLogoutView.as_view(), name="driver-auth-logout"),
    path(
        "setup-password/",
        DriverPasswordSetupView.as_view(),
        name="driver-auth-setup-password",
    ),
]
