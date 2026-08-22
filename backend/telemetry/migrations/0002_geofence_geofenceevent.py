import uuid

import django.contrib.gis.db.models.fields
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("telemetry", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Geofence",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120)),
                ("description", models.CharField(blank=True, max_length=500)),
                ("category", models.CharField(choices=[("DEPOT", "Depot"), ("CUSTOMER", "Customer site"), ("HOTEL", "Hotel property"), ("RESTRICTED", "Restricted area"), ("CUSTOM", "Custom")], default="CUSTOM", max_length=20)),
                ("shape_type", models.CharField(choices=[("CIRCLE", "Circle"), ("POLYGON", "Custom polygon")], max_length=12)),
                ("boundary", django.contrib.gis.db.models.fields.PolygonField(srid=4326)),
                ("center", django.contrib.gis.db.models.fields.PointField(srid=4326)),
                ("radius_meters", models.PositiveIntegerField(blank=True, null=True)),
                ("color", models.CharField(default="#008F8C", max_length=7)),
                ("show_on_map", models.BooleanField(default=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_geofences", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("name", "pk"),
                "indexes": [models.Index(fields=["is_active", "show_on_map"], name="geofence_visible_idx")],
                "constraints": [models.CheckConstraint(condition=models.Q(radius_meters__isnull=True) | models.Q(radius_meters__gte=25, radius_meters__lte=5000), name="geofence_radius_valid")],
            },
        ),
        migrations.CreateModel(
            name="GeofenceEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(choices=[("ENTER", "Entered"), ("EXIT", "Exited")], max_length=8)),
                ("occurred_at", models.DateTimeField()),
                ("location", django.contrib.gis.db.models.fields.PointField(srid=4326)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("geofence", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="telemetry.geofence")),
                ("telemetry_event", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="geofence_events", to="telemetry.telemetryevent")),
                ("vehicle", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="geofence_events", to="fleet.vehicle")),
            ],
            options={
                "ordering": ("-occurred_at", "-pk"),
                "indexes": [models.Index(fields=["geofence", "-occurred_at"], name="geofence_event_time_idx"), models.Index(fields=["vehicle", "-occurred_at"], name="geo_event_vehicle_idx")],
                "constraints": [models.UniqueConstraint(fields=("geofence", "vehicle", "telemetry_event", "event_type"), name="unique_geofence_transition")],
            },
        ),
    ]
