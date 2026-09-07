from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from fleet.models import Vehicle
from telemetry.models import TelemetryDevice, TelemetryDeviceBinding


class DevicePairingConflict(Exception):
    pass


@transaction.atomic
def pair_device_to_vehicle(*, device_id, vehicle_id, user, replace_current=False):
    device = TelemetryDevice.objects.select_for_update().get(device_id=device_id)
    vehicle = Vehicle.objects.select_for_update().get(pk=vehicle_id)
    if device.registration_status != TelemetryDevice.RegistrationStatus.REGISTERED:
        raise DevicePairingConflict("Only registered devices can be paired.")
    if not vehicle.is_active:
        raise DevicePairingConflict("Telemetry devices can only be paired to active vehicles.")

    bindings = TelemetryDeviceBinding.objects.select_for_update().filter(
        Q(device=device) | Q(vehicle=vehicle),
        unpaired_at__isnull=True,
    )
    device_binding = next((item for item in bindings if item.device_id == device.pk), None)
    vehicle_binding = next((item for item in bindings if item.vehicle_id == vehicle.pk), None)

    if device_binding is not None:
        if device_binding.vehicle_id == vehicle.pk:
            return device_binding, False
        raise DevicePairingConflict("Device is already paired to another vehicle.")

    paired_at = timezone.now()
    if vehicle_binding is not None:
        if not replace_current:
            raise DevicePairingConflict("Vehicle already has a current telemetry device.")
        vehicle_binding.unpaired_at = paired_at
        vehicle_binding.unpaired_by = user
        vehicle_binding.save(update_fields=["unpaired_at", "unpaired_by"])

    try:
        binding = TelemetryDeviceBinding.objects.create(
            device=device,
            vehicle=vehicle,
            paired_at=paired_at,
            paired_by=user,
        )
    except IntegrityError as exc:
        raise DevicePairingConflict("Device or vehicle received a conflicting pairing.") from exc
    return binding, True


@transaction.atomic
def unpair_device(*, device_id, user):
    device = TelemetryDevice.objects.select_for_update().get(device_id=device_id)
    binding = (
        TelemetryDeviceBinding.objects.select_for_update()
        .filter(device=device, unpaired_at__isnull=True)
        .first()
    )
    if binding is None:
        raise DevicePairingConflict("Device is not currently paired.")
    binding.unpaired_at = timezone.now()
    binding.unpaired_by = user
    binding.save(update_fields=["unpaired_at", "unpaired_by"])
    return binding
