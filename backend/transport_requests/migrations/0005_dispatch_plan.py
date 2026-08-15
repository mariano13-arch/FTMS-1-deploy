import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fleet", "0007_driver_driverdocument"),
        ("transport_requests", "0004_dispatch_assignment"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DispatchPlan",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "plan_type",
                    models.CharField(
                        choices=[("CONSOLIDATED", "Consolidated")],
                        default="CONSOLIDATED",
                        max_length=16,
                    ),
                ),
                ("confirmed_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "confirmed_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="confirmed_dispatch_plans",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "driver",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="dispatch_plans",
                        to="fleet.driver",
                    ),
                ),
                (
                    "vehicle",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="dispatch_plans",
                        to="fleet.vehicle",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="dispatchassignment",
            name="plan",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="assignments",
                to="transport_requests.dispatchplan",
            ),
        ),
        migrations.CreateModel(
            name="DispatchPlanStop",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "stop_type",
                    models.CharField(
                        choices=[("PICKUP", "Pickup"), ("DELIVERY", "Delivery")], max_length=10
                    ),
                ),
                ("sequence", models.PositiveSmallIntegerField()),
                (
                    "plan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="stops",
                        to="transport_requests.dispatchplan",
                    ),
                ),
                (
                    "transport_request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="dispatch_plan_stops",
                        to="transport_requests.transportrequest",
                    ),
                ),
            ],
            options={"ordering": ("sequence", "pk")},
        ),
        migrations.CreateModel(
            name="DispatchPlanEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("event_type", models.CharField(max_length=32)),
                ("details", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "performed_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="dispatch_plan_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "plan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="events",
                        to="transport_requests.dispatchplan",
                    ),
                ),
            ],
            options={"ordering": ("created_at", "pk")},
        ),
        migrations.AddConstraint(
            model_name="dispatchplanstop",
            constraint=models.UniqueConstraint(
                fields=("plan", "sequence"), name="dispatch_plan_sequence_uq"
            ),
        ),
        migrations.AddConstraint(
            model_name="dispatchplanstop",
            constraint=models.UniqueConstraint(
                fields=("plan", "transport_request", "stop_type"),
                name="dispatch_plan_request_stop_uq",
            ),
        ),
    ]
