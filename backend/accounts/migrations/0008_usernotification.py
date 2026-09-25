import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_permission_matrix_p2a"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserNotification",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "notification_type",
                    models.CharField(
                        choices=[
                            ("TRANSPORT_READY", "Transport request ready"),
                            ("DISPATCH_CONFIRMED", "Dispatch confirmed"),
                            ("DRIVER_ACCEPTED", "Driver accepted"),
                            ("SOS_ACTIVE", "SOS active"),
                            ("INSPECTION_ATTENTION", "Inspection attention"),
                            ("MAINTENANCE_COMPLETED", "Maintenance completed"),
                        ],
                        max_length=32,
                    ),
                ),
                ("title", models.CharField(max_length=160)),
                ("message", models.CharField(max_length=500)),
                ("target_url", models.CharField(max_length=300)),
                ("source_key", models.CharField(max_length=180)),
                ("is_read", models.BooleanField(default=False)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "recipient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ftms_notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("-created_at", "-pk")},
        ),
        migrations.AddConstraint(
            model_name="usernotification",
            constraint=models.UniqueConstraint(
                fields=("recipient", "source_key"),
                name="accounts_unique_notification_source_per_recipient",
            ),
        ),
        migrations.AddIndex(
            model_name="usernotification",
            index=models.Index(
                fields=["recipient", "is_read", "created_at"], name="accounts_notif_inbox_idx"
            ),
        ),
    ]
