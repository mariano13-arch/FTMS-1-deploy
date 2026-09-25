from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase

from fleet.models import (
    NumberCodingRule,
    NumberCodingSuspension,
    Vehicle,
    VehicleCodingExemption,
)
from fleet.number_coding import evaluate_vehicle_number_coding


class NumberCodingEvaluationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="coding-admin")
        self.vehicle = Vehicle.objects.create(
            device_id="CODING-001", plate_number="ABC-123", display_name="Coding Van"
        )
        self.pickup = datetime(2026, 9, 21, 8, 30, tzinfo=ZoneInfo("Asia/Manila"))
        self.rule = NumberCodingRule.objects.create(
            authority="MMDA",
            jurisdiction="Metro Manila",
            weekday=NumberCodingRule.Weekday.MONDAY,
            restricted_last_digits=[1, 2, 3],
            start_time=time(7),
            end_time=time(10),
            effective_from=date(2026, 1, 1),
            source_reference="Official configured source",
        )

    def test_rule_uses_scheduled_pickup_in_manila_and_final_numeric_digit(self):
        utc_pickup = self.pickup.astimezone(dt_timezone.utc)

        result = evaluate_vehicle_number_coding(self.vehicle, utc_pickup)

        self.assertEqual(result.status, "RESTRICTED")
        self.assertEqual(result.plate_last_digit, 3)
        self.assertFalse(result.eligible)

    def test_no_matching_rule_is_clear_and_unparseable_plate_is_unknown(self):
        self.assertEqual(
            evaluate_vehicle_number_coding(self.vehicle, self.pickup + timedelta(hours=3)).status,
            "CLEAR",
        )
        self.vehicle.plate_number = "NO-DIGITS"
        self.assertEqual(
            evaluate_vehicle_number_coding(self.vehicle, self.pickup).status,
            "UNKNOWN",
        )

    def test_suspension_precedes_verified_exemption(self):
        VehicleCodingExemption.objects.create(
            vehicle=self.vehicle,
            authority=self.rule.authority,
            jurisdiction=self.rule.jurisdiction,
            starts_at=self.pickup - timedelta(hours=1),
            ends_at=self.pickup + timedelta(hours=1),
            reason="Verified official exemption",
            source_reference="Official exemption record",
            verified_by=self.user,
        )
        NumberCodingSuspension.objects.create(
            authority=self.rule.authority,
            jurisdiction=self.rule.jurisdiction,
            starts_at=self.pickup - timedelta(hours=1),
            ends_at=self.pickup + timedelta(hours=1),
            reason="Official temporary suspension",
            source_reference="Official suspension notice",
            created_by=self.user,
        )

        result = evaluate_vehicle_number_coding(self.vehicle, self.pickup)

        self.assertEqual(result.status, "SUSPENDED")
        self.assertTrue(result.eligible)

    def test_verified_exemption_is_eligible_without_suspension(self):
        VehicleCodingExemption.objects.create(
            vehicle=self.vehicle,
            authority=self.rule.authority,
            jurisdiction=self.rule.jurisdiction,
            starts_at=self.pickup - timedelta(hours=1),
            ends_at=self.pickup + timedelta(hours=1),
            reason="Verified official exemption",
            source_reference="Official exemption record",
            verified_by=self.user,
        )

        self.assertEqual(
            evaluate_vehicle_number_coding(self.vehicle, self.pickup).status,
            "EXEMPT",
        )

    @patch("fleet.number_coding.timezone.now")
    def test_current_time_does_not_affect_evaluation(self, now_mock):
        now_mock.return_value = self.pickup + timedelta(days=1)
        self.assertEqual(
            evaluate_vehicle_number_coding(self.vehicle, self.pickup).status,
            "RESTRICTED",
        )
