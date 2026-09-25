from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("fleet", "0015_fuelpricerecord_fuel_grade")]

    operations = [
        migrations.CreateModel(
            name="VehicleFuelReferenceBaseline",
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
                    "reference_fuel_rate_lph",
                    models.DecimalField(
                        decimal_places=4,
                        max_digits=8,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.0001"))],
                    ),
                ),
                (
                    "provenance",
                    models.CharField(
                        choices=[("CAPSTONE_REFERENCE", "Capstone reference")],
                        default="CAPSTONE_REFERENCE",
                        max_length=32,
                    ),
                ),
                ("basis_version", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "vehicle",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fuel_reference_baseline",
                        to="fleet.vehicle",
                    ),
                ),
            ],
            options={
                "ordering": ("vehicle__device_id",),
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("reference_fuel_rate_lph__gt", 0)),
                        name="fuel_reference_rate_positive",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("provenance", "CAPSTONE_REFERENCE")),
                        name="fuel_reference_capstone_provenance",
                    ),
                ],
            },
        )
    ]
