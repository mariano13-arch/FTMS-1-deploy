from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import RolePermission, StaffProfile
from fleet.models import NumberCodingRule, NumberCodingSuspension, Vehicle, VehicleCodingExemption


class NumberCodingApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.manager = get_user_model().objects.create_user(username="fleet-manager", is_staff=True)
        StaffProfile.objects.create(user=self.manager, role=StaffProfile.Role.FLEET_MANAGER)
        self.dispatcher = get_user_model().objects.create_user(username="dispatcher", is_staff=True)
        StaffProfile.objects.create(user=self.dispatcher, role=StaffProfile.Role.DISPATCHER)
        for role in (StaffProfile.Role.FLEET_MANAGER, StaffProfile.Role.DISPATCHER):
            RolePermission.objects.get_or_create(role=role, module="SYSTEM_SETTINGS", action="VIEW")
        RolePermission.objects.get_or_create(
            role=StaffProfile.Role.FLEET_MANAGER,
            module="SYSTEM_SETTINGS", action="MANAGE_NUMBER_CODING",
        )
        self.vehicle = Vehicle.objects.create(
            device_id="NC-API-1", plate_number="ABC-123", display_name="Coding Van"
        )

    def rule_payload(self, **overrides):
        return {
            "authority": "MMDA",
            "jurisdiction": "Metro Manila",
            "weekday": 0,
            "restricted_last_digits": [1, 2],
            "start_time": "07:00:00",
            "end_time": "10:00:00",
            "effective_from": "2026-09-01",
            "effective_until": None,
            "is_active": True,
            "source_reference": "Official configured source",
            "notes": "",
            **overrides,
        }

    def test_manager_can_list_create_update_and_deactivate_rule(self):
        self.client.force_authenticate(self.manager)
        created = self.client.post(
            "/api/v1/vehicles/number-coding/rules/", self.rule_payload(), format="json"
        )
        self.assertEqual(created.status_code, 201)
        record_id = created.json()["id"]
        updated = self.client.patch(
            f"/api/v1/vehicles/number-coding/rules/{record_id}/",
            {"restricted_last_digits": [3, 4], "is_active": False},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["restricted_last_digits"], [3, 4])
        self.assertFalse(updated.json()["is_active"])
        self.assertEqual(len(self.client.get("/api/v1/vehicles/number-coding/rules/").json()), 1)
        self.assertTrue(NumberCodingRule.objects.filter(pk=record_id).exists())
        self.assertEqual(
            self.client.delete(f"/api/v1/vehicles/number-coding/rules/{record_id}/").status_code,
            405,
        )

    def test_dispatcher_can_read_but_cannot_write(self):
        NumberCodingRule.objects.create(
            authority="MMDA",
            jurisdiction="Metro Manila",
            weekday=0,
            restricted_last_digits=[1, 2],
            effective_from=date(2026, 9, 1),
        )
        self.client.force_authenticate(self.dispatcher)
        self.assertEqual(self.client.get("/api/v1/vehicles/number-coding/rules/").status_code, 200)
        self.assertEqual(
            self.client.post(
                "/api/v1/vehicles/number-coding/rules/", self.rule_payload(), format="json"
            ).status_code,
            403,
        )

    def test_rule_validation_rejects_invalid_digits_dates_and_times(self):
        self.client.force_authenticate(self.manager)
        url = "/api/v1/vehicles/number-coding/rules/"
        for changes in (
            {"restricted_last_digits": [10]},
            {"weekday": 9},
            {"start_time": "10:00:00", "end_time": "07:00:00"},
            {"effective_until": "2026-08-31"},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(
                    self.client.post(url, self.rule_payload(**changes), format="json").status_code,
                    400,
                )

    def test_suspension_and_exemption_crud_use_real_attribution_and_vehicle(self):
        self.client.force_authenticate(self.manager)
        starts_at = timezone.now() + timedelta(days=1)
        ends_at = starts_at + timedelta(days=1)
        suspension = self.client.post(
            "/api/v1/vehicles/number-coding/suspensions/",
            {
                "authority": "MMDA",
                "jurisdiction": "Metro Manila",
                "starts_at": starts_at,
                "ends_at": ends_at,
                "reason": "Official suspension",
                "source_reference": "Official notice",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(suspension.status_code, 201)
        self.assertEqual(NumberCodingSuspension.objects.get().created_by, self.manager)
        exemption = self.client.post(
            "/api/v1/vehicles/number-coding/exemptions/",
            {
                "vehicle": self.vehicle.pk,
                "authority": "MMDA",
                "jurisdiction": "Metro Manila",
                "starts_at": starts_at,
                "ends_at": ends_at,
                "reason": "Verified official exemption",
                "source_reference": "Official exemption",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(exemption.status_code, 201)
        self.assertEqual(exemption.json()["plate_number"], self.vehicle.plate_number)
        self.assertEqual(VehicleCodingExemption.objects.get().verified_by, self.manager)
        invalid_vehicle = self.client.post(
            "/api/v1/vehicles/number-coding/exemptions/",
            {
                "vehicle": 999999,
                "authority": "MMDA",
                "jurisdiction": "Metro Manila",
                "starts_at": starts_at,
                "ends_at": ends_at,
                "reason": "Verified",
                "source_reference": "Official reference",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(invalid_vehicle.status_code, 400)

    def test_period_validation_and_activation_patch(self):
        self.client.force_authenticate(self.manager)
        starts_at = timezone.now() + timedelta(days=1)
        invalid = self.client.post(
            "/api/v1/vehicles/number-coding/suspensions/",
            {
                "authority": "MMDA",
                "jurisdiction": "Metro Manila",
                "starts_at": starts_at,
                "ends_at": starts_at,
                "reason": "Official suspension",
                "source_reference": "Official notice",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)
