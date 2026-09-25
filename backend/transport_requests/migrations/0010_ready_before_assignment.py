from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("transport_requests", "0009_canonical_transport_context")]

    operations = [
        migrations.RemoveConstraint(
            model_name="transportrequest",
            name="tr_ready_requires_vehicle",
        ),
    ]
