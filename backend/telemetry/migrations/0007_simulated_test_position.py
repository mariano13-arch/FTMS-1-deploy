from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("telemetry", "0006_telemetryevent_obd_source")]

    operations = [
        migrations.AlterField(
            model_name="telemetryevent",
            name="position_source",
            field=models.CharField(
                choices=[
                    ("GNSS", "GNSS"),
                    ("CELLULAR_LBS", "Cellular LBS"),
                    ("SIMULATED_TEST", "Simulated test data"),
                ],
                default="GNSS",
                max_length=16,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="telemetryevent",
            name="tel_position_source_valid",
        ),
        migrations.AddConstraint(
            model_name="telemetryevent",
            constraint=models.CheckConstraint(
                condition=(
                    Q(position_source="GNSS", gnss_speed_kph__isnull=False)
                    | Q(
                        position_source="CELLULAR_LBS",
                        gnss_speed_kph__isnull=True,
                        position_accuracy_m__gt=0,
                    )
                    | Q(
                        position_source="SIMULATED_TEST",
                        gnss_speed_kph__isnull=True,
                        position_accuracy_m__isnull=True,
                    )
                ),
                name="tel_position_source_valid",
            ),
        ),
    ]
