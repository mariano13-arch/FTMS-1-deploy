from .models import (
    VALID_MODULE_ACTIONS,
    PermissionAction,
    PermissionModule,
    RolePermission,
    StaffProfile,
    valid_module_action,
)

MANDATORY_MFA_ROLES = {
    StaffProfile.Role.FLEET_ADMIN,
    StaffProfile.Role.FLEET_MANAGER,
}


def resolve_role(user):
    if not user or not user.is_authenticated or not user.is_active or not user.is_staff:
        return None
    try:
        role = user.staff_profile.role
    except StaffProfile.DoesNotExist:
        return None
    return role if role in StaffProfile.Role.values else None


def can_view(user):
    return resolve_role(user) is not None


def requires_mfa(user):
    return resolve_role(user) in MANDATORY_MFA_ROLES


def is_driver_identity(user):
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if user.is_staff or user.is_superuser:
        return False
    try:
        staff_profile = user.staff_profile
    except StaffProfile.DoesNotExist:
        return True
    return staff_profile is None


def can_create(user):
    return has_module_permission(user, PermissionModule.VEHICLES, PermissionAction.CREATE)


def can_edit(user):
    return has_module_permission(user, PermissionModule.VEHICLES, PermissionAction.EDIT)


def can_change_status(user):
    return has_module_permission(
        user, PermissionModule.VEHICLES, PermissionAction.CHANGE_STATUS
    )


def has_module_permission(user, module, action):
    if not valid_module_action(module, action):
        return False
    role = resolve_role(user)
    if role == StaffProfile.Role.FLEET_ADMIN:
        return True
    if role not in StaffProfile.Role.values:
        return False
    return RolePermission.objects.filter(
        role=role, module=module, action=action
    ).exists()


def user_data(user):
    display_name = user.get_full_name().strip() or user.username
    role = resolve_role(user)
    if role == StaffProfile.Role.FLEET_ADMIN:
        capabilities = [
            f"{module}.{action}"
            for module, actions in VALID_MODULE_ACTIONS.items()
            for action in actions
        ]
    elif role in StaffProfile.Role.values:
        capabilities = [
            f"{module}.{action}"
            for module, action in RolePermission.objects.filter(role=role)
            .order_by("module", "action")
            .values_list("module", "action")
        ]
    else:
        capabilities = []
    return {
        "id": user.pk,
        "username": user.username,
        "display_name": display_name,
        "role": role,
        "capabilities": capabilities,
    }
