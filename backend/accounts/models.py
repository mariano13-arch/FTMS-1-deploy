from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class StaffProfile(models.Model):
    class Role(models.TextChoices):
        FLEET_MANAGER = "FLEET_MANAGER", "Fleet Manager"
        DISPATCHER = "DISPATCHER", "Dispatcher"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_profile"
    )
    role = models.CharField(max_length=20, choices=Role.choices)

    def __str__(self):
        return f"{self.user.username}: {self.role}"


class PermissionModule(models.TextChoices):
    TRANSPORT_REQUESTS = "TRANSPORT_REQUESTS", "Transport Requests"
    DISPATCH_BOARD = "DISPATCH_BOARD", "Dispatch Board"
    LIVE_MAP = "LIVE_MAP", "Live Map"
    DRIVERS = "DRIVERS", "Drivers"
    VEHICLES = "VEHICLES", "Vehicles"
    FUEL_ANALYTICS = "FUEL_ANALYTICS", "Fuel Analytics"
    MAINTENANCE = "MAINTENANCE", "Maintenance"
    SYSTEM_SETTINGS = "SYSTEM_SETTINGS", "System Settings"
    USERS_ACCESS = "USERS_ACCESS", "Users & Access"


class PermissionAction(models.TextChoices):
    VIEW = "VIEW", "View"
    EDIT = "EDIT", "Edit"
    APPROVE = "APPROVE", "Approve"
    CANCEL = "CANCEL", "Cancel"
    ASSIGN = "ASSIGN", "Assign"
    DISPATCH = "DISPATCH", "Dispatch"
    OVERRIDE = "OVERRIDE", "Override"
    MANAGE_GEOFENCES = "MANAGE_GEOFENCES", "Manage Geofences"
    CREATE = "CREATE", "Create"
    MANAGE_DOCUMENTS = "MANAGE_DOCUMENTS", "Manage Documents"
    CHANGE_STATUS = "CHANGE_STATUS", "Change Status"
    INSPECT = "INSPECT", "Inspect"
    VIEW_USERS = "VIEW_USERS", "View Users"
    CREATE_USER = "CREATE_USER", "Create User"
    EDIT_USER = "EDIT_USER", "Edit User"
    CHANGE_USER_STATUS = "CHANGE_USER_STATUS", "Change User Status"
    ASSIGN_ROLE = "ASSIGN_ROLE", "Assign Role"
    MANAGE_ROLE_PERMISSIONS = "MANAGE_ROLE_PERMISSIONS", "Manage Role Permissions"


VALID_MODULE_ACTIONS = {
    PermissionModule.TRANSPORT_REQUESTS: (
        PermissionAction.VIEW, PermissionAction.EDIT,
        PermissionAction.APPROVE, PermissionAction.CANCEL,
    ),
    PermissionModule.DISPATCH_BOARD: (
        PermissionAction.VIEW, PermissionAction.ASSIGN,
        PermissionAction.DISPATCH, PermissionAction.OVERRIDE,
    ),
    PermissionModule.LIVE_MAP: (
        PermissionAction.VIEW, PermissionAction.MANAGE_GEOFENCES,
    ),
    PermissionModule.DRIVERS: (
        PermissionAction.VIEW, PermissionAction.CREATE,
        PermissionAction.EDIT, PermissionAction.MANAGE_DOCUMENTS,
    ),
    PermissionModule.VEHICLES: (
        PermissionAction.VIEW, PermissionAction.CREATE, PermissionAction.EDIT,
        PermissionAction.CHANGE_STATUS, PermissionAction.INSPECT,
        PermissionAction.MANAGE_DOCUMENTS,
    ),
    PermissionModule.FUEL_ANALYTICS: (PermissionAction.VIEW,),
    PermissionModule.MAINTENANCE: (PermissionAction.VIEW,),
    PermissionModule.SYSTEM_SETTINGS: (PermissionAction.VIEW,),
    PermissionModule.USERS_ACCESS: (
        PermissionAction.VIEW_USERS, PermissionAction.CREATE_USER,
        PermissionAction.EDIT_USER, PermissionAction.CHANGE_USER_STATUS,
        PermissionAction.ASSIGN_ROLE, PermissionAction.MANAGE_ROLE_PERMISSIONS,
    ),
}


def valid_module_action(module, action):
    return module in VALID_MODULE_ACTIONS and action in VALID_MODULE_ACTIONS[module]


class RolePermission(models.Model):
    role = models.CharField(max_length=20, choices=StaffProfile.Role.choices)
    module = models.CharField(max_length=32, choices=PermissionModule.choices)
    action = models.CharField(max_length=32, choices=PermissionAction.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("role", "module", "action"),
                name="accounts_unique_role_module_action",
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=StaffProfile.Role.values),
                name="accounts_rolepermission_managed_role",
            ),
        ]
        ordering = ("role", "module", "action")

    def __str__(self):
        return f"{self.role}: {self.module}.{self.action}"

    def clean(self):
        super().clean()
        if not valid_module_action(self.module, self.action):
            raise ValidationError(
                {"action": "Action is not valid for the selected module."}
            )
