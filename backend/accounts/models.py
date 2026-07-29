from django.conf import settings
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
