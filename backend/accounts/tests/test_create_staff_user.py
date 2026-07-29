from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase

from accounts.models import StaffProfile


class CreateStaffUserCommandTests(TestCase):
    def run_command(self, username="newstaff", role="FLEET_MANAGER"):
        output = StringIO()
        call_command(
            "create_staff_user", username=username, role=role, stdout=output
        )
        return output.getvalue()

    @patch(
        "accounts.management.commands.create_staff_user.getpass",
        side_effect=["A-strong-command-password-42!", "A-strong-command-password-42!"],
    )
    def test_success_normalizes_username_and_assigns_role(self, prompt):
        output = self.run_command(username="  NewStaff  ", role="DISPATCHER")
        user = get_user_model().objects.get(username="NewStaff")
        self.assertTrue(user.is_staff)
        self.assertEqual(user.staff_profile.role, StaffProfile.Role.DISPATCHER)
        self.assertNotIn("password", output.lower())
        self.assertEqual(prompt.call_count, 2)

    @patch(
        "accounts.management.commands.create_staff_user.getpass",
        side_effect=["first-password-A1!", "second-password-A1!"],
    )
    def test_mismatch_leaves_no_rows(self, _prompt):
        with self.assertRaises(CommandError):
            self.run_command()
        self.assertFalse(get_user_model().objects.filter(username="newstaff").exists())
        self.assertEqual(StaffProfile.objects.count(), 0)

    @patch(
        "accounts.management.commands.create_staff_user.getpass",
        side_effect=["weak", "weak"],
    )
    def test_weak_password_leaves_no_rows(self, _prompt):
        with self.assertRaises(CommandError):
            self.run_command()
        self.assertFalse(get_user_model().objects.filter(username="newstaff").exists())

    @patch("accounts.management.commands.create_staff_user.getpass")
    def test_invalid_username_fails_before_prompt(self, prompt):
        with self.assertRaises(CommandError):
            self.run_command(username="invalid username")
        prompt.assert_not_called()
        self.assertEqual(get_user_model().objects.count(), 0)

    @patch("accounts.management.commands.create_staff_user.getpass")
    def test_duplicate_username_fails_before_prompt(self, prompt):
        get_user_model().objects.create_user(username="newstaff")
        with self.assertRaises(CommandError):
            self.run_command()
        prompt.assert_not_called()
        self.assertEqual(get_user_model().objects.filter(username="newstaff").count(), 1)

    @patch(
        "accounts.management.commands.create_staff_user.StaffProfile.objects.create",
        side_effect=RuntimeError("profile failure"),
    )
    @patch(
        "accounts.management.commands.create_staff_user.getpass",
        side_effect=["A-strong-command-password-42!", "A-strong-command-password-42!"],
    )
    def test_profile_failure_rolls_back_user(self, _prompt, _create_profile):
        with self.assertRaises(RuntimeError):
            self.run_command()
        self.assertFalse(get_user_model().objects.filter(username="newstaff").exists())

    def test_no_visible_password_argument_exists(self):
        with self.assertRaises(TypeError):
            call_command(
                "create_staff_user", username="newstaff", role="DISPATCHER",
                password="visible-is-forbidden",
            )
