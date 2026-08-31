from django.db import migrations


FLEET_MANAGER_PERMISSIONS = (
    ("TRANSPORT_REQUESTS", "VIEW"),
    ("TRANSPORT_REQUESTS", "EDIT"),
    ("TRANSPORT_REQUESTS", "APPROVE"),
    ("TRANSPORT_REQUESTS", "CANCEL"),
    ("DISPATCH_BOARD", "VIEW"),
    ("DISPATCH_BOARD", "ASSIGN"),
    ("DISPATCH_BOARD", "DISPATCH"),
    ("DISPATCH_BOARD", "OVERRIDE"),
    ("LIVE_MAP", "VIEW"),
    ("LIVE_MAP", "MANAGE_GEOFENCES"),
    ("DRIVERS", "VIEW"),
    ("DRIVERS", "EDIT"),
    ("DRIVERS", "MANAGE_DOCUMENTS"),
    ("VEHICLES", "VIEW"),
    ("VEHICLES", "EDIT"),
    ("VEHICLES", "INSPECT"),
    ("VEHICLES", "MANAGE_DOCUMENTS"),
    ("FUEL_ANALYTICS", "VIEW"),
    ("MAINTENANCE", "VIEW"),
)

DISPATCHER_PERMISSIONS = (
    ("TRANSPORT_REQUESTS", "VIEW"),
    ("TRANSPORT_REQUESTS", "EDIT"),
    ("DISPATCH_BOARD", "VIEW"),
    ("DISPATCH_BOARD", "ASSIGN"),
    ("DISPATCH_BOARD", "DISPATCH"),
    ("DISPATCH_BOARD", "OVERRIDE"),
    ("LIVE_MAP", "VIEW"),
    ("DRIVERS", "VIEW"),
    ("VEHICLES", "VIEW"),
    ("FUEL_ANALYTICS", "VIEW"),
    ("MAINTENANCE", "VIEW"),
)

INITIAL_PERMISSIONS = {
    "FLEET_MANAGER": FLEET_MANAGER_PERMISSIONS,
    "DISPATCHER": DISPATCHER_PERMISSIONS,
}


def seed_role_permissions(apps, schema_editor):
    role_permission = apps.get_model("accounts", "RolePermission")
    for role, permissions in INITIAL_PERMISSIONS.items():
        for module, action in permissions:
            role_permission.objects.get_or_create(
                role=role,
                module=module,
                action=action,
            )


def remove_seeded_role_permissions(apps, schema_editor):
    role_permission = apps.get_model("accounts", "RolePermission")
    for role, permissions in INITIAL_PERMISSIONS.items():
        for module, action in permissions:
            role_permission.objects.filter(
                role=role,
                module=module,
                action=action,
            ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_rolepermission"),
    ]

    operations = [
        migrations.RunPython(
            seed_role_permissions,
            remove_seeded_role_permissions,
        ),
    ]
