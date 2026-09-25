from django.contrib.auth import get_user_model

from .models import StaffProfile, UserNotification
from .roles import has_module_permission


def notify_capability_users(
    *,
    module,
    action,
    notification_type,
    title,
    message,
    target_url,
    source_key,
    exclude_user_id=None,
):
    """Persist one deduplicated notification for each currently eligible staff user."""
    users = (
        get_user_model()
        .objects.filter(
            is_active=True,
            is_staff=True,
            staff_profile__role__in=StaffProfile.Role.values,
        )
        .select_related("staff_profile")
        .order_by("pk")
    )
    if exclude_user_id is not None:
        users = users.exclude(pk=exclude_user_id)
    created = []
    for user in users.iterator():
        if not has_module_permission(user, module, action):
            continue
        notification, was_created = UserNotification.objects.get_or_create(
            recipient=user,
            source_key=source_key,
            defaults={
                "notification_type": notification_type,
                "title": title,
                "message": message,
                "target_url": target_url,
            },
        )
        if was_created:
            created.append(notification)
    return created
