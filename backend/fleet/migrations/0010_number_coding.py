import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import fleet.models


class Migration(migrations.Migration):
    dependencies = [
        ("fleet", "0009_vehicle_photo"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="NumberCodingRule",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("authority", models.CharField(max_length=120)),
                ("jurisdiction", models.CharField(max_length=120)),
                (
                    "weekday",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (0, "Monday"),
                            (1, "Tuesday"),
                            (2, "Wednesday"),
                            (3, "Thursday"),
                            (4, "Friday"),
                            (5, "Saturday"),
                            (6, "Sunday"),
                        ]
                    ),
                ),
                (
                    "restricted_last_digits",
                    models.JSONField(validators=[fleet.models.validate_restricted_plate_digits]),
                ),
                ("start_time", models.TimeField(blank=True, null=True)),
                ("end_time", models.TimeField(blank=True, null=True)),
                ("effective_from", models.DateField()),
                ("effective_until", models.DateField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("source_reference", models.CharField(blank=True, default="", max_length=300)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("weekday", "start_time", "pk")},
        ),
        migrations.CreateModel(
            name="NumberCodingSuspension",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("authority", models.CharField(max_length=120)),
                ("jurisdiction", models.CharField(max_length=120)),
                ("starts_at", models.DateTimeField()),
                ("ends_at", models.DateTimeField()),
                ("reason", models.TextField()),
                ("source_reference", models.CharField(max_length=300)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="number_coding_suspensions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("-starts_at", "-pk")},
        ),
        migrations.CreateModel(
            name="VehicleCodingExemption",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("authority", models.CharField(max_length=120)),
                ("jurisdiction", models.CharField(max_length=120)),
                ("starts_at", models.DateTimeField()),
                ("ends_at", models.DateTimeField()),
                ("reason", models.TextField()),
                ("source_reference", models.CharField(max_length=300)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "vehicle",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="number_coding_exemptions",
                        to="fleet.vehicle",
                    ),
                ),
                (
                    "verified_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="verified_number_coding_exemptions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("-starts_at", "-pk")},
        ),
        migrations.AddConstraint(
            model_name="numbercodingrule",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("end_time__isnull", True), ("start_time__isnull", True)),
                    models.Q(("end_time__isnull", False), ("start_time__isnull", False)),
                    _connector="OR",
                ),
                name="fleet_coding_rule_time_pair",
            ),
        ),
        migrations.AddConstraint(
            model_name="numbercodingrule",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("effective_until__isnull", True),
                    ("effective_until__gte", models.F("effective_from")),
                    _connector="OR",
                ),
                name="fleet_coding_rule_dates_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="numbercodingsuspension",
            constraint=models.CheckConstraint(
                condition=models.Q(("ends_at__gt", models.F("starts_at"))),
                name="fleet_coding_suspension_period_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="vehiclecodingexemption",
            constraint=models.CheckConstraint(
                condition=models.Q(("ends_at__gt", models.F("starts_at"))),
                name="fleet_coding_exemption_period_valid",
            ),
        ),
    ]
