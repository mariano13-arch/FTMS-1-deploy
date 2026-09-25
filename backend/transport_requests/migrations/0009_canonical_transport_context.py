# Generated for the canonical transport execution flow.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("transport_requests", "0008_integrationclient")]

    operations = [
        migrations.AlterField(
            model_name="transportrequest",
            name="source_system",
            field=models.CharField(
                choices=[
                    ("HOTEL_MANAGEMENT_SYSTEM", "Hotel management system"),
                    ("RESTAURANT_MANAGEMENT_SYSTEM", "Restaurant management system"),
                    ("SUPPLY_CHAIN_MANAGEMENT_SYSTEM", "Supply chain management system"),
                    ("MANUAL_STAFF_ENTRY", "Manual staff entry"),
                    ("OTHER_SUBSYSTEM", "Other subsystem"),
                ],
                max_length=40,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="integrationclient",
            name="integration_client_trusted_source",
        ),
        migrations.AlterField(
            model_name="integrationclient",
            name="source_system",
            field=models.CharField(
                choices=[
                    ("HOTEL_MANAGEMENT_SYSTEM", "Hotel management system"),
                    ("RESTAURANT_MANAGEMENT_SYSTEM", "Restaurant management system"),
                    ("SUPPLY_CHAIN_MANAGEMENT_SYSTEM", "Supply chain management system"),
                ],
                max_length=40,
            ),
        ),
        migrations.AddConstraint(
            model_name="integrationclient",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    source_system__in=(
                        "HOTEL_MANAGEMENT_SYSTEM",
                        "RESTAURANT_MANAGEMENT_SYSTEM",
                        "SUPPLY_CHAIN_MANAGEMENT_SYSTEM",
                    )
                ),
                name="integration_client_trusted_source",
            ),
        ),
        migrations.CreateModel(
            name="TransportRequestFlightContext",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(choices=[("FLIGHTRADAR24", "Flightradar24")], default="FLIGHTRADAR24", max_length=24)),
                ("flight_number", models.CharField(max_length=20)),
                ("flight_date", models.DateField(blank=True, null=True)),
                ("origin_airport", models.CharField(blank=True, default="", max_length=120)),
                ("arrival_airport", models.CharField(blank=True, default="", max_length=120)),
                ("terminal", models.CharField(blank=True, default="", max_length=40)),
                ("scheduled_arrival_at", models.DateTimeField(blank=True, null=True)),
                ("estimated_arrival_at", models.DateTimeField(blank=True, null=True)),
                ("actual_arrival_at", models.DateTimeField(blank=True, null=True)),
                ("provider_flight_status", models.CharField(blank=True, default="", max_length=80)),
                ("refresh_status", models.CharField(choices=[("NOT_CONFIGURED", "Not configured"), ("NOT_REFRESHED", "Not refreshed"), ("AVAILABLE", "Available"), ("UNAVAILABLE", "Unavailable")], default="NOT_REFRESHED", max_length=24)),
                ("last_refresh_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("last_successful_refresh_at", models.DateTimeField(blank=True, null=True)),
                ("refresh_message", models.CharField(blank=True, default="", max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("transport_request", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="flight_context", to="transport_requests.transportrequest")),
            ],
            options={"ordering": ("transport_request_id",)},
        ),
        migrations.CreateModel(
            name="SourceResultOutbox",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(default="TRIP_COMPLETED", max_length=32)),
                ("payload", models.JSONField(default=dict)),
                ("delivery_status", models.CharField(choices=[("UNCONFIGURED", "Callback not configured"), ("PENDING", "Pending"), ("DELIVERED", "Delivered"), ("FAILED", "Failed")], default="UNCONFIGURED", max_length=16)),
                ("delivery_attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, default="", max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("transport_request", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="source_result_outbox", to="transport_requests.transportrequest")),
            ],
            options={
                "ordering": ("created_at", "pk"),
                "constraints": [models.UniqueConstraint(fields=("transport_request", "event_type"), name="source_result_outbox_event_uq")],
            },
        ),
    ]
