import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrate_existing_vehicle_mappings(apps, schema_editor):
    TelemetryDevice = apps.get_model("telemetry", "TelemetryDevice")
    TelemetryDeviceBinding = apps.get_model("telemetry", "TelemetryDeviceBinding")
    TelemetryEvent = apps.get_model("telemetry", "TelemetryEvent")
    Vehicle = apps.get_model("fleet", "Vehicle")

    for vehicle in Vehicle.objects.order_by("pk").iterator():
        device, _ = TelemetryDevice.objects.get_or_create(
            device_id=vehicle.device_id,
            defaults={"registration_status": "REGISTERED"},
        )
        TelemetryDeviceBinding.objects.get_or_create(
            device_id=device.pk,
            vehicle_id=vehicle.pk,
            unpaired_at=None,
            defaults={"paired_at": vehicle.created_at},
        )
        TelemetryEvent.objects.filter(
            vehicle_id=vehicle.pk,
            device_id__isnull=True,
        ).update(device_id=device.pk)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("fleet", "0007_driver_driverdocument"),
        ("telemetry", "0002_geofence_geofenceevent"),
    ]

    operations = [
        migrations.CreateModel(
            name="TelemetryDevice",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "device_id",
                    models.CharField(
                        max_length=64,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                "^[A-Z0-9][A-Z0-9._-]{0,63}$"
                            )
                        ],
                    ),
                ),
                (
                    "registration_status",
                    models.CharField(
                        choices=[("REGISTERED", "Registered"), ("RETIRED", "Retired")],
                        default="REGISTERED",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("device_id",),
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            device_id__regex="^[A-Z0-9][A-Z0-9._-]{0,63}$"
                        ),
                        name="telemetry_device_id_format",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="TelemetryDeviceBinding",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("paired_at", models.DateTimeField()),
                ("unpaired_at", models.DateTimeField(blank=True, null=True)),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="bindings",
                        to="telemetry.telemetrydevice",
                    ),
                ),
                (
                    "vehicle",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="telemetry_device_bindings",
                        to="fleet.vehicle",
                    ),
                ),
                (
                    "paired_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="telemetry_device_pairings",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "unpaired_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="telemetry_device_unpairings",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-paired_at", "-pk"),
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(unpaired_at__isnull=True),
                        fields=("device",),
                        name="telemetry_one_active_vehicle_per_device",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(unpaired_at__isnull=True),
                        fields=("vehicle",),
                        name="telemetry_one_active_device_per_vehicle",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(unpaired_at__isnull=True)
                        | models.Q(unpaired_at__gte=models.F("paired_at")),
                        name="telemetry_binding_dates_ordered",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="telemetryevent",
            name="device",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="telemetry_events",
                to="telemetry.telemetrydevice",
            ),
        ),
        migrations.RunPython(migrate_existing_vehicle_mappings, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="telemetryevent",
            name="device",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="telemetry_events",
                to="telemetry.telemetrydevice",
            ),
        ),
    ]
