from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("fleet", "0010_number_coding")]
    operations = [
        migrations.AddField(
            model_name="driver", name="work_shift",
            field=models.CharField(
                choices=[("DAY", "Day Shift"), ("NIGHT", "Night Shift")],
                default="DAY", max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="driver", name="weekly_rest_days",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
