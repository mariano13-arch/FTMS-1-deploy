from django.db import migrations, models

MODULE_CHOICES = [
    ("DASHBOARD", "Dashboard"),
    ("TRANSPORT_REQUESTS", "Transport Requests"),
    ("DISPATCH_BOARD", "Dispatch Board"),
    ("LIVE_MAP", "Live Map"),
    ("DRIVERS", "Drivers"),
    ("DRIVER_SAFETY", "Driver Safety"),
    ("VEHICLES", "Vehicles"),
    ("INSPECTIONS", "Inspections"),
    ("ALERTS_SOS", "Alerts & SOS"),
    ("FUEL_ANALYTICS", "Fuel Analytics"),
    ("MAINTENANCE", "Maintenance"),
    ("REPORTS", "Reports"),
    ("DEVICES", "Devices"),
    ("SYSTEM_SETTINGS", "System Settings"),
    ("USERS_ACCESS", "Users & Access"),
]

ACTION_CHOICES = [
    ("VIEW", "View"),
    ("EDIT", "Edit"),
    ("APPROVE", "Approve"),
    ("CANCEL", "Cancel"),
    ("ASSIGN", "Assign"),
    ("DISPATCH", "Dispatch"),
    ("OVERRIDE", "Override"),
    ("GENERATE_RECOMMENDATION", "Generate Recommendation"),
    ("REJECT", "Reject"),
    ("REQUEST_MORE_DETAILS", "Request More Details"),
    ("PREPARE_DISPATCH", "Prepare Dispatch"),
    ("MANAGE_GEOFENCES", "Manage Geofences"),
    ("CREATE", "Create"),
    ("MANAGE_DOCUMENTS", "Manage Documents"),
    ("CHANGE_STATUS", "Change Status"),
    ("INSPECT", "Inspect"),
    ("CORRECT", "Correct"),
    ("SCHEDULE", "Schedule"),
    ("START", "Start"),
    ("COMPLETE", "Complete"),
    ("EXPORT", "Export"),
    ("REGISTER", "Register"),
    ("PAIR", "Pair"),
    ("REPLACE", "Replace"),
    ("UNPAIR", "Unpair"),
    ("MANAGE_NUMBER_CODING", "Manage Number Coding"),
    ("MANAGE_PRICES", "Manage Fuel Prices"),
    ("VIEW_USERS", "View Users"),
    ("CREATE_USER", "Create User"),
    ("EDIT_USER", "Edit User"),
    ("CHANGE_USER_STATUS", "Change User Status"),
    ("ASSIGN_ROLE", "Assign Role"),
    ("MANAGE_ROLE_PERMISSIONS", "Manage Role Permissions"),
]

VALID = {
    "DASHBOARD": ("VIEW",),
    "TRANSPORT_REQUESTS": (
        "VIEW",
        "EDIT",
        "APPROVE",
        "REJECT",
        "REQUEST_MORE_DETAILS",
        "PREPARE_DISPATCH",
        "CANCEL",
    ),
    "DISPATCH_BOARD": ("VIEW", "GENERATE_RECOMMENDATION", "ASSIGN", "DISPATCH", "OVERRIDE"),
    "LIVE_MAP": ("VIEW", "MANAGE_GEOFENCES"),
    "DRIVERS": ("VIEW", "CREATE", "EDIT", "MANAGE_DOCUMENTS"),
    "DRIVER_SAFETY": ("VIEW",),
    "VEHICLES": ("VIEW", "CREATE", "EDIT", "CHANGE_STATUS", "MANAGE_DOCUMENTS"),
    "INSPECTIONS": ("VIEW", "CREATE", "CORRECT"),
    "ALERTS_SOS": ("VIEW",),
    "FUEL_ANALYTICS": ("VIEW",),
    "MAINTENANCE": ("VIEW", "CREATE", "SCHEDULE", "START", "COMPLETE", "CANCEL"),
    "REPORTS": ("VIEW", "EXPORT"),
    "DEVICES": ("VIEW", "REGISTER", "PAIR", "REPLACE", "UNPAIR"),
    "SYSTEM_SETTINGS": ("VIEW", "MANAGE_NUMBER_CODING", "MANAGE_PRICES"),
    "USERS_ACCESS": (
        "VIEW_USERS",
        "CREATE_USER",
        "EDIT_USER",
        "CHANGE_USER_STATUS",
        "ASSIGN_ROLE",
        "MANAGE_ROLE_PERMISSIONS",
    ),
}

MANAGER = {module: actions for module, actions in VALID.items() if module != "USERS_ACCESS"}
DISPATCHER = {
    "DASHBOARD": ("VIEW",),
    "TRANSPORT_REQUESTS": ("VIEW", "EDIT", "PREPARE_DISPATCH"),
    "DISPATCH_BOARD": ("VIEW", "GENERATE_RECOMMENDATION", "ASSIGN", "DISPATCH", "OVERRIDE"),
    "LIVE_MAP": ("VIEW",),
    "DRIVERS": ("VIEW",),
    "DRIVER_SAFETY": ("VIEW",),
    "VEHICLES": ("VIEW",),
    "INSPECTIONS": ("VIEW",),
    "ALERTS_SOS": ("VIEW",),
    "FUEL_ANALYTICS": ("VIEW",),
    "MAINTENANCE": ("VIEW",),
}
STAFF = {
    "DASHBOARD": ("VIEW",),
    "TRANSPORT_REQUESTS": ("VIEW",),
    "LIVE_MAP": ("VIEW",),
    "DRIVERS": ("VIEW",),
    "VEHICLES": ("VIEW",),
    "INSPECTIONS": ("VIEW", "CREATE"),
    "ALERTS_SOS": ("VIEW",),
    "MAINTENANCE": ("VIEW", "CREATE", "START", "COMPLETE"),
    "DEVICES": ("VIEW", "REGISTER", "PAIR", "UNPAIR"),
}


def seed_permissions(apps, schema_editor):
    permission = apps.get_model("accounts", "RolePermission")
    inspect_roles = list(
        permission.objects.filter(module="VEHICLES", action="INSPECT").values_list(
            "role", flat=True
        )
    )
    for role in inspect_roles:
        for action in ("VIEW", "CREATE"):
            permission.objects.get_or_create(role=role, module="INSPECTIONS", action=action)
    permission.objects.filter(module="VEHICLES", action="INSPECT").delete()

    defaults = {
        "FLEET_ADMIN": VALID,
        "FLEET_MANAGER": MANAGER,
        "DISPATCHER": DISPATCHER,
        "FLEET_STAFF": STAFF,
    }
    for role, policy in defaults.items():
        for module, actions in policy.items():
            for action in actions:
                permission.objects.get_or_create(role=role, module=module, action=action)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_staff_role_refresh")]

    operations = [
        migrations.AlterField(
            model_name="rolepermission",
            name="module",
            field=models.CharField(choices=MODULE_CHOICES, max_length=32),
        ),
        migrations.AlterField(
            model_name="rolepermission",
            name="action",
            field=models.CharField(choices=ACTION_CHOICES, max_length=32),
        ),
        migrations.RunPython(seed_permissions, migrations.RunPython.noop),
    ]
