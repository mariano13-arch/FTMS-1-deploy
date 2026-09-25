from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from fleet.management.commands.seed_professional_drivers import CODE_PREFIX, PROFILE_COUNT
from fleet.models import Driver, DriverSafetyDemoEvent, DriverSafetyDemoProfile

SOURCE = DriverSafetyDemoProfile.Source.DEMO_SEED
EVENT_TYPES = tuple(DriverSafetyDemoEvent.EventType.values)
EVENTS_PER_DRIVER = 40
GENERATED_AT = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
MOBILE_TEST_DRIVER_CODE = "DEV-MOBILE-TEST-111"
MOBILE_TEST_VALUES = (88, 132, Decimal("176.5"), EVENTS_PER_DRIVER)
MOBILE_TEST_EVENT_TYPES = (
    (DriverSafetyDemoEvent.EventType.HARSH_ACCELERATION,) * 13
    + (DriverSafetyDemoEvent.EventType.HARSH_BRAKING,) * 13
    + (DriverSafetyDemoEvent.EventType.SHARP_TURN,) * 14
)


def demo_values(index):
    # Exact deterministic bands: 35 high, 70 strong, 35 developing, 10 coaching.
    if index < 35:
        score = 90 + index % 9
    elif index < 105:
        score = 80 + (index - 35) % 10
    elif index < 140:
        score = 70 + (index - 105) % 10
    else:
        score = 60 + (index - 140) % 10
    if score >= 90:
        completed = 140 + (index * 17) % 101
        hours = Decimal(2000 + (index * 37) % 1801) / Decimal(10)
    elif score >= 80:
        completed = 100 + (index * 13) % 91
        hours = Decimal(1200 + (index * 31) % 1401) / Decimal(10)
    elif score >= 70:
        completed = 65 + (index * 11) % 76
        hours = Decimal(650 + (index * 29) % 1051) / Decimal(10)
    else:
        completed = 40 + (index * 7) % 61
        hours = Decimal(350 + (index * 23) % 751) / Decimal(10)
    return score, completed, hours, EVENTS_PER_DRIVER


def target_drivers():
    expected = {f"{CODE_PREFIX}{number:04d}" for number in range(1, PROFILE_COUNT + 1)}
    drivers = list(Driver.objects.filter(driver_code__in=expected).order_by("driver_code"))
    found = {driver.driver_code for driver in drivers}
    if found != expected:
        missing = sorted(expected - found)
        raise CommandError(
            f"Verified professional cohort is incomplete ({len(drivers)}/{PROFILE_COUNT}); "
            f"missing: {', '.join(missing[:5])}."
        )
    return drivers


class Command(BaseCommand):
    help = "Seed deterministic presentation-only safety profiles for professional drivers."

    @transaction.atomic
    def handle(self, *args, **options):
        drivers = target_drivers()
        total_events = 0
        for index, driver in enumerate(drivers):
            score, trips, hours, event_count = demo_values(index)
            profile, _ = DriverSafetyDemoProfile.objects.update_or_create(
                driver=driver,
                defaults={
                    "safety_score": score,
                    "completed_trip_count": trips,
                    "driving_hours": hours,
                    "safety_event_count": event_count,
                    "source": SOURCE,
                    "generated_at": GENERATED_AT,
                },
            )
            profile.events.exclude(sequence__lt=EVENTS_PER_DRIVER).delete()
            for sequence in range(event_count):
                DriverSafetyDemoEvent.objects.update_or_create(
                    profile=profile,
                    sequence=sequence,
                    defaults={
                        "event_type": EVENT_TYPES[
                            (index * 2 + sequence + sequence // (2 + index % 3))
                            % len(EVENT_TYPES)
                        ],
                        "occurred_at": GENERATED_AT
                        - timedelta(days=1 + (index * 3 + sequence * 7) % 90, hours=(index + sequence * 5) % 24),
                        "source": SOURCE,
                    },
                )
            total_events += event_count

        mobile_driver = Driver.objects.filter(driver_code=MOBILE_TEST_DRIVER_CODE).first()
        if mobile_driver is None:
            raise CommandError(f"Targeted demo driver {MOBILE_TEST_DRIVER_CODE} does not exist.")
        score, trips, hours, event_count = MOBILE_TEST_VALUES
        mobile_profile, _ = DriverSafetyDemoProfile.objects.update_or_create(
            driver=mobile_driver,
            defaults={
                "safety_score": score,
                "completed_trip_count": trips,
                "driving_hours": hours,
                "safety_event_count": event_count,
                "source": SOURCE,
                "generated_at": GENERATED_AT,
            },
        )
        mobile_profile.events.exclude(sequence__lt=EVENTS_PER_DRIVER).delete()
        for sequence, event_type in enumerate(MOBILE_TEST_EVENT_TYPES):
            DriverSafetyDemoEvent.objects.update_or_create(
                profile=mobile_profile,
                sequence=sequence,
                defaults={
                    "event_type": event_type,
                    "occurred_at": GENERATED_AT
                    - timedelta(days=1 + (sequence * 7) % 90, hours=(sequence * 5) % 24),
                    "source": SOURCE,
                },
            )
        total_events += event_count

        self.stdout.write(self.style.SUCCESS(f"Demo safety profiles: {len(drivers) + 1}"))
        self.stdout.write(f"Demo safety events: {total_events}")
        self.stdout.write("Drivers skipped: 0")
        self.stdout.write("Real safety records modified: 0")
