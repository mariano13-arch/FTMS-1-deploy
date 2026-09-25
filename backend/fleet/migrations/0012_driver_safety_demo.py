from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("fleet", "0011_driver_local_schedule")]
    operations = [
        migrations.CreateModel(
            name="DriverSafetyDemoProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("safety_score", models.PositiveSmallIntegerField()),
                ("completed_trip_count", models.PositiveSmallIntegerField()),
                ("driving_hours", models.DecimalField(decimal_places=1, max_digits=5)),
                ("safety_event_count", models.PositiveSmallIntegerField()),
                ("source", models.CharField(choices=[("DEMO_SEED", "Demo seed")], max_length=20)),
                ("generated_at", models.DateTimeField()),
                ("driver", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="safety_demo_profile", to="fleet.driver")),
            ],
            options={"ordering": ("driver__driver_code",)},
        ),
        migrations.CreateModel(
            name="DriverSafetyDemoEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence", models.PositiveSmallIntegerField()),
                ("event_type", models.CharField(choices=[("HARSH_ACCELERATION", "Harsh Acceleration"), ("HARSH_BRAKING", "Harsh Braking"), ("SHARP_TURN", "Sharp Turn")], max_length=32)),
                ("occurred_at", models.DateTimeField()),
                ("source", models.CharField(choices=[("DEMO_SEED", "Demo seed")], default="DEMO_SEED", max_length=20)),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="fleet.driversafetydemoprofile")),
            ],
            options={"ordering": ("-occurred_at", "-pk")},
        ),
        migrations.AddConstraint(
            model_name="driversafetydemoevent",
            constraint=models.UniqueConstraint(fields=("profile", "sequence"), name="unique_demo_safety_event_sequence"),
        ),
    ]
