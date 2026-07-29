from django.db import models


class Vehicle(models.Model):
    device_id = models.CharField(max_length=64, unique=True)
    plate_number = models.CharField(max_length=32, unique=True)
    display_name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("device_id",)

    def __str__(self):
        return f"{self.device_id} ({self.plate_number})"
