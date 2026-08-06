# Generated for Sprint 4.
import django.core.validators
import django.db.models.deletion
import transport_requests.models
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("fleet", "0003_dynamic_model_year_ceiling"),
    ]
    operations = [
        migrations.CreateModel(
            name="TransportRequest",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("request_number", models.CharField(default=transport_requests.models.generate_request_number, editable=False, max_length=24, unique=True)),
                ("source_system", models.CharField(choices=[("HOTEL_MANAGEMENT_SYSTEM", "Hotel management system"), ("RESTAURANT_MANAGEMENT_SYSTEM", "Restaurant management system"), ("MANUAL_STAFF_ENTRY", "Manual staff entry"), ("OTHER_SUBSYSTEM", "Other subsystem")], max_length=40)),
                ("external_reference", models.CharField(blank=True, default="", max_length=120)),
                ("request_type", models.CharField(choices=[("AIRPORT_PICKUP", "Airport pickup"), ("GUEST_TRANSFER", "Guest transfer"), ("SUPPLIER_PICKUP", "Supplier pickup"), ("FOOD_DELIVERY", "Food delivery"), ("BRANCH_TRANSFER", "Branch transfer"), ("OTHER", "Other")], max_length=30)),
                ("requester_name", models.CharField(max_length=160)),
                ("requester_contact", models.CharField(blank=True, default="", max_length=160)),
                ("pickup_name", models.CharField(max_length=200)),
                ("pickup_address", models.CharField(max_length=300)),
                ("pickup_latitude", models.DecimalField(decimal_places=6, max_digits=9, validators=[django.core.validators.MinValueValidator(-90), django.core.validators.MaxValueValidator(90)])),
                ("pickup_longitude", models.DecimalField(decimal_places=6, max_digits=9, validators=[django.core.validators.MinValueValidator(-180), django.core.validators.MaxValueValidator(180)])),
                ("destination_name", models.CharField(max_length=200)),
                ("destination_address", models.CharField(max_length=300)),
                ("destination_latitude", models.DecimalField(decimal_places=6, max_digits=9, validators=[django.core.validators.MinValueValidator(-90), django.core.validators.MaxValueValidator(90)])),
                ("destination_longitude", models.DecimalField(decimal_places=6, max_digits=9, validators=[django.core.validators.MinValueValidator(-180), django.core.validators.MaxValueValidator(180)])),
                ("scheduled_pickup_at", models.DateTimeField()),
                ("passenger_count", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(100)])),
                ("luggage_count", models.PositiveSmallIntegerField(default=0, validators=[django.core.validators.MaxValueValidator(100)])),
                ("priority", models.CharField(choices=[("LOW", "Low"), ("NORMAL", "Normal"), ("HIGH", "High"), ("URGENT", "Urgent")], default="NORMAL", max_length=10)),
                ("notes", models.TextField(blank=True, default="")),
                ("status", models.CharField(choices=[("FOR_APPROVAL", "For approval"), ("APPROVED", "Approved"), ("REJECTED", "Rejected"), ("READY_FOR_DISPATCH", "Ready for dispatch"), ("CANCELLED", "Cancelled")], default="FOR_APPROVAL", max_length=24)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="approved_transport_requests", to=settings.AUTH_USER_MODEL)),
                ("assigned_vehicle", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="transport_requests", to="fleet.vehicle")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_transport_requests", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("scheduled_pickup_at", "created_at"), "indexes": [models.Index(fields=["status"], name="tr_status_idx"), models.Index(fields=["scheduled_pickup_at"], name="tr_schedule_idx"), models.Index(fields=["priority"], name="tr_priority_idx"), models.Index(fields=["source_system"], name="tr_source_idx")]},
        ),
        migrations.CreateModel(
            name="TransportRequestEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=40)),
                ("previous_status", models.CharField(blank=True, default="", max_length=24)),
                ("new_status", models.CharField(blank=True, default="", max_length=24)),
                ("note", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("performed_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="transport_requests.transportrequest")),
            ], options={"ordering": ("created_at", "pk")},
        ),
        migrations.AddConstraint(
            model_name="transportrequest",
            constraint=models.UniqueConstraint(condition=models.Q(("external_reference", ""), _negated=True), fields=("source_system", "external_reference"), name="tr_source_external_unique"),
        ),
    ]
