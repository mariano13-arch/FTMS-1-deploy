from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import PermissionAction, PermissionModule, RolePermission, StaffProfile
from accounts.roles import has_module_permission, resolve_role
from fleet.models import Driver, Vehicle


class PhaseP1RoleAndPermissionTests(TestCase):
    def staff(self, username, role, *, superuser=False):
        user = get_user_model().objects.create_user(
            username=username,
            password="test",
            is_staff=True,
            is_superuser=superuser,
        )
        StaffProfile.objects.create(user=user, role=role)
        return user

    @staticmethod
    def client_for(user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_staff_role_vocabulary_is_exact_and_excludes_driver_and_super_admin(self):
        self.assertEqual(
            set(StaffProfile.Role.values),
            {"FLEET_ADMIN", "FLEET_MANAGER", "DISPATCHER", "FLEET_STAFF"},
        )
        self.assertNotIn("DRIVER", StaffProfile.Role.values)
        self.assertNotIn("SUPER_ADMIN", StaffProfile.Role.values)

    def test_profileless_django_superuser_has_no_ftms_business_role(self):
        user = get_user_model().objects.create_superuser("framework-root", password="test")
        self.assertIsNone(resolve_role(user))
        self.assertFalse(
            has_module_permission(user, PermissionModule.USERS_ACCESS, PermissionAction.VIEW_USERS)
        )

    def test_fleet_admin_is_persisted_role_and_has_users_access(self):
        admin = self.staff("admin", StaffProfile.Role.FLEET_ADMIN, superuser=True)
        self.assertEqual(resolve_role(admin), "FLEET_ADMIN")
        self.assertEqual(
            self.client_for(admin).get("/api/v1/auth/role-permissions/").status_code,
            200,
        )

    def test_non_admin_roles_cannot_manage_permission_matrix(self):
        for role in (
            StaffProfile.Role.FLEET_MANAGER,
            StaffProfile.Role.DISPATCHER,
            StaffProfile.Role.FLEET_STAFF,
        ):
            with self.subTest(role=role):
                user = self.staff(role.lower(), role)
                self.assertEqual(
                    self.client_for(user).get("/api/v1/auth/role-permissions/").status_code,
                    403,
                )

    def test_missing_grant_denies_and_added_grant_allows_transport_read(self):
        user = self.staff("limited", StaffProfile.Role.FLEET_STAFF)
        RolePermission.objects.filter(
            role=user.staff_profile.role,
            module=PermissionModule.TRANSPORT_REQUESTS,
            action=PermissionAction.VIEW,
        ).delete()
        client = self.client_for(user)
        self.assertEqual(client.get("/api/v1/transport-requests/").status_code, 403)
        RolePermission.objects.create(
            role=user.staff_profile.role,
            module=PermissionModule.TRANSPORT_REQUESTS,
            action=PermissionAction.VIEW,
        )
        self.assertEqual(client.get("/api/v1/transport-requests/").status_code, 200)

    def test_dispatch_and_geofence_writes_require_their_stored_grants(self):
        dispatcher = self.staff("dispatcher", StaffProfile.Role.DISPATCHER)
        RolePermission.objects.filter(
            role=StaffProfile.Role.DISPATCHER,
            module=PermissionModule.LIVE_MAP,
            action=PermissionAction.MANAGE_GEOFENCES,
        ).delete()
        client = self.client_for(dispatcher)
        response = client.post("/api/v1/fleet-live/geofences/", {}, format="json")
        self.assertEqual(response.status_code, 403)

        staff = self.staff("field", StaffProfile.Role.FLEET_STAFF)
        self.assertEqual(
            self.client_for(staff).post(
                "/api/v1/transport-requests/dispatch-board/confirm/", {}, format="json"
            ).status_code,
            403,
        )

    def test_fleet_staff_can_reach_supported_inspection_creation(self):
        staff = self.staff("inspector", StaffProfile.Role.FLEET_STAFF)
        vehicle = Vehicle.objects.create(
            device_id="P1-INSPECT", display_name="P1 Van", plate_number="P1-001"
        )
        response = self.client_for(staff).post(
            f"/api/v1/vehicles/{vehicle.device_id}/inspections/", {}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_sensitive_driver_documents_require_manage_documents(self):
        dispatcher = self.staff("docs-dispatcher", StaffProfile.Role.DISPATCHER)
        driver = Driver.objects.create(
            driver_code="P1-DOC", first_name="P1", last_name="Driver"
        )
        self.assertEqual(
            self.client_for(dispatcher).get(
                f"/api/v1/drivers/{driver.pk}/documents/"
            ).status_code,
            403,
        )
