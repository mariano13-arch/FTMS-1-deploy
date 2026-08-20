import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("transport_requests", "0005_dispatch_plan"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="dispatchassignment",
            name="completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="dispatchassignment",
            name="destination_arrived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="dispatchassignment",
            name="execution_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="dispatchassignment",
            name="execution_status",
            field=models.CharField(
                choices=[
                    ("ASSIGNED", "Assigned"),
                    ("EN_ROUTE_TO_PICKUP", "En route to pickup"),
                    ("AT_PICKUP", "At pickup"),
                    ("IN_TRANSIT", "In transit"),
                    ("AT_DESTINATION", "At destination"),
                    ("COMPLETED", "Completed"),
                ],
                default="ASSIGNED",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="dispatchassignment",
            name="pickup_arrived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="dispatchassignment",
            name="pickup_departed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="DispatchExecutionEvent",
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
                    "previous_status",
                    models.CharField(
                        choices=[
                            ("ASSIGNED", "Assigned"),
                            ("EN_ROUTE_TO_PICKUP", "En route to pickup"),
                            ("AT_PICKUP", "At pickup"),
                            ("IN_TRANSIT", "In transit"),
                            ("AT_DESTINATION", "At destination"),
                            ("COMPLETED", "Completed"),
                        ],
                        max_length=24,
                    ),
                ),
                (
                    "new_status",
                    models.CharField(
                        choices=[
                            ("ASSIGNED", "Assigned"),
                            ("EN_ROUTE_TO_PICKUP", "En route to pickup"),
                            ("AT_PICKUP", "At pickup"),
                            ("IN_TRANSIT", "In transit"),
                            ("AT_DESTINATION", "At destination"),
                            ("COMPLETED", "Completed"),
                        ],
                        max_length=24,
                    ),
                ),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("START_TOWARD_PICKUP", "Start toward pickup"),
                            ("ARRIVE_AT_PICKUP", "Arrive at pickup"),
                            ("DEPART_PICKUP", "Depart pickup"),
                            ("ARRIVE_AT_DESTINATION", "Arrive at destination"),
                            ("COMPLETE", "Complete"),
                        ],
                        max_length=24,
                    ),
                ),
                (
                    "actor_type",
                    models.CharField(
                        choices=[("DRIVER", "Driver"), ("STAFF", "Staff")],
                        default="DRIVER",
                        max_length=12,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "assignment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="execution_events",
                        to="transport_requests.dispatchassignment",
                    ),
                ),
                (
                    "performed_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="dispatch_execution_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("created_at", "pk")},
        ),
    ]
