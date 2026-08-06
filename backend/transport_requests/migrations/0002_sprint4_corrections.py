import django.core.validators
from django.db import migrations, models


def repair_invalid_ready_requests(apps, schema_editor):
    request_model = apps.get_model("transport_requests", "TransportRequest")
    request_model.objects.filter(
        status="READY_FOR_DISPATCH", assigned_vehicle__isnull=True
    ).update(status="APPROVED")


class Migration(migrations.Migration):
    dependencies = [("transport_requests", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="transportrequest",
            name="estimated_duration_minutes",
            field=models.PositiveSmallIntegerField(
                default=60,
                validators=[
                    django.core.validators.MinValueValidator(15),
                    django.core.validators.MaxValueValidator(1440),
                ],
            ),
        ),
        migrations.AddField(
            model_name="transportrequest",
            name="required_vehicle_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("SEDAN", "Sedan"),
                    ("SUV", "SUV"),
                    ("VAN", "Van"),
                    ("SHUTTLE_BUS", "Shuttle bus"),
                    ("SERVICE_TRUCK", "Service truck"),
                    ("MOTORCYCLE", "Motorcycle"),
                    ("OTHER", "Other"),
                ],
                default="",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="transportrequest",
            name="request_type",
            field=models.CharField(
                choices=[
                    ("AIRPORT_PICKUP", "Airport pickup"),
                    ("AIRPORT_DROPOFF", "Airport dropoff"),
                    ("GUEST_TRANSFER", "Guest transfer"),
                    ("VIP_TRANSPORT", "VIP transport"),
                    ("STAFF_SHUTTLE", "Staff shuttle"),
                    ("SUPPLIER_PICKUP", "Supplier pickup"),
                    ("FOOD_DELIVERY", "Food delivery"),
                    ("CATERING_DELIVERY", "Catering delivery"),
                    ("BANQUET_LOGISTICS", "Banquet logistics"),
                    ("BRANCH_TRANSFER", "Branch transfer"),
                    ("OTHER", "Other"),
                ],
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="transportrequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("FOR_APPROVAL", "For approval"),
                    ("NEEDS_MORE_DETAILS", "Needs more details"),
                    ("APPROVED", "Approved"),
                    ("REJECTED", "Rejected"),
                    ("READY_FOR_DISPATCH", "Ready for dispatch"),
                    ("CANCELLED", "Cancelled"),
                ],
                default="FOR_APPROVAL",
                max_length=24,
            ),
        ),
        migrations.RunPython(repair_invalid_ready_requests, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="transportrequest",
            constraint=models.CheckConstraint(
                condition=(
                    ~models.Q(status="READY_FOR_DISPATCH")
                    | models.Q(assigned_vehicle__isnull=False)
                ),
                name="tr_ready_requires_vehicle",
            ),
        ),
    ]
