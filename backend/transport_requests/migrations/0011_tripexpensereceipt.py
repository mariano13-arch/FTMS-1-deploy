import django.core.validators
import django.db.models.deletion
import transport_requests.models
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0016_vehiclefuelreferencebaseline"),
        ("transport_requests", "0010_ready_before_assignment"),
    ]

    operations = [
        migrations.CreateModel(
            name="TripExpenseReceipt",
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
                    "expense_type",
                    models.CharField(
                        choices=[("FUEL", "Fuel"), ("TOLL", "Toll")],
                        max_length=8,
                    ),
                ),
                ("transaction_at", models.DateTimeField()),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.01"))],
                    ),
                ),
                ("receipt_number", models.CharField(blank=True, default="", max_length=80)),
                ("merchant_or_operator", models.CharField(max_length=160)),
                (
                    "receipt_image",
                    models.FileField(upload_to=transport_requests.models.receipt_image_upload_to),
                ),
                (
                    "liters",
                    models.DecimalField(
                        blank=True,
                        decimal_places=3,
                        max_digits=10,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.001"))],
                    ),
                ),
                (
                    "unit_price",
                    models.DecimalField(
                        blank=True,
                        decimal_places=4,
                        max_digits=10,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.0001"))
                        ],
                    ),
                ),
                (
                    "fuel_type",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("GASOLINE", "Gasoline"),
                            ("DIESEL", "Diesel"),
                            ("", "Unspecified"),
                        ],
                        default="",
                        max_length=20,
                    ),
                ),
                (
                    "fuel_grade",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("UNLEADED_91", "Unleaded 91"),
                            ("PREMIUM_95", "Premium 95"),
                            ("PREMIUM_97", "Premium 97"),
                            ("REGULAR_DIESEL", "Regular Diesel"),
                            ("PREMIUM_DIESEL", "Premium Diesel"),
                            ("", "Unspecified"),
                        ],
                        default="",
                        max_length=20,
                    ),
                ),
                ("toll_plaza", models.CharField(blank=True, default="", max_length=160)),
                ("confirmed_at", models.DateTimeField(auto_now_add=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "dispatch_assignment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="expense_receipts",
                        to="transport_requests.dispatchassignment",
                    ),
                ),
                (
                    "driver",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="expense_receipts",
                        to="fleet.driver",
                    ),
                ),
                (
                    "vehicle",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="expense_receipts",
                        to="fleet.vehicle",
                    ),
                ),
            ],
            options={
                "ordering": ("-transaction_at", "-created_at", "-pk"),
            },
        ),
        migrations.AddIndex(
            model_name="tripexpensereceipt",
            index=models.Index(
                fields=["dispatch_assignment", "-transaction_at"],
                name="trip_rcpt_assign_time_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="tripexpensereceipt",
            index=models.Index(
                fields=["driver", "-created_at"],
                name="trip_receipt_driver_time_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="tripexpensereceipt",
            index=models.Index(
                fields=["expense_type", "receipt_number"],
                name="trip_receipt_type_number_idx",
            ),
        ),
    ]
