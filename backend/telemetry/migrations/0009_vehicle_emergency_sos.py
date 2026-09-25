import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fleet", "0012_driver_safety_demo"),
        ("telemetry", "0008_driver_safety_event"),
    ]

    operations = [
        migrations.CreateModel(
            name="VehicleEmergencySOS",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("ACTIVE", "Active"), ("CLEARED", "Cleared")], max_length=12)),
                ("source", models.CharField(choices=[("PHYSICAL_BUTTON", "Physical emergency button")], max_length=24)),
                ("activated_at", models.DateTimeField()),
                ("cleared_at", models.DateTimeField(blank=True, null=True)),
                ("device", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="emergency_sos_events", to="telemetry.telemetrydevice")),
                ("driver", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="emergency_sos_events", to="fleet.driver")),
                ("vehicle", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="emergency_sos_events", to="fleet.vehicle")),
            ],
            options={"ordering": ("-activated_at", "-pk")},
        ),
        migrations.AddConstraint(
            model_name="vehicleemergencysos",
            constraint=models.UniqueConstraint(condition=models.Q(("status", "ACTIVE")), fields=("device",), name="telemetry_one_active_sos_per_device"),
        ),
        migrations.AddConstraint(
            model_name="vehicleemergencysos",
            constraint=models.CheckConstraint(condition=models.Q(models.Q(("cleared_at__isnull", True), ("status", "ACTIVE")), models.Q(("cleared_at__isnull", False), ("status", "CLEARED")), _connector="OR"), name="telemetry_sos_status_timestamp_consistent"),
        ),
    ]
