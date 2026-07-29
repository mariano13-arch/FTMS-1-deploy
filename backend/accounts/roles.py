from .models import StaffProfile

SUPER_ADMIN = "SUPER_ADMIN"


def resolve_role(user):
    if not user or not user.is_authenticated or not user.is_active or not user.is_staff:
        return None
    if user.is_superuser:
        return SUPER_ADMIN
    try:
        return user.staff_profile.role
    except StaffProfile.DoesNotExist:
        return None


def can_view(user):
    return resolve_role(user) is not None


def can_create(user):
    return resolve_role(user) == SUPER_ADMIN


def can_edit(user):
    return resolve_role(user) in {SUPER_ADMIN, StaffProfile.Role.FLEET_MANAGER}


def can_change_status(user):
    return resolve_role(user) == SUPER_ADMIN


def user_data(user):
    display_name = user.get_full_name().strip() or user.username
    return {
        "id": user.pk,
        "username": user.username,
        "display_name": display_name,
        "role": resolve_role(user),
    }
