import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fleet", "0011_driver_local_schedule"),
        ("telemetry", "0007_simulated_test_position"),
        ("transport_requests", "0010_ready_before_assignment"),
    ]

    operations = [
        migrations.CreateModel(
            name="DriverSafetyEvent",
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
                    "event_type",
                    models.CharField(
                        choices=[
                            ("NORMAL", "Normal"),
                            ("HARSH_BRAKING", "Harsh braking"),
                            ("HARSH_ACCELERATION", "Harsh acceleration"),
                            ("SHARP_TURN", "Sharp turn"),
                        ],
                        max_length=32,
                    ),
                ),
                ("occurred_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "assignment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="driver_safety_events",
                        to="transport_requests.dispatchassignment",
                    ),
                ),
                (
                    "driver",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="safety_events",
                        to="fleet.driver",
                    ),
                ),
                (
                    "telemetry_event",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="driver_safety_event",
                        to="telemetry.telemetryevent",
                    ),
                ),
                (
                    "vehicle",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="driver_safety_events",
                        to="fleet.vehicle",
                    ),
                ),
            ],
            options={
                "ordering": ("-occurred_at", "-pk"),
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            event_type__in=(
                                "HARSH_ACCELERATION",
                                "HARSH_BRAKING",
                                "SHARP_TURN",
                            )
                        ),
                        name="driver_safety_event_type_harsh",
                    )
                ],
            },
        )
    ]
