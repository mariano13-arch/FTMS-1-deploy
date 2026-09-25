from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_staffloginsecuritystate"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("occurred_at", models.DateTimeField(auto_now_add=True)),
                ("actor_type", models.CharField(choices=[("STAFF", "Staff"), ("DRIVER", "Driver"), ("SYSTEM", "System"), ("DEVICE", "Device"), ("UNKNOWN", "Unknown")], default="UNKNOWN", max_length=12)),
                ("action", models.CharField(max_length=64)),
                ("target_type", models.CharField(blank=True, default="", max_length=80)),
                ("target_id", models.CharField(blank=True, default="", max_length=80)),
                ("target_label", models.CharField(blank=True, default="", max_length=180)),
                ("outcome", models.CharField(choices=[("SUCCESS", "Success"), ("FAILURE", "Failure"), ("DENIED", "Denied")], default="SUCCESS", max_length=12)),
                ("source", models.CharField(choices=[("WEB", "Web"), ("MOBILE", "Mobile"), ("API", "API"), ("SYSTEM", "System")], default="WEB", max_length=12)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, default="", max_length=240)),
                ("changes", models.JSONField(blank=True, default=dict)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="audit_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-occurred_at", "-pk"),
            },
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["-occurred_at"], name="audit_event_time_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["actor", "-occurred_at"], name="audit_event_actor_time_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["action", "-occurred_at"], name="audit_event_action_time_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["target_type", "target_id"], name="audit_event_target_idx"),
        ),
    ]
