from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("telemetry", "0004_position_provenance")]

    operations = [
        migrations.AlterField(
            model_name="telemetryevent",
            name="driving_event",
            field=models.CharField(
                blank=True,
                choices=[
                    ("NORMAL", "Normal"),
                    ("HARSH_BRAKING", "Harsh braking"),
                    ("HARSH_ACCELERATION", "Harsh acceleration"),
                    ("SHARP_TURN", "Sharp turn"),
                ],
                max_length=32,
                null=True,
            ),
        ),
    ]
