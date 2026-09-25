from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from fleet.management.commands.seed_vehicle_registry import (
    OXFORD_LATITUDE,
    OXFORD_LONGITUDE,
    POSITION_PREFIX,
)
from fleet.models import Vehicle
from telemetry.models import TelemetryDeviceBinding, TelemetryEvent


class Command(BaseCommand):
    help = "Refresh only professional seeded fleet positions at Oxford Suites Makati."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Simulated position refresh is restricted to DEBUG environments.")
        vehicles = Vehicle.objects.filter(device_id__regex=r"^FT-(GT|ST)-[0-9]{3}$").order_by(
            "device_id"
        )
        if vehicles.count() != 80:
            raise CommandError("Expected exactly 80 professional seeded vehicles.")
        now = timezone.now()
        for index, vehicle in enumerate(vehicles, start=1):
            binding = TelemetryDeviceBinding.objects.select_related("device").get(
                vehicle=vehicle, unpaired_at__isnull=True
            )
            TelemetryEvent.objects.update_or_create(
                event_id=f"{POSITION_PREFIX}{vehicle.device_id}",
                defaults={
                    "schema_version": "1.2",
                    "sequence_number": index,
                    "device": binding.device,
                    "vehicle": vehicle,
                    "recorded_at": now,
                    "location": Point(OXFORD_LONGITUDE, OXFORD_LATITUDE, srid=4326),
                    "position_source": TelemetryEvent.PositionSource.SIMULATED_TEST,
                    "gnss_speed_kph": None,
                    "position_accuracy_m": None,
                    "obd_source": None,
                    "driving_event": None,
                },
            )
        self.stdout.write(self.style.SUCCESS("Refreshed 80 simulated fleet positions."))
