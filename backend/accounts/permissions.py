from rest_framework.permissions import BasePermission

from .roles import can_change_status, can_create, can_edit, can_view


class StaffAccess(BasePermission):
    def has_permission(self, request, view):
        return can_view(request.user)


class CanCreateVehicle(BasePermission):
    def has_permission(self, request, view):
        return can_create(request.user)


class CanEditVehicle(BasePermission):
    def has_permission(self, request, view):
        return can_edit(request.user)


class CanChangeVehicleStatus(BasePermission):
    def has_permission(self, request, view):
        return can_change_status(request.user)
