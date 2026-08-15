import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fleet", "0007_driver_driverdocument"),
        ("transport_requests", "0003_request_category_and_delivery_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DispatchAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("selection_mode", models.CharField(choices=[("OPTIMIZED", "Optimized"), ("MANUAL", "Manual")], max_length=12)),
                ("override_reason", models.TextField(blank=True, default="")),
                ("confirmed_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("confirmed_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="confirmed_dispatch_assignments", to=settings.AUTH_USER_MODEL)),
                ("driver", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="dispatch_assignments", to="fleet.driver")),
                ("transport_request", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="dispatch_assignment", to="transport_requests.transportrequest")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="updated_dispatch_assignments", to=settings.AUTH_USER_MODEL)),
                ("vehicle", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="dispatch_assignments", to="fleet.vehicle")),
            ],
            options={
                "ordering": ("transport_request__scheduled_pickup_at", "pk"),
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            ("selection_mode", "OPTIMIZED"),
                            models.Q(("override_reason", ""), _negated=True),
                            _connector="OR",
                        ),
                        name="dispatch_manual_reason_required",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="DispatchAssignmentEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("selection_mode", models.CharField(choices=[("OPTIMIZED", "Optimized"), ("MANUAL", "Manual")], max_length=12)),
                ("reason", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("assignment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="events", to="transport_requests.dispatchassignment")),
                ("new_driver", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="new_dispatch_events", to="fleet.driver")),
                ("new_vehicle", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="new_dispatch_events", to="fleet.vehicle")),
                ("performed_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="dispatch_assignment_events", to=settings.AUTH_USER_MODEL)),
                ("previous_driver", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="previous_dispatch_events", to="fleet.driver")),
                ("previous_vehicle", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="previous_dispatch_events", to="fleet.vehicle")),
            ],
            options={"ordering": ("created_at", "pk")},
        ),
    ]
