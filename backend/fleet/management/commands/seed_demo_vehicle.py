from django.core.management.base import BaseCommand

from fleet.models import Vehicle


class Command(BaseCommand):
    help = "Create or reconcile the deterministic simulated pilot vehicle."

    def handle(self, *args, **options):
        vehicle, created = Vehicle.objects.update_or_create(
            device_id="LILYGO-001",
            defaults={
                "plate_number": "DEMO-001",
                "display_name": "Sprint 1 Demo Vehicle",
                "is_active": True,
            },
        )
        action = "Created" if created else "Updated"
        message = f"{action} {vehicle.device_id} / {vehicle.plate_number}"
        self.stdout.write(self.style.SUCCESS(message))
