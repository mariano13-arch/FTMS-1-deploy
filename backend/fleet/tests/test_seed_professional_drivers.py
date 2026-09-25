from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from fleet.management.commands.seed_professional_drivers import (
    CODE_PREFIX,
    MOBILE_ACCESS_DRIVER_CODE,
    PROFILE_COUNT,
    _rest_days,
)
from fleet.models import Driver
from fleet.schedules import WEEKDAYS, compact_driver_name
from fleet.serializers import driver_eligibility
from transport_requests.models import DispatchAssignment


class ProfessionalDriverSeedTests(TestCase):
    def setUp(self):
        self.aljohn_user = get_user_model().objects.create_user(
            username="aljohn-preserved",
            email="aljohn@example.com",
        )
        self.aljohn = Driver.objects.create(
            driver_code="123-GFD",
            first_name="ALJOHN",
            middle_name="ANDAMON",
            last_name="MARIANO",
            linked_user=self.aljohn_user,
        )
        self.mobile_user = get_user_model().objects.create_user(
            username=MOBILE_ACCESS_DRIVER_CODE,
            email="mobile-driver@example.com",
            password="preserved-password",
        )
        today = timezone.localdate()
        self.mobile_driver = Driver.objects.create(
            driver_code=MOBILE_ACCESS_DRIVER_CODE,
            external_hr_id="12139921",
            first_name="ALJOHN",
            middle_name="ANDAMON",
            last_name="MARIANO",
            linked_user=self.mobile_user,
            employment_status=Driver.EmploymentStatus.TERMINATED,
            license_number="32312-23123-23",
            license_expiry_date=today.replace(year=today.year + 2),
            medical_certificate_expiry_date=today.replace(year=today.year + 1),
        )
        self.legacy_account = get_user_model().objects.create_user(username="legacy-driver")
        self.referenced_legacy = Driver.objects.create(
            driver_code="OLD-DRV-001",
            first_name="Legacy",
            last_name="Operator",
            linked_user=self.legacy_account,
        )
        self.unreferenced_legacy = Driver.objects.create(
            driver_code="OLD-DRV-002",
            first_name="Old",
            last_name="Record",
        )

    def run_seed(self, *args):
        output = StringIO()
        call_command("seed_professional_drivers", *args, stdout=output)
        return output.getvalue()

    def test_dry_run_reports_plan_without_mutating_rows(self):
        original_ids = list(Driver.objects.order_by("pk").values_list("pk", flat=True))

        output = self.run_seed("--replace-development-drivers", "--dry-run")

        self.assertEqual(
            list(Driver.objects.order_by("pk").values_list("pk", flat=True)),
            original_ids,
        )
        self.assertIn(f"Preserved ALJOHN row: pk={self.aljohn.pk}", output)
        self.assertIn(
            f"Protected mobile-access driver: pk={self.mobile_driver.pk}, "
            f"code={MOBILE_ACCESS_DRIVER_CODE}, linked_user={self.mobile_user.pk}",
            output,
        )
        self.assertIn(
            "Preserved ALJOHN eligibility: RESTRICTED — "
            "Driver license number is missing; Driver license expiry is missing; "
            "Medical certificate expiry is missing",
            output,
        )
        self.assertIn("Old development drivers found: 2", output)
        self.assertIn("Would delete unreferenced: OLD-DRV-002", output)
        self.assertIn("Would deactivate referenced: OLD-DRV-001", output)
        self.assertIn("Professional drivers to reconcile: 150", output)
        self.assertIn("Operational history to create: none", output)
        self.mobile_driver.refresh_from_db()
        self.assertEqual(
            self.mobile_driver.employment_status, Driver.EmploymentStatus.TERMINATED
        )

    def test_replacement_preserves_aljohn_and_builds_complete_eligible_profiles(self):
        aljohn_pk = self.aljohn.pk
        aljohn_user_id = self.aljohn.linked_user_id
        mobile_pk = self.mobile_driver.pk
        mobile_user_id = self.mobile_driver.linked_user_id
        mobile_password_hash = self.mobile_user.password

        self.run_seed("--replace-development-drivers")

        self.aljohn.refresh_from_db()
        self.assertEqual(self.aljohn.pk, aljohn_pk)
        self.assertEqual(self.aljohn.linked_user_id, aljohn_user_id)
        self.mobile_driver.refresh_from_db()
        self.mobile_user.refresh_from_db()
        self.assertEqual(self.mobile_driver.pk, mobile_pk)
        self.assertEqual(self.mobile_driver.linked_user_id, mobile_user_id)
        self.assertEqual(self.mobile_user.password, mobile_password_hash)
        self.assertTrue(self.mobile_user.is_active)
        self.assertEqual(
            self.mobile_driver.employment_status, Driver.EmploymentStatus.ACTIVE
        )
        self.assertEqual(self.mobile_driver.work_shift, Driver.WorkShift.DAY)
        self.assertEqual(self.mobile_driver.weekly_rest_days, _rest_days(PROFILE_COUNT + 1))
        self.assertEqual(len(set(self.mobile_driver.weekly_rest_days)), 2)
        self.assertEqual(driver_eligibility(self.mobile_driver), ("ELIGIBLE", []))
        self.assertNotEqual(self.mobile_driver.pk, self.aljohn.pk)
        generated = Driver.objects.filter(driver_code__startswith=CODE_PREFIX)
        self.assertEqual(generated.count(), PROFILE_COUNT)
        self.assertEqual(generated.values("driver_code").distinct().count(), PROFILE_COUNT)
        full_names = {
            compact_driver_name(item)
            for item in generated
        }
        self.assertEqual(len(full_names), PROFILE_COUNT)
        self.assertEqual(generated.values("last_name").distinct().count(), PROFILE_COUNT)
        self.assertNotIn("MARIANO", {item.last_name.upper() for item in generated})
        self.assertEqual(generated.filter(work_shift=Driver.WorkShift.DAY).count(), 75)
        self.assertEqual(generated.filter(work_shift=Driver.WorkShift.NIGHT).count(), 75)
        self.assertEqual(self.aljohn.work_shift, Driver.WorkShift.DAY)
        self.assertEqual(
            Driver.objects.filter(employment_status=Driver.EmploymentStatus.ACTIVE).count(),
            PROFILE_COUNT + 2,
        )
        forbidden = ("DEMO", "TEST", "SAMPLE", "DUMMY")
        today = timezone.localdate()
        for driver in generated:
            self.assertRegex(compact_driver_name(driver), r"^[A-Za-zÀ-ÿ]+ [A-Z]\. .+$")
            self.assertEqual(len(driver.weekly_rest_days), 2)
            self.assertEqual(len(set(driver.weekly_rest_days)), 2)
            self.assertTrue(set(driver.weekly_rest_days) <= set(WEEKDAYS))
            material = " ".join(
                (
                    driver.driver_code,
                    driver.first_name,
                    driver.middle_name,
                    driver.last_name,
                    driver.email,
                    driver.license_number,
                )
            ).upper()
            self.assertFalse(any(word in material for word in forbidden))
            self.assertTrue(driver.contact_number)
            self.assertTrue(driver.email.endswith("@example.com"))
            self.assertTrue(driver.external_hr_id)
            self.assertTrue(driver.date_hired)
            self.assertTrue(driver.license_number)
            self.assertTrue(driver.license_category)
            self.assertTrue(driver.license_codes)
            self.assertLess(driver.license_issue_date, driver.license_expiry_date)
            self.assertGreaterEqual(driver.license_expiry_date, today)
            self.assertGreaterEqual(driver.medical_certificate_expiry_date, today)
            self.assertEqual(driver_eligibility(driver), ("ELIGIBLE", []))

        self.assertFalse(Driver.objects.filter(pk=self.unreferenced_legacy.pk).exists())
        self.referenced_legacy.refresh_from_db()
        self.assertEqual(
            self.referenced_legacy.employment_status,
            Driver.EmploymentStatus.TERMINATED,
        )
        self.assertEqual(self.referenced_legacy.linked_user_id, self.legacy_account.pk)
        self.assertEqual(DispatchAssignment.objects.count(), 0)

    def test_rerun_is_idempotent(self):
        self.run_seed("--replace-development-drivers")
        generated_ids = dict(
            Driver.objects.filter(driver_code__startswith=CODE_PREFIX).values_list(
                "driver_code", "pk"
            )
        )
        original_master_data = list(
            Driver.objects.filter(driver_code__startswith=CODE_PREFIX)
            .order_by("driver_code")
            .values_list(
                "driver_code", "first_name", "middle_name", "last_name",
                "work_shift", "weekly_rest_days",
            )
        )

        self.run_seed("--replace-development-drivers")

        self.assertEqual(
            dict(
                Driver.objects.filter(driver_code__startswith=CODE_PREFIX).values_list(
                    "driver_code", "pk"
                )
            ),
            generated_ids,
        )
        self.assertEqual(
            Driver.objects.filter(employment_status=Driver.EmploymentStatus.ACTIVE).count(),
            PROFILE_COUNT + 2,
        )
        self.assertEqual(DispatchAssignment.objects.count(), 0)
        self.assertEqual(
            list(
                Driver.objects.filter(driver_code__startswith=CODE_PREFIX)
                .order_by("driver_code")
                .values_list(
                    "driver_code", "first_name", "middle_name", "last_name",
                    "work_shift", "weekly_rest_days",
                )
            ),
            original_master_data,
        )

    def test_rest_day_distribution_is_balanced_and_varied(self):
        self.run_seed("--replace-development-drivers")
        drivers = list(Driver.objects.filter(employment_status=Driver.EmploymentStatus.ACTIVE))
        counts = {day: 0 for day in WEEKDAYS}
        combinations = set()
        for driver in drivers:
            combinations.add(tuple(driver.weekly_rest_days))
            for day in driver.weekly_rest_days:
                counts[day] += 1
        self.assertEqual(sum(counts.values()), 304)
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 2)
        self.assertGreater(len(combinations), 7)

    def test_mobile_access_driver_remains_protected_on_repeated_cleanup(self):
        identity = (
            self.mobile_driver.pk,
            self.mobile_driver.linked_user_id,
            self.mobile_driver.external_hr_id,
        )
        self.run_seed("--replace-development-drivers")
        self.mobile_driver.refresh_from_db()
        first_schedule = (
            self.mobile_driver.work_shift,
            list(self.mobile_driver.weekly_rest_days),
        )

        self.run_seed("--replace-development-drivers")
        self.mobile_driver.refresh_from_db()

        self.assertEqual(
            (
                self.mobile_driver.pk,
                self.mobile_driver.linked_user_id,
                self.mobile_driver.external_hr_id,
            ),
            identity,
        )
        self.assertEqual(
            (self.mobile_driver.work_shift, self.mobile_driver.weekly_rest_days),
            first_schedule,
        )
        self.assertEqual(
            self.mobile_driver.employment_status, Driver.EmploymentStatus.ACTIVE
        )
        self.assertEqual(
            Driver.objects.filter(driver_code__startswith=CODE_PREFIX).count(),
            PROFILE_COUNT,
        )
