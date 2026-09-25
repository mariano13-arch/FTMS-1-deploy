from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import RolePermission, StaffProfile
from fleet.models import FuelPriceRecord


class PartnerFuelPriceSettingsTests(TestCase):
    url = "/api/v1/vehicles/partner-fuel-prices/"

    def user(self, username, role, *, superuser=False):
        user = get_user_model().objects.create_user(
            username=username, is_staff=True, is_superuser=superuser
        )
        if superuser:
            StaffProfile.objects.create(user=user, role=StaffProfile.Role.FLEET_ADMIN)
        else:
            StaffProfile.objects.create(user=user, role=role)
            RolePermission.objects.get_or_create(
                role=role, module="SYSTEM_SETTINGS", action="VIEW"
            )
            if role == StaffProfile.Role.FLEET_MANAGER:
                RolePermission.objects.get_or_create(
                    role=role, module="SYSTEM_SETTINGS", action="MANAGE_PRICES"
                )
        return user

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def payload(self, grade="UNLEADED_91", price="71.2500", *, hours=1):
        return {
            "fuel_grade": grade,
            "price_per_liter": price,
            "effective_at": (timezone.now() - timedelta(hours=hours)).isoformat(),
        }

    def test_staff_can_read_exact_supported_products_and_unconfigured_values(self):
        client = self.client_for(
            self.user("dispatcher", StaffProfile.Role.DISPATCHER)
        )
        response = client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["provider"], "ShellPH")
        self.assertEqual(
            [item["fuel_grade"] for item in response.data["products"]],
            [
                "UNLEADED_91",
                "PREMIUM_95",
                "PREMIUM_97",
                "REGULAR_DIESEL",
                "PREMIUM_DIESEL",
            ],
        )
        self.assertTrue(
            all(item["current_price"] is None for item in response.data["products"])
        )

    def test_dispatcher_cannot_modify_but_fleet_manager_can_record_each_grade(self):
        dispatcher = self.client_for(
            self.user("dispatcher", StaffProfile.Role.DISPATCHER)
        )
        self.assertEqual(dispatcher.post(self.url, self.payload(), format="json").status_code, 403)

        manager = self.client_for(
            self.user("manager", StaffProfile.Role.FLEET_MANAGER)
        )
        grades = (
            "UNLEADED_91",
            "PREMIUM_95",
            "PREMIUM_97",
            "REGULAR_DIESEL",
            "PREMIUM_DIESEL",
        )
        for grade in grades:
            with self.subTest(grade=grade):
                response = manager.post(self.url, self.payload(grade), format="json")
                self.assertEqual(response.status_code, 201)
                self.assertEqual(response.data["provider"], "ShellPH")
                self.assertEqual(response.data["currency"], "PHP")
                self.assertEqual(response.data["fuel_grade"], grade)

    def test_invalid_grade_price_and_future_time_are_rejected(self):
        client = self.client_for(
            self.user("manager", StaffProfile.Role.FLEET_MANAGER)
        )
        invalid = (
            {**self.payload(), "fuel_grade": ""},
            self.payload(price="0"),
            self.payload(price="-1"),
            self.payload(price="bad"),
            self.payload(hours=-1),
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertEqual(client.post(self.url, payload, format="json").status_code, 400)
        self.assertEqual(FuelPriceRecord.objects.count(), 0)

    def test_new_price_preserves_history_and_latest_effective_is_current(self):
        client = self.client_for(
            self.user("manager", StaffProfile.Role.FLEET_MANAGER)
        )
        first = client.post(
            self.url, self.payload(price="70.0000", hours=2), format="json"
        )
        second = client.post(
            self.url, self.payload(price="72.0000", hours=1), format="json"
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        response = client.get(self.url)
        product = response.data["products"][0]
        self.assertEqual(product["current_price"]["price_per_liter"], "72.0000")
        self.assertEqual(len(product["history"]), 2)
        self.assertEqual(FuelPriceRecord.objects.count(), 2)

    def test_public_market_records_never_become_shell_prices(self):
        for provider in ("GasWatchPH", "GlobalPetrolPrices"):
            FuelPriceRecord.objects.create(
                fuel_type="GASOLINE",
                fuel_grade="UNLEADED_91",
                price_per_liter=Decimal("60"),
                currency="PHP",
                effective_at=timezone.now() - timedelta(hours=1),
                provider=provider,
                source_mode="EXTERNAL_CACHED",
            )
        client = self.client_for(
            self.user("dispatcher", StaffProfile.Role.DISPATCHER)
        )
        response = client.get(self.url)
        self.assertIsNone(response.data["products"][0]["current_price"])
