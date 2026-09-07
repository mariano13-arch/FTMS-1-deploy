from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from fleet.models import Vehicle
from telemetry.models import TelemetryDevice, TelemetryDeviceBinding


@receiver(post_save, sender=Vehicle, dispatch_uid="telemetry.bootstrap_vehicle_device_mapping")
def bootstrap_vehicle_device_mapping(sender, instance, created, **kwargs):
    if not created:
        return
    device, _ = TelemetryDevice.objects.get_or_create(device_id=instance.device_id)
    TelemetryDeviceBinding.objects.get_or_create(
        device=device,
        vehicle=instance,
        unpaired_at=None,
        defaults={"paired_at": instance.created_at or timezone.now()},
    )
