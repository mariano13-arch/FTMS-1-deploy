from django.urls import path

from .views import (
    CsrfView,
    LoginView,
    LogoutView,
    ManagedStaffInvitationView,
    ManagedStaffListCreateView,
    ManagedStaffRoleView,
    ManagedStaffStatusView,
    MeView,
    RolePermissionListView,
    RolePermissionReplaceView,
    StaffPasswordSetupView,
)

urlpatterns = [
    path("csrf/", CsrfView.as_view(), name="auth-csrf"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path(
        "role-permissions/",
        RolePermissionListView.as_view(),
        name="role-permission-list",
    ),
    path(
        "role-permissions/<str:role>/",
        RolePermissionReplaceView.as_view(),
        name="role-permission-replace",
    ),
    path("staff/", ManagedStaffListCreateView.as_view(), name="managed-staff-list"),
    path(
        "staff/<int:user_id>/role/",
        ManagedStaffRoleView.as_view(),
        name="managed-staff-role",
    ),
    path(
        "staff/<int:user_id>/status/",
        ManagedStaffStatusView.as_view(),
        name="managed-staff-status",
    ),
    path(
        "staff/<int:user_id>/resend-invitation/",
        ManagedStaffInvitationView.as_view(),
        name="managed-staff-resend-invitation",
    ),
    path(
        "staff/setup-password/",
        StaffPasswordSetupView.as_view(),
        name="staff-setup-password",
    ),
]
