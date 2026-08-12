from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


PASSENGER_TYPES = {
    "AIRPORT_PICKUP", "AIRPORT_DROPOFF", "GUEST_TRANSFER",
    "VIP_TRANSPORT", "STAFF_SHUTTLE",
}
DELIVERY_TYPES = {
    "SUPPLIER_PICKUP", "FOOD_DELIVERY", "CATERING_DELIVERY", "BANQUET_LOGISTICS",
}


def backfill_request_categories(apps, schema_editor):
    request_model = apps.get_model("transport_requests", "TransportRequest")
    request_model.objects.filter(request_type__in=PASSENGER_TYPES).update(
        request_category="PASSENGER_TRANSPORT"
    )
    request_model.objects.filter(request_type__in=DELIVERY_TYPES).update(
        request_category="DELIVERY_LOGISTICS"
    )


class Migration(migrations.Migration):
    dependencies = [("transport_requests", "0002_sprint4_corrections")]

    operations = [
        migrations.AddField(
            model_name="transportrequest", name="request_category",
            field=models.CharField(
                blank=True,
                choices=[
                    ("PASSENGER_TRANSPORT", "Passenger transport"),
                    ("DELIVERY_LOGISTICS", "Delivery logistics"),
                ],
                max_length=24, null=True,
            ),
        ),
        migrations.AddField(
            model_name="transportrequest", name="load_description",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="transportrequest", name="load_quantity",
            field=models.PositiveIntegerField(
                blank=True, null=True, validators=[MinValueValidator(1)]
            ),
        ),
        migrations.AddField(
            model_name="transportrequest", name="estimated_weight_kg",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=10, null=True,
                validators=[MinValueValidator(Decimal("0.01"))],
            ),
        ),
        migrations.AddField(
            model_name="transportrequest", name="handling_instructions",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="transportrequest", name="temperature_requirement",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="transportrequest", name="passenger_count",
            field=models.PositiveSmallIntegerField(validators=[MaxValueValidator(100)]),
        ),
        migrations.RunPython(backfill_request_categories, migrations.RunPython.noop),
    ]
