import django.core.validators
from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [("fleet", "0001_initial")]
    operations = [
        migrations.AlterField(model_name="vehicle", name="plate_number", field=models.CharField(max_length=32)),
        migrations.AddField(model_name="vehicle", name="manufacturer", field=models.CharField(blank=True, default="", max_length=120)),
        migrations.AddField(model_name="vehicle", name="model", field=models.CharField(blank=True, default="", max_length=120)),
        migrations.AlterField(
            model_name="vehicle", name="device_id",
            field=models.CharField(
                max_length=64, unique=True,
                validators=[django.core.validators.RegexValidator("^[A-Z0-9][A-Z0-9._-]{0,63}$")],
            ),
        ),
        migrations.AddField(
            model_name="vehicle", name="model_year",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True,
                validators=[django.core.validators.MinValueValidator(1980)],
            ),
        ),
        migrations.AddField(
            model_name="vehicle", name="passenger_capacity",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True,
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(100)],
            ),
        ),
        migrations.AddField(
            model_name="vehicle", name="vehicle_type",
            field=models.CharField(
                choices=[("SEDAN","Sedan"),("SUV","SUV"),("VAN","Van"),("SHUTTLE_BUS","Shuttle bus"),("SERVICE_TRUCK","Service truck"),("MOTORCYCLE","Motorcycle"),("OTHER","Other")],
                default="OTHER", max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="vehicle",
            constraint=models.CheckConstraint(
                condition=models.Q(device_id__regex="^[A-Z0-9][A-Z0-9._-]{0,63}$"),
                name="fleet_vehicle_device_id_format",
            ),
        ),
        migrations.AddConstraint(
            model_name="vehicle",
            constraint=models.UniqueConstraint(Lower("plate_number"), name="fleet_vehicle_plate_ci_unique"),
        ),
        migrations.AddConstraint(
            model_name="vehicle",
            constraint=models.CheckConstraint(
                condition=models.Q(model_year__isnull=True) | models.Q(model_year__range=(1980, 2027)),
                name="fleet_vehicle_model_year_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="vehicle",
            constraint=models.CheckConstraint(
                condition=models.Q(passenger_capacity__isnull=True) | models.Q(passenger_capacity__range=(1, 100)),
                name="fleet_vehicle_capacity_range",
            ),
        ),
    ]
