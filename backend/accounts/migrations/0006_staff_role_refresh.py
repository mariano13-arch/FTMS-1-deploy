from django.db import migrations, models

FLEET_ADMIN_PERMISSIONS = (
    ("TRANSPORT_REQUESTS", ("VIEW", "EDIT", "APPROVE", "CANCEL")),
    ("DISPATCH_BOARD", ("VIEW", "ASSIGN", "DISPATCH", "OVERRIDE")),
    ("LIVE_MAP", ("VIEW", "MANAGE_GEOFENCES")),
    ("DRIVERS", ("VIEW", "CREATE", "EDIT", "MANAGE_DOCUMENTS")),
    ("VEHICLES", ("VIEW", "CREATE", "EDIT", "CHANGE_STATUS", "INSPECT", "MANAGE_DOCUMENTS")),
    ("FUEL_ANALYTICS", ("VIEW",)),
    ("MAINTENANCE", ("VIEW",)),
    ("SYSTEM_SETTINGS", ("VIEW",)),
    (
        "USERS_ACCESS",
        (
            "VIEW_USERS",
            "CREATE_USER",
            "EDIT_USER",
            "CHANGE_USER_STATUS",
            "ASSIGN_ROLE",
            "MANAGE_ROLE_PERMISSIONS",
        ),
    ),
)

FLEET_STAFF_PERMISSIONS = (
    ("TRANSPORT_REQUESTS", ("VIEW",)),
    ("LIVE_MAP", ("VIEW",)),
    ("DRIVERS", ("VIEW",)),
    ("VEHICLES", ("VIEW", "INSPECT")),
    ("MAINTENANCE", ("VIEW",)),
)


def persist_approved_fleet_admin_and_defaults(apps, schema_editor):
    user_model = apps.get_model("auth", "User")
    staff_profile = apps.get_model("accounts", "StaffProfile")
    role_permission = apps.get_model("accounts", "RolePermission")

    # User ID 16 was explicitly approved after the pre-migration safety audit.
    approved = user_model.objects.filter(
        pk=16, is_active=True, is_staff=True, is_superuser=True
    ).first()
    if approved is not None:
        staff_profile.objects.update_or_create(
            user_id=approved.pk, defaults={"role": "FLEET_ADMIN"}
        )

    for role, policy in (
        ("FLEET_ADMIN", FLEET_ADMIN_PERMISSIONS),
        ("FLEET_STAFF", FLEET_STAFF_PERMISSIONS),
    ):
        for module, actions in policy:
            for action in actions:
                role_permission.objects.get_or_create(
                    role=role, module=module, action=action
                )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_activeusersession")]

    operations = [
        migrations.AlterField(
            model_name="staffprofile",
            name="role",
            field=models.CharField(
                choices=[
                    ("FLEET_ADMIN", "Fleet Admin"),
                    ("FLEET_MANAGER", "Fleet Manager"),
                    ("DISPATCHER", "Dispatcher"),
                    ("FLEET_STAFF", "Fleet Staff"),
                ],
                max_length=20,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="rolepermission",
            name="accounts_rolepermission_managed_role",
        ),
        migrations.AlterField(
            model_name="rolepermission",
            name="role",
            field=models.CharField(
                choices=[
                    ("FLEET_ADMIN", "Fleet Admin"),
                    ("FLEET_MANAGER", "Fleet Manager"),
                    ("DISPATCHER", "Dispatcher"),
                    ("FLEET_STAFF", "Fleet Staff"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="rolepermission",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    role__in=(
                        "FLEET_ADMIN",
                        "FLEET_MANAGER",
                        "DISPATCHER",
                        "FLEET_STAFF",
                    )
                ),
                name="accounts_rolepermission_managed_role",
            ),
        ),
        migrations.RunPython(
            persist_approved_fleet_admin_and_defaults,
            migrations.RunPython.noop,
        ),
    ]
