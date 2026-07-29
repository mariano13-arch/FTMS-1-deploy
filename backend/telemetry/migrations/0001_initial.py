import django.contrib.gis.db.models.fields
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [("fleet", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="TelemetryEvent",
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
                ("schema_version", models.CharField(max_length=8)),
                ("event_id", models.CharField(max_length=128, unique=True)),
                ("sequence_number", models.PositiveBigIntegerField()),
                ("recorded_at", models.DateTimeField()),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                (
                    "location",
                    django.contrib.gis.db.models.fields.PointField(srid=4326),
                ),
                (
                    "gnss_speed_kph",
                    models.DecimalField(decimal_places=2, max_digits=6),
                ),
                ("rpm", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "coolant_c",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=5,
                        null=True,
                    ),
                ),
                (
                    "engine_load_pct",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=5,
                        null=True,
                    ),
                ),
                (
                    "driving_event",
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
                (
                    "vehicle",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="telemetry_events",
                        to="fleet.vehicle",
                    ),
                ),
            ],
            options={
                "ordering": (
                    "-recorded_at",
                    "-sequence_number",
                    "-received_at",
                    "-pk",
                ),
                "indexes": [
                    models.Index(
                        fields=[
                            "vehicle",
                            "-recorded_at",
                            "-sequence_number",
                            "-received_at",
                        ],
                        name="tel_vehicle_latest_idx",
                    ),
                    models.Index(fields=["recorded_at"], name="tel_recorded_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            ("gnss_speed_kph__gte", 0),
                            ("gnss_speed_kph__lte", 300),
                        ),
                        name="tel_speed_valid",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("rpm__isnull", True),
                            models.Q(("rpm__gte", 0), ("rpm__lte", 12000)),
                            _connector="OR",
                        ),
                        name="tel_rpm_valid",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("engine_load_pct__isnull", True),
                            models.Q(
                                ("engine_load_pct__gte", 0),
                                ("engine_load_pct__lte", 100),
                            ),
                            _connector="OR",
                        ),
                        name="tel_load_valid",
                    ),
                ],
            },
        ),
    ]
