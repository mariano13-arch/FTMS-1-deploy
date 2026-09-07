from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("telemetry", "0005_nullable_driving_event")]

    operations = [
        migrations.AddField(
            model_name="telemetryevent",
            name="obd_source",
            field=models.CharField(
                blank=True,
                choices=[
                    ("SIMULATED_TEST", "Simulated test"),
                    ("PHYSICAL_OBD", "Physical OBD"),
                ],
                max_length=16,
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="telemetryevent",
            constraint=models.CheckConstraint(
                condition=~Q(schema_version="1.2")
                | Q(obd_source__isnull=False)
                | Q(rpm__isnull=True, coolant_c__isnull=True, engine_load_pct__isnull=True),
                name="tel_v12_obd_source_required",
            ),
        ),
    ]
