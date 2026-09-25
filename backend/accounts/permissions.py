from rest_framework.permissions import BasePermission

from fleet.models import Driver

from .roles import (
    can_change_status,
    can_create,
    can_edit,
    can_view,
    has_module_permission,
    is_driver_identity,
)


class StaffAccess(BasePermission):
    def has_permission(self, request, view):
        return can_view(request.user)


class DriverAccess(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not is_driver_identity(user):
            return False
        try:
            request.driver = user.driver_record
        except Driver.DoesNotExist:
            return False
        return True


class ModuleActionAccess(BasePermission):
    """Deny-by-default authority for a view's declared FTMS capability."""

    module = None
    action = None

    def has_permission(self, request, view):
        if request.method.lower() not in getattr(view, "http_method_names", []):
            return True
        module = getattr(view, "permission_module", self.module)
        action = getattr(view, "permission_action", self.action)
        action = getattr(view, "permission_actions", {}).get(request.method, action)
        return bool(module and action) and has_module_permission(
            request.user, module, action
        )


def module_action_access(module, action):
    class ConfiguredModuleActionAccess(ModuleActionAccess):
        pass

    ConfiguredModuleActionAccess.module = module
    ConfiguredModuleActionAccess.action = action
    ConfiguredModuleActionAccess.__name__ = f"{module.title()}{action.title()}Access"
    return ConfiguredModuleActionAccess


class CanCreateVehicle(BasePermission):
    def has_permission(self, request, view):
        return can_create(request.user)


class CanEditVehicle(BasePermission):
    def has_permission(self, request, view):
        return can_edit(request.user)


class CanChangeVehicleStatus(BasePermission):
    def has_permission(self, request, view):
        return can_change_status(request.user)
