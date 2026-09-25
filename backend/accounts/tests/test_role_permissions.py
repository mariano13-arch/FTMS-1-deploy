from importlib import import_module

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import (
    VALID_MODULE_ACTIONS,
    PermissionAction,
    PermissionModule,
    RolePermission,
    StaffProfile,
)
from accounts.roles import has_module_permission


class RolePermissionModelTests(TestCase):
    def setUp(self):
        RolePermission.objects.all().delete()

    def test_managed_roles_can_store_valid_permissions(self):
        for role, module, action in (
            (StaffProfile.Role.FLEET_MANAGER, PermissionModule.VEHICLES, PermissionAction.EDIT),
            (
                StaffProfile.Role.DISPATCHER,
                PermissionModule.DISPATCH_BOARD,
                PermissionAction.DISPATCH,
            ),
        ):
            with self.subTest(role=role):
                permission = RolePermission(role=role, module=module, action=action)
                permission.full_clean()
                permission.save()
        self.assertEqual(RolePermission.objects.count(), 2)

    def test_p2a_matrix_defines_every_approved_module_and_action(self):
        expected = {
            "DASHBOARD": {"VIEW"},
            "TRANSPORT_REQUESTS": {
                "VIEW",
                "EDIT",
                "APPROVE",
                "REJECT",
                "REQUEST_MORE_DETAILS",
                "PREPARE_DISPATCH",
                "CANCEL",
            },
            "DISPATCH_BOARD": {"VIEW", "GENERATE_RECOMMENDATION", "ASSIGN", "DISPATCH", "OVERRIDE"},
            "LIVE_MAP": {"VIEW", "MANAGE_GEOFENCES"},
            "DRIVERS": {"VIEW", "CREATE", "EDIT", "MANAGE_DOCUMENTS"},
            "DRIVER_SAFETY": {"VIEW"},
            "VEHICLES": {"VIEW", "CREATE", "EDIT", "CHANGE_STATUS", "MANAGE_DOCUMENTS"},
            "INSPECTIONS": {"VIEW", "CREATE", "CORRECT"},
            "ALERTS_SOS": {"VIEW"},
            "FUEL_ANALYTICS": {"VIEW"},
            "MAINTENANCE": {"VIEW", "CREATE", "SCHEDULE", "START", "COMPLETE", "CANCEL"},
            "REPORTS": {"VIEW", "EXPORT"},
            "DEVICES": {"VIEW", "REGISTER", "PAIR", "REPLACE", "UNPAIR"},
            "SYSTEM_SETTINGS": {"VIEW", "MANAGE_NUMBER_CODING", "MANAGE_PRICES"},
            "USERS_ACCESS": {
                "VIEW_USERS",
                "CREATE_USER",
                "EDIT_USER",
                "CHANGE_USER_STATUS",
                "ASSIGN_ROLE",
                "MANAGE_ROLE_PERMISSIONS",
            },
        }
        self.assertEqual(
            {
                str(module): {str(action) for action in actions}
                for module, actions in VALID_MODULE_ACTIONS.items()
            },
            expected,
        )
        for module, actions in VALID_MODULE_ACTIONS.items():
            for action in actions:
                with self.subTest(module=module, action=action):
                    permission = RolePermission(
                        role=StaffProfile.Role.FLEET_MANAGER,
                        module=module,
                        action=action,
                    )
                    permission.full_clean()

    def test_p2a_permission_seed_is_idempotent(self):
        seed_permissions = import_module(
            "accounts.migrations.0007_permission_matrix_p2a"
        ).seed_permissions
        seed_permissions(apps, None)
        first = set(RolePermission.objects.values_list("role", "module", "action"))
        seed_permissions(apps, None)
        self.assertEqual(
            set(RolePermission.objects.values_list("role", "module", "action")),
            first,
        )

    def test_duplicate_permission_is_database_rejected(self):
        values = {
            "role": StaffProfile.Role.FLEET_MANAGER,
            "module": PermissionModule.VEHICLES,
            "action": PermissionAction.VIEW,
        }
        RolePermission.objects.create(**values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            RolePermission.objects.create(**values)

    def test_super_admin_cannot_be_persisted(self):
        permission = RolePermission(
            role="SUPER_ADMIN",
            module=PermissionModule.VEHICLES,
            action=PermissionAction.VIEW,
        )
        with self.assertRaises(ValidationError):
            permission.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            RolePermission.objects.create(
                role="SUPER_ADMIN",
                module=PermissionModule.VEHICLES,
                action=PermissionAction.VIEW,
            )

    def test_invalid_module_action_and_combination_fail_validation(self):
        cases = (
            ("UNKNOWN", PermissionAction.VIEW),
            (PermissionModule.VEHICLES, "UNKNOWN"),
            (PermissionModule.FUEL_ANALYTICS, PermissionAction.EDIT),
        )
        for module, action in cases:
            with self.subTest(module=module, action=action):
                permission = RolePermission(
                    role=StaffProfile.Role.FLEET_MANAGER,
                    module=module,
                    action=action,
                )
                with self.assertRaises(ValidationError):
                    permission.full_clean()


class ModulePermissionHelperTests(TestCase):
    def setUp(self):
        RolePermission.objects.all().delete()
        user_model = get_user_model()
        self.super_admin = user_model.objects.create_superuser("root", password="test")
        StaffProfile.objects.create(user=self.super_admin, role=StaffProfile.Role.FLEET_ADMIN)
        self.manager = self.create_staff("manager", StaffProfile.Role.FLEET_MANAGER)
        self.dispatcher = self.create_staff("dispatcher", StaffProfile.Role.DISPATCHER)

    @staticmethod
    def create_staff(username, role):
        user = get_user_model().objects.create_user(
            username=username, password="test", is_staff=True
        )
        StaffProfile.objects.create(user=user, role=role)
        return user

    def test_super_admin_bypasses_rows_only_for_valid_combinations(self):
        self.assertTrue(
            has_module_permission(
                self.super_admin, PermissionModule.VEHICLES, PermissionAction.VIEW
            )
        )
        self.assertFalse(
            has_module_permission(
                self.super_admin, PermissionModule.FUEL_ANALYTICS, PermissionAction.EDIT
            )
        )
        self.assertEqual(RolePermission.objects.count(), 0)

    def test_managed_roles_require_their_corresponding_grant(self):
        RolePermission.objects.create(
            role=StaffProfile.Role.FLEET_MANAGER,
            module=PermissionModule.VEHICLES,
            action=PermissionAction.EDIT,
        )
        RolePermission.objects.create(
            role=StaffProfile.Role.DISPATCHER,
            module=PermissionModule.DISPATCH_BOARD,
            action=PermissionAction.DISPATCH,
        )
        self.assertTrue(
            has_module_permission(self.manager, PermissionModule.VEHICLES, PermissionAction.EDIT)
        )
        self.assertFalse(
            has_module_permission(self.manager, PermissionModule.VEHICLES, PermissionAction.VIEW)
        )
        self.assertTrue(
            has_module_permission(
                self.dispatcher, PermissionModule.DISPATCH_BOARD, PermissionAction.DISPATCH
            )
        )
        self.assertFalse(
            has_module_permission(
                self.dispatcher, PermissionModule.DISPATCH_BOARD, PermissionAction.ASSIGN
            )
        )

    def test_inactive_unauthenticated_nonstaff_and_profileless_fail_closed(self):
        self.manager.is_active = False
        self.manager.save(update_fields=["is_active"])
        nonstaff = get_user_model().objects.create_user("nonstaff", password="test")
        profileless = get_user_model().objects.create_user(
            "profileless", password="test", is_staff=True
        )
        for user in (self.manager, AnonymousUser(), nonstaff, profileless, None):
            with self.subTest(user=user):
                self.assertFalse(
                    has_module_permission(user, PermissionModule.VEHICLES, PermissionAction.VIEW)
                )

    def test_invalid_identifiers_fail_closed_even_with_a_grant(self):
        RolePermission.objects.create(
            role=StaffProfile.Role.FLEET_MANAGER,
            module=PermissionModule.VEHICLES,
            action=PermissionAction.VIEW,
        )
        self.assertFalse(has_module_permission(self.manager, "UNKNOWN", "VIEW"))
        self.assertFalse(has_module_permission(self.manager, "VEHICLES", "UNKNOWN"))
        self.assertFalse(
            has_module_permission(
                self.manager, PermissionModule.FUEL_ANALYTICS, PermissionAction.EDIT
            )
        )


class RolePermissionApiTests(TestCase):
    list_url = "/api/v1/auth/role-permissions/"

    def setUp(self):
        RolePermission.objects.all().delete()
        user_model = get_user_model()
        self.super_admin = user_model.objects.create_superuser("root", password="test")
        StaffProfile.objects.create(user=self.super_admin, role=StaffProfile.Role.FLEET_ADMIN)
        self.manager = self.create_staff("manager", StaffProfile.Role.FLEET_MANAGER)
        self.dispatcher = self.create_staff("dispatcher", StaffProfile.Role.DISPATCHER)

    @staticmethod
    def create_staff(username, role):
        user = get_user_model().objects.create_user(
            username=username, password="test", is_staff=True
        )
        StaffProfile.objects.create(user=user, role=role)
        return user

    @staticmethod
    def client_for(user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def role_url(self, role):
        return f"{self.list_url}{role}/"

    def test_super_admin_reads_definitions_and_current_managed_roles(self):
        RolePermission.objects.create(
            role=StaffProfile.Role.DISPATCHER,
            module=PermissionModule.DISPATCH_BOARD,
            action=PermissionAction.VIEW,
        )
        response = self.client_for(self.super_admin).get(self.list_url)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body["roles"]), {"FLEET_MANAGER", "DISPATCHER", "FLEET_STAFF"})
        self.assertNotIn("SUPER_ADMIN", body["roles"])
        self.assertEqual(
            body["definitions"]["TRANSPORT_REQUESTS"],
            [
                "VIEW",
                "EDIT",
                "APPROVE",
                "REJECT",
                "REQUEST_MORE_DETAILS",
                "PREPARE_DISPATCH",
                "CANCEL",
            ],
        )
        self.assertNotIn("CREATE", body["definitions"]["TRANSPORT_REQUESTS"])
        self.assertNotIn("VIEW_AUDIT_LOG", str(body))
        self.assertEqual(body["roles"]["DISPATCHER"]["DISPATCH_BOARD"], ["VIEW"])

    def test_super_admin_atomically_replaces_only_selected_role(self):
        RolePermission.objects.create(
            role=StaffProfile.Role.FLEET_MANAGER,
            module=PermissionModule.VEHICLES,
            action=PermissionAction.VIEW,
        )
        dispatcher = RolePermission.objects.create(
            role=StaffProfile.Role.DISPATCHER,
            module=PermissionModule.DISPATCH_BOARD,
            action=PermissionAction.VIEW,
        )
        response = self.client_for(self.super_admin).put(
            self.role_url("FLEET_MANAGER"),
            {
                "permissions": [
                    {"module": "VEHICLES", "action": "EDIT"},
                    {"module": "MAINTENANCE", "action": "VIEW"},
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(
                RolePermission.objects.filter(role="FLEET_MANAGER").values_list("module", "action")
            ),
            {("VEHICLES", "EDIT"), ("MAINTENANCE", "VIEW")},
        )
        self.assertTrue(RolePermission.objects.filter(pk=dispatcher.pk).exists())

    def test_invalid_replacement_does_not_remove_existing_grants(self):
        existing = RolePermission.objects.create(
            role=StaffProfile.Role.FLEET_MANAGER,
            module=PermissionModule.VEHICLES,
            action=PermissionAction.VIEW,
        )
        invalid_entries = (
            {"module": "UNKNOWN", "action": "VIEW"},
            {"module": "VEHICLES", "action": "UNKNOWN"},
            {"module": "FUEL_ANALYTICS", "action": "EDIT"},
        )
        for entry in invalid_entries:
            with self.subTest(entry=entry):
                response = self.client_for(self.super_admin).put(
                    self.role_url("FLEET_MANAGER"),
                    {"permissions": [entry]},
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertTrue(RolePermission.objects.filter(pk=existing.pk).exists())

    def test_duplicate_and_unknown_fields_are_rejected(self):
        entry = {"module": "VEHICLES", "action": "VIEW"}
        client = self.client_for(self.super_admin)
        duplicate = client.put(
            self.role_url("FLEET_MANAGER"),
            {"permissions": [entry, entry]},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("permissions", duplicate.json())
        unknown = client.put(
            self.role_url("FLEET_MANAGER"),
            {"permissions": [entry], "master": True},
            format="json",
        )
        self.assertEqual(unknown.status_code, 400)
        self.assertIn("master", unknown.json())

    def test_super_admin_role_is_not_editable(self):
        response = self.client_for(self.super_admin).put(
            self.role_url("SUPER_ADMIN"), {"permissions": []}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("role", response.json())

    def test_management_api_requires_super_admin(self):
        for user in (self.manager, self.dispatcher):
            with self.subTest(role=user.staff_profile.role):
                client = self.client_for(user)
                self.assertEqual(client.get(self.list_url).status_code, 403)
                self.assertEqual(
                    client.put(
                        self.role_url("FLEET_MANAGER"),
                        {"permissions": []},
                        format="json",
                    ).status_code,
                    403,
                )
        self.assertEqual(APIClient().get(self.list_url).status_code, 401)

    def test_empty_matrix_does_not_change_existing_auth_or_staff_management(self):
        self.assertEqual(RolePermission.objects.count(), 0)
        self.assertEqual(self.client_for(self.manager).get("/api/v1/auth/me/").status_code, 200)
        self.assertEqual(self.client_for(self.manager).get("/api/v1/auth/staff/").status_code, 403)
        self.assertEqual(
            self.client_for(self.super_admin).get("/api/v1/auth/staff/").status_code,
            200,
        )

    def test_definition_inventory_is_exact(self):
        self.assertEqual(set(VALID_MODULE_ACTIONS), set(PermissionModule.values))
        self.assertNotIn("INSPECT", VALID_MODULE_ACTIONS[PermissionModule.VEHICLES])
        self.assertEqual(
            set(VALID_MODULE_ACTIONS[PermissionModule.INSPECTIONS]),
            {"VIEW", "CREATE", "CORRECT"},
        )


class InitialRolePermissionPolicyTests(TestCase):
    fleet_manager_permissions = {
        (str(module), str(action))
        for module, actions in VALID_MODULE_ACTIONS.items()
        if module != PermissionModule.USERS_ACCESS
        for action in actions
    }
    dispatcher_permissions = {
        ("DASHBOARD", "VIEW"),
        ("TRANSPORT_REQUESTS", "VIEW"),
        ("TRANSPORT_REQUESTS", "EDIT"),
        ("TRANSPORT_REQUESTS", "PREPARE_DISPATCH"),
        ("DISPATCH_BOARD", "VIEW"),
        ("DISPATCH_BOARD", "GENERATE_RECOMMENDATION"),
        ("DISPATCH_BOARD", "ASSIGN"),
        ("DISPATCH_BOARD", "DISPATCH"),
        ("DISPATCH_BOARD", "OVERRIDE"),
        ("LIVE_MAP", "VIEW"),
        ("DRIVERS", "VIEW"),
        ("DRIVER_SAFETY", "VIEW"),
        ("VEHICLES", "VIEW"),
        ("INSPECTIONS", "VIEW"),
        ("ALERTS_SOS", "VIEW"),
        ("FUEL_ANALYTICS", "VIEW"),
        ("MAINTENANCE", "VIEW"),
    }

    @staticmethod
    def grants(role):
        return set(RolePermission.objects.filter(role=role).values_list("module", "action"))

    def test_exact_approved_managed_role_grants_are_seeded(self):
        self.assertEqual(self.grants("FLEET_MANAGER"), self.fleet_manager_permissions)
        self.assertEqual(self.grants("DISPATCHER"), self.dispatcher_permissions)
        self.assertFalse(RolePermission.objects.filter(role="SUPER_ADMIN").exists())

    def test_intentional_denies_are_not_seeded(self):
        users_access_actions = {
            "VIEW_USERS",
            "CREATE_USER",
            "EDIT_USER",
            "CHANGE_USER_STATUS",
            "ASSIGN_ROLE",
            "MANAGE_ROLE_PERMISSIONS",
        }
        for role in (
            StaffProfile.Role.FLEET_MANAGER,
            StaffProfile.Role.DISPATCHER,
            StaffProfile.Role.FLEET_STAFF,
        ):
            with self.subTest(role=role):
                grants = self.grants(role)
                self.assertFalse(
                    any(
                        module == "USERS_ACCESS" and action in users_access_actions
                        for module, action in grants
                    )
                )
        dispatcher_denies = {
            ("TRANSPORT_REQUESTS", "APPROVE"),
            ("TRANSPORT_REQUESTS", "CANCEL"),
            ("LIVE_MAP", "MANAGE_GEOFENCES"),
            ("DRIVERS", "EDIT"),
            ("DRIVERS", "MANAGE_DOCUMENTS"),
            ("VEHICLES", "EDIT"),
            ("VEHICLES", "MANAGE_DOCUMENTS"),
            ("INSPECTIONS", "CREATE"),
            ("REPORTS", "VIEW"),
            ("DEVICES", "VIEW"),
            ("SYSTEM_SETTINGS", "VIEW"),
        }
        self.assertTrue(dispatcher_denies.isdisjoint(self.grants("DISPATCHER")))

    def test_helper_uses_database_rows_not_hardcoded_policy(self):
        manager = get_user_model().objects.create_user(
            username="policy-manager", password="test", is_staff=True
        )
        StaffProfile.objects.create(user=manager, role=StaffProfile.Role.FLEET_MANAGER)
        self.assertTrue(has_module_permission(manager, "MAINTENANCE", "VIEW"))
        RolePermission.objects.filter(
            role="FLEET_MANAGER", module="MAINTENANCE", action="VIEW"
        ).delete()
        self.assertFalse(has_module_permission(manager, "MAINTENANCE", "VIEW"))

    def test_super_admin_can_replace_seeded_matrix_after_migration(self):
        super_admin = get_user_model().objects.create_superuser(
            username="policy-root", password="test"
        )
        StaffProfile.objects.create(user=super_admin, role=StaffProfile.Role.FLEET_ADMIN)
        client = APIClient()
        client.force_authenticate(super_admin)
        response = client.put(
            "/api/v1/auth/role-permissions/FLEET_MANAGER/",
            {"permissions": [{"module": "VEHICLES", "action": "VIEW"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.grants("FLEET_MANAGER"), {("VEHICLES", "VIEW")})
        self.assertEqual(self.grants("DISPATCHER"), self.dispatcher_permissions)
