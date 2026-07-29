from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("fleet", "0002_vehicle_registry")]
    operations = [
        migrations.RemoveConstraint(
            model_name="vehicle", name="fleet_vehicle_model_year_range"
        ),
        migrations.AddConstraint(
            model_name="vehicle",
            constraint=models.CheckConstraint(
                condition=models.Q(model_year__isnull=True)
                | models.Q(model_year__gte=1980),
                name="fleet_vehicle_model_year_min",
            ),
        ),
    ]
