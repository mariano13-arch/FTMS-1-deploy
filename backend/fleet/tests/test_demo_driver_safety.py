from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Count
from django.test import TestCase
from django.utils import timezone

from fleet.management.commands.seed_demo_driver_safety import (
    EVENTS_PER_DRIVER,
    MOBILE_TEST_DRIVER_CODE,
    MOBILE_TEST_VALUES,
    demo_values,
)
from fleet.management.commands.seed_professional_drivers import CODE_PREFIX, PROFILE_COUNT
from fleet.models import Driver, DriverSafetyDemoEvent, DriverSafetyDemoProfile
from fleet.serializers import DriverSerializer
from fleet.safety import safety_calibration_summary
from telemetry.models import DriverSafetyEvent


class DemoDriverSafetySeedTests(TestCase):
    def setUp(self):
        self.aljohn = Driver.objects.create(
            driver_code="123-GFD", first_name="ALJOHN", middle_name="ANDAMON", last_name="MARIANO"
        )
        self.mobile = Driver.objects.create(
            driver_code="DEV-MOBILE-TEST-111", first_name="ALJOHN", middle_name="A.", last_name="MARIANO"
        )
        Driver.objects.bulk_create([
            Driver(driver_code=f"{CODE_PREFIX}{number:04d}", first_name="Driver", last_name=str(number))
            for number in range(1, PROFILE_COUNT + 1)
        ])

    def seed(self):
        output = StringIO()
        call_command("seed_demo_driver_safety", stdout=output)
        return output.getvalue()

    def test_requires_the_complete_verified_cohort(self):
        Driver.objects.get(driver_code=f"{CODE_PREFIX}0150").delete()
        with self.assertRaises(CommandError):
            self.seed()

    def test_targets_exact_cohort_plus_mobile_driver_and_preserves_other_aljohn_row(self):
        self.seed()
        self.assertEqual(DriverSafetyDemoProfile.objects.count(), PROFILE_COUNT + 1)
        self.assertFalse(DriverSafetyDemoProfile.objects.filter(driver=self.aljohn).exists())
        profile = DriverSafetyDemoProfile.objects.get(driver=self.mobile)
        self.assertEqual(
            (profile.safety_score, profile.completed_trip_count, profile.driving_hours, profile.safety_event_count),
            MOBILE_TEST_VALUES,
        )
        self.assertEqual(profile.events.count(), EVENTS_PER_DRIVER)

    def test_rerun_is_deterministic_and_idempotent(self):
        first_output = self.seed()
        first = list(DriverSafetyDemoProfile.objects.order_by("driver__driver_code").values_list(
            "safety_score", "completed_trip_count", "driving_hours", "safety_event_count"
        ))
        event_ids = list(DriverSafetyDemoEvent.objects.order_by("profile_id", "sequence").values_list("profile_id", "sequence"))
        second_output = self.seed()
        self.assertEqual(first, list(DriverSafetyDemoProfile.objects.order_by("driver__driver_code").values_list(
            "safety_score", "completed_trip_count", "driving_hours", "safety_event_count"
        )))
        self.assertEqual(event_ids, list(DriverSafetyDemoEvent.objects.order_by("profile_id", "sequence").values_list("profile_id", "sequence")))
        self.assertIn("Demo safety profiles: 151", first_output)
        self.assertIn("Demo safety events: 6040", first_output)
        self.assertEqual(DriverSafetyDemoEvent.objects.count(), 6040)
        self.assertEqual(self.mobile.safety_demo_profile.events.count(), EVENTS_PER_DRIVER)
        self.assertIn("Real safety records modified: 0", second_output)

    def test_distribution_ranges_events_and_timestamps(self):
        self.seed()
        cohort = DriverSafetyDemoProfile.objects.filter(driver__driver_code__startswith=CODE_PREFIX)
        scores = list(cohort.values_list("safety_score", flat=True))
        self.assertEqual(sum(90 <= score <= 98 for score in scores), 35)
        self.assertEqual(sum(80 <= score <= 89 for score in scores), 70)
        self.assertEqual(sum(70 <= score <= 79 for score in scores), 35)
        self.assertEqual(sum(60 <= score <= 69 for score in scores), 10)
        self.assertTrue(all(0 <= score <= 100 for score in scores))
        self.assertFalse(DriverSafetyDemoProfile.objects.exclude(safety_event_count=EVENTS_PER_DRIVER).exists())
        self.assertEqual(DriverSafetyDemoEvent.objects.count(), (PROFILE_COUNT + 1) * EVENTS_PER_DRIVER)
        self.assertFalse(
            DriverSafetyDemoProfile.objects.annotate(actual_events=Count("events"))
            .exclude(actual_events=EVENTS_PER_DRIVER)
            .exists()
        )
        self.assertFalse(DriverSafetyDemoEvent.objects.filter(occurred_at__gt=timezone.now()).exists())
        self.assertFalse(DriverSafetyDemoEvent.objects.exclude(event_type__in=DriverSafetyDemoEvent.EventType.values).exists())
        histories = [
            tuple(DriverSafetyDemoEvent.objects.filter(profile__driver__driver_code=f"{CODE_PREFIX}{number:04d}").order_by("sequence").values_list("event_type", flat=True))
            for number in (1, 2, 3)
        ]
        self.assertEqual(len(set(histories)), 3)
        mobile_events = DriverSafetyDemoEvent.objects.filter(profile__driver=self.mobile)
        self.assertEqual(
            dict(mobile_events.values_list("event_type").annotate(count=Count("id"))),
            {"HARSH_ACCELERATION": 13, "HARSH_BRAKING": 13, "SHARP_TURN": 14},
        )
        high = DriverSafetyDemoProfile.objects.filter(safety_score__gte=90).order_by("driver__driver_code").first()
        low = DriverSafetyDemoProfile.objects.filter(safety_score__lt=70).order_by("driver__driver_code").first()
        self.assertGreater(float(high.driving_hours), float(low.driving_hours))
        self.assertLess(high.safety_event_count / float(high.driving_hours), low.safety_event_count / float(low.driving_hours))

    def test_demo_records_do_not_enter_real_calibration_or_real_history(self):
        self.seed()
        driver_ids = list(DriverSafetyDemoProfile.objects.values_list("driver_id", flat=True))
        summary = safety_calibration_summary(driver_ids)
        self.assertEqual(summary["exposure_eligible_drivers"], 0)
        self.assertEqual(DriverSafetyEvent.objects.count(), 0)

    def test_driver_api_shape_exposes_labeled_demo_values(self):
        self.seed()
        driver = Driver.objects.get(driver_code=f"{CODE_PREFIX}0001")
        data = DriverSerializer(driver).data
        expected = demo_values(0)
        self.assertEqual(data["safety_score"], expected[0])
        self.assertEqual(data["safety_score_source"], "DEMO_SEED")
        self.assertEqual(data["safety_completed_trips"], expected[1])
        self.assertEqual(len(data["safety_history"]), expected[3])
        occurred = [item["occurred_at"] for item in data["safety_history"]]
        self.assertEqual(occurred, sorted(occurred, reverse=True))
        self.assertTrue(all(item["event_label"] in {"Harsh Acceleration", "Harsh Braking", "Sharp Turn"} for item in data["safety_history"]))

        mobile_data = DriverSerializer(self.mobile).data
        self.assertEqual(mobile_data["safety_score"], MOBILE_TEST_VALUES[0])
        self.assertEqual(mobile_data["safety_score_source"], "DEMO_SEED")
        self.assertEqual(len(mobile_data["safety_history"]), EVENTS_PER_DRIVER)

    def test_real_event_presence_does_not_suppress_demo_score_and_history(self):
        self.seed()
        driver = Driver.objects.get(driver_code=f"{CODE_PREFIX}0001")
        with patch.object(driver.safety_events, "exists", return_value=True):
            data = DriverSerializer(driver).data
        self.assertEqual(data["safety_score"], demo_values(0)[0])
        self.assertEqual(data["safety_score_status"], "DEMO_SCORED")
        self.assertEqual(data["safety_score_source"], "DEMO_SEED")
        self.assertEqual(len(data["safety_history"]), EVENTS_PER_DRIVER)

    def test_real_numeric_score_takes_precedence_over_demo_profile(self):
        self.seed()
        driver = Driver.objects.get(driver_code=MOBILE_TEST_DRIVER_CODE)
        data = DriverSerializer(driver, context={"real_safety_scores": {driver.pk: 96}}).data
        self.assertEqual(data["safety_score"], 96)
        self.assertEqual(data["safety_score_status"], "REAL_SCORED")
        self.assertEqual(data["safety_score_source"], "REAL")
        self.assertEqual(data["safety_history"], [])
