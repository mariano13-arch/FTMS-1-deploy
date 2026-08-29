from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from fleet.models import Vehicle
from ml.demo_fuel import (
    DEMO_DEVICE_ID,
    DEMO_DISPLAY_NAME,
    DEMO_HISTORY_LIMIT,
    DEMO_PLATE_NUMBER,
    DEMO_SOURCE_MODE,
    run_demo_inference,
)
from ml.models import FuelPrediction
from telemetry.models import TelemetryEvent


class Command(BaseCommand):
    help = "Seed or clear explicitly labeled DEMO-001 fuel-model verification records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete only DEMO-001 FuelPrediction rows with source_mode=demo_seed.",
        )

    def resolve_demo_vehicle(self):
        vehicle = Vehicle.objects.filter(device_id=DEMO_DEVICE_ID).first()
        if vehicle is None:
            vehicle = Vehicle.objects.filter(
                plate_number__iexact=DEMO_PLATE_NUMBER
            ).first()
        if vehicle is None:
            raise CommandError(
                "Sprint 1 Demo Vehicle was not found by device_id=LILYGO-001 or "
                "plate_number=DEMO-001. No vehicle was created."
            )
        if DEMO_DISPLAY_NAME.lower() not in vehicle.display_name.lower():
            raise CommandError(
                f"Resolved vehicle {vehicle.device_id} / {vehicle.plate_number}, but its "
                f"display name is not '{DEMO_DISPLAY_NAME}'. Refusing to seed it."
            )
        return vehicle

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_fuel_demo is development-only and requires settings.DEBUG=True."
            )

        vehicle = self.resolve_demo_vehicle()

        if options["clear"]:
            demo_predictions = FuelPrediction.objects.filter(
                vehicle=vehicle,
                source_mode=DEMO_SOURCE_MODE,
            )
            count = demo_predictions.count()
            self.stdout.write(
                f"Removing {count} DEMO/TEST/RESEARCH fuel prediction record(s) "
                "for DEMO-001 only; telemetry and other records will not be changed."
            )
            demo_predictions.delete()
            self.stdout.write(self.style.SUCCESS("Demo fuel predictions cleared."))
            return

        events = list(
            TelemetryEvent.objects.filter(vehicle=vehicle, rpm__isnull=False)
            .order_by("-recorded_at", "-sequence_number", "-received_at", "-pk")[
                :DEMO_HISTORY_LIMIT
            ]
        )
        if not events:
            self.stdout.write(
                self.style.WARNING(
                    "No persisted DEMO-001 telemetry with usable speed and RPM was found; "
                    "nothing was seeded."
                )
            )
            return

        created_count = 0
        skipped_count = 0
        with transaction.atomic():
            for event in reversed(events):
                result = run_demo_inference(event)
                if result["status"] != "prediction_available":
                    raise CommandError(
                        f"Fuel inference failed for telemetry event {event.event_id}: "
                        f"{result['status']}."
                    )
                _, created = FuelPrediction.objects.get_or_create(
                    vehicle=vehicle,
                    input_timestamp=event.recorded_at,
                    model_version=result["model_version"],
                    defaults={
                        "estimated_fuel_lph": result["estimated_fuel_lph"],
                        "model_name": result["model_name"],
                        "source_mode": DEMO_SOURCE_MODE,
                        "validated_inputs": result["inputs"],
                    },
                )
                created_count += int(created)
                skipped_count += int(not created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created_count} DEMO/TEST/RESEARCH fuel prediction(s) for "
                f"DEMO-001; skipped {skipped_count} existing prediction(s)."
            )
        )
        self.stdout.write(
            "Speed/RPM came from persisted telemetry; all other model inputs came from "
            "CONTROLLED_DEMO_INPUTS and are not operational telemetry."
        )
