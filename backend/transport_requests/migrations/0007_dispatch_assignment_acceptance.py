import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("transport_requests", "0006_driver_trip_execution"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="dispatchassignment",
            name="accepted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="dispatchassignment",
            name="accepted_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="accepted_dispatch_assignments",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="dispatchassignmentevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("ASSIGNMENT_CONFIRMED", "Assignment confirmed"),
                    ("ASSIGNMENT_CHANGED", "Assignment changed"),
                    ("DRIVER_ACCEPTED", "Driver accepted"),
                ],
                default="ASSIGNMENT_CONFIRMED",
                max_length=24,
            ),
        ),
    ]
