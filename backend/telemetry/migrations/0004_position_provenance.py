from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("telemetry", "0003_device_registry_and_bindings")]

    operations = [
        migrations.AddField(
            model_name="telemetryevent",
            name="position_source",
            field=models.CharField(
                choices=[("GNSS", "GNSS"), ("CELLULAR_LBS", "Cellular LBS")],
                default="GNSS",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="telemetryevent",
            name="position_accuracy_m",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=10, null=True
            ),
        ),
        migrations.RemoveConstraint(model_name="telemetryevent", name="tel_speed_valid"),
        migrations.AlterField(
            model_name="telemetryevent",
            name="gnss_speed_kph",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=6, null=True
            ),
        ),
        migrations.AddConstraint(
            model_name="telemetryevent",
            constraint=models.CheckConstraint(
                condition=Q(gnss_speed_kph__isnull=True)
                | Q(gnss_speed_kph__gte=0, gnss_speed_kph__lte=300),
                name="tel_speed_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="telemetryevent",
            constraint=models.CheckConstraint(
                condition=Q(position_source="GNSS", gnss_speed_kph__isnull=False)
                | Q(
                    position_source="CELLULAR_LBS",
                    gnss_speed_kph__isnull=True,
                    position_accuracy_m__gt=0,
                ),
                name="tel_position_source_valid",
            ),
        ),
    ]
