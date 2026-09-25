from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class StaffProfile(models.Model):
    class Role(models.TextChoices):
        FLEET_ADMIN = "FLEET_ADMIN", "Fleet Admin"
        FLEET_MANAGER = "FLEET_MANAGER", "Fleet Manager"
        DISPATCHER = "DISPATCHER", "Dispatcher"
        FLEET_STAFF = "FLEET_STAFF", "Fleet Staff"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_profile"
    )
    role = models.CharField(max_length=20, choices=Role.choices)

    def __str__(self):
        return f"{self.user.username}: {self.role}"


class TwoFactorCredential(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="two_factor_credential",
    )
    encrypted_secret = models.TextField()
    is_enabled = models.BooleanField(default=False)
    enabled_at = models.DateTimeField(null=True, blank=True)
    last_used_time_step = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Two-factor credential for {self.user_id}"


class TwoFactorRecoveryCode(models.Model):
    credential = models.ForeignKey(
        TwoFactorCredential,
        on_delete=models.CASCADE,
        related_name="recovery_codes",
    )
    code_hash = models.CharField(max_length=128)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Two-factor recovery code {self.pk}"


class ActiveUserSession(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="active_ftms_session",
    )
    session_key = models.CharField(max_length=40, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Active FTMS session for user {self.user_id}"


class StaffLoginSecurityState(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_login_security_state",
    )
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Staff login security state for user {self.user_id}"


class AuditEvent(models.Model):
    class ActorType(models.TextChoices):
        STAFF = "STAFF", "Staff"
        DRIVER = "DRIVER", "Driver"
        SYSTEM = "SYSTEM", "System"
        DEVICE = "DEVICE", "Device"
        UNKNOWN = "UNKNOWN", "Unknown"

    class Outcome(models.TextChoices):
        SUCCESS = "SUCCESS", "Success"
        FAILURE = "FAILURE", "Failure"
        DENIED = "DENIED", "Denied"

    class Source(models.TextChoices):
        WEB = "WEB", "Web"
        MOBILE = "MOBILE", "Mobile"
        API = "API", "API"
        SYSTEM = "SYSTEM", "System"

    occurred_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    actor_type = models.CharField(
        max_length=12, choices=ActorType.choices, default=ActorType.UNKNOWN
    )
    action = models.CharField(max_length=64)
    target_type = models.CharField(max_length=80, blank=True, default="")
    target_id = models.CharField(max_length=80, blank=True, default="")
    target_label = models.CharField(max_length=180, blank=True, default="")
    outcome = models.CharField(
        max_length=12, choices=Outcome.choices, default=Outcome.SUCCESS
    )
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.WEB)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=240, blank=True, default="")
    changes = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-occurred_at", "-pk")
        indexes = [
            models.Index(fields=["-occurred_at"], name="audit_event_time_idx"),
            models.Index(fields=["actor", "-occurred_at"], name="audit_event_actor_time_idx"),
            models.Index(fields=["action", "-occurred_at"], name="audit_event_action_time_idx"),
            models.Index(fields=["target_type", "target_id"], name="audit_event_target_idx"),
        ]

    def __str__(self):
        return f"{self.occurred_at}: {self.action}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Audit events are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Audit events are immutable.")


class PermissionModule(models.TextChoices):
    DASHBOARD = "DASHBOARD", "Dashboard"
    TRANSPORT_REQUESTS = "TRANSPORT_REQUESTS", "Transport Requests"
    DISPATCH_BOARD = "DISPATCH_BOARD", "Dispatch Board"
    LIVE_MAP = "LIVE_MAP", "Live Map"
    DRIVERS = "DRIVERS", "Drivers"
    DRIVER_SAFETY = "DRIVER_SAFETY", "Driver Safety"
    VEHICLES = "VEHICLES", "Vehicles"
    INSPECTIONS = "INSPECTIONS", "Inspections"
    ALERTS_SOS = "ALERTS_SOS", "Alerts & SOS"
    FUEL_ANALYTICS = "FUEL_ANALYTICS", "Fuel Analytics"
    MAINTENANCE = "MAINTENANCE", "Maintenance"
    REPORTS = "REPORTS", "Reports"
    DEVICES = "DEVICES", "Devices"
    SYSTEM_SETTINGS = "SYSTEM_SETTINGS", "System Settings"
    USERS_ACCESS = "USERS_ACCESS", "Users & Access"


class PermissionAction(models.TextChoices):
    VIEW = "VIEW", "View"
    EDIT = "EDIT", "Edit"
    APPROVE = "APPROVE", "Approve"
    CANCEL = "CANCEL", "Cancel"
    ASSIGN = "ASSIGN", "Assign"
    DISPATCH = "DISPATCH", "Dispatch"
    OVERRIDE = "OVERRIDE", "Override"
    GENERATE_RECOMMENDATION = "GENERATE_RECOMMENDATION", "Generate Recommendation"
    REJECT = "REJECT", "Reject"
    REQUEST_MORE_DETAILS = "REQUEST_MORE_DETAILS", "Request More Details"
    PREPARE_DISPATCH = "PREPARE_DISPATCH", "Prepare Dispatch"
    MANAGE_GEOFENCES = "MANAGE_GEOFENCES", "Manage Geofences"
    CREATE = "CREATE", "Create"
    MANAGE_DOCUMENTS = "MANAGE_DOCUMENTS", "Manage Documents"
    CHANGE_STATUS = "CHANGE_STATUS", "Change Status"
    INSPECT = "INSPECT", "Inspect"
    CORRECT = "CORRECT", "Correct"
    SCHEDULE = "SCHEDULE", "Schedule"
    START = "START", "Start"
    COMPLETE = "COMPLETE", "Complete"
    EXPORT = "EXPORT", "Export"
    REGISTER = "REGISTER", "Register"
    PAIR = "PAIR", "Pair"
    REPLACE = "REPLACE", "Replace"
    UNPAIR = "UNPAIR", "Unpair"
    MANAGE_NUMBER_CODING = "MANAGE_NUMBER_CODING", "Manage Number Coding"
    MANAGE_PRICES = "MANAGE_PRICES", "Manage Fuel Prices"
    VIEW_USERS = "VIEW_USERS", "View Users"
    CREATE_USER = "CREATE_USER", "Create User"
    EDIT_USER = "EDIT_USER", "Edit User"
    CHANGE_USER_STATUS = "CHANGE_USER_STATUS", "Change User Status"
    ASSIGN_ROLE = "ASSIGN_ROLE", "Assign Role"
    MANAGE_ROLE_PERMISSIONS = "MANAGE_ROLE_PERMISSIONS", "Manage Role Permissions"


VALID_MODULE_ACTIONS = {
    PermissionModule.DASHBOARD: (PermissionAction.VIEW,),
    PermissionModule.TRANSPORT_REQUESTS: (
        PermissionAction.VIEW,
        PermissionAction.EDIT,
        PermissionAction.APPROVE,
        PermissionAction.REJECT,
        PermissionAction.REQUEST_MORE_DETAILS,
        PermissionAction.PREPARE_DISPATCH,
        PermissionAction.CANCEL,
    ),
    PermissionModule.DISPATCH_BOARD: (
        PermissionAction.VIEW,
        PermissionAction.GENERATE_RECOMMENDATION,
        PermissionAction.ASSIGN,
        PermissionAction.DISPATCH,
        PermissionAction.OVERRIDE,
    ),
    PermissionModule.LIVE_MAP: (
        PermissionAction.VIEW,
        PermissionAction.MANAGE_GEOFENCES,
    ),
    PermissionModule.DRIVERS: (
        PermissionAction.VIEW,
        PermissionAction.CREATE,
        PermissionAction.EDIT,
        PermissionAction.MANAGE_DOCUMENTS,
    ),
    PermissionModule.DRIVER_SAFETY: (PermissionAction.VIEW,),
    PermissionModule.VEHICLES: (
        PermissionAction.VIEW,
        PermissionAction.CREATE,
        PermissionAction.EDIT,
        PermissionAction.CHANGE_STATUS,
        PermissionAction.MANAGE_DOCUMENTS,
    ),
    PermissionModule.INSPECTIONS: (
        PermissionAction.VIEW,
        PermissionAction.CREATE,
        PermissionAction.CORRECT,
    ),
    PermissionModule.ALERTS_SOS: (PermissionAction.VIEW,),
    PermissionModule.FUEL_ANALYTICS: (PermissionAction.VIEW,),
    PermissionModule.MAINTENANCE: (
        PermissionAction.VIEW,
        PermissionAction.CREATE,
        PermissionAction.SCHEDULE,
        PermissionAction.START,
        PermissionAction.COMPLETE,
        PermissionAction.CANCEL,
    ),
    PermissionModule.REPORTS: (PermissionAction.VIEW, PermissionAction.EXPORT),
    PermissionModule.DEVICES: (
        PermissionAction.VIEW,
        PermissionAction.REGISTER,
        PermissionAction.PAIR,
        PermissionAction.REPLACE,
        PermissionAction.UNPAIR,
    ),
    PermissionModule.SYSTEM_SETTINGS: (
        PermissionAction.VIEW,
        PermissionAction.MANAGE_NUMBER_CODING,
        PermissionAction.MANAGE_PRICES,
    ),
    PermissionModule.USERS_ACCESS: (
        PermissionAction.VIEW_USERS,
        PermissionAction.CREATE_USER,
        PermissionAction.EDIT_USER,
        PermissionAction.CHANGE_USER_STATUS,
        PermissionAction.ASSIGN_ROLE,
        PermissionAction.MANAGE_ROLE_PERMISSIONS,
    ),
}


def valid_module_action(module, action):
    return module in VALID_MODULE_ACTIONS and action in VALID_MODULE_ACTIONS[module]


class RolePermission(models.Model):
    role = models.CharField(max_length=20, choices=StaffProfile.Role.choices)
    module = models.CharField(max_length=32, choices=PermissionModule.choices)
    action = models.CharField(max_length=32, choices=PermissionAction.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("role", "module", "action"),
                name="accounts_unique_role_module_action",
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=StaffProfile.Role.values),
                name="accounts_rolepermission_managed_role",
            ),
        ]
        ordering = ("role", "module", "action")

    def __str__(self):
        return f"{self.role}: {self.module}.{self.action}"

    def clean(self):
        super().clean()
        if not valid_module_action(self.module, self.action):
            raise ValidationError({"action": "Action is not valid for the selected module."})


class UserNotification(models.Model):
    IMMUTABLE_FIELDS = (
        "recipient_id",
        "notification_type",
        "title",
        "message",
        "target_url",
        "source_key",
    )

    class Type(models.TextChoices):
        TRANSPORT_READY = "TRANSPORT_READY", "Transport request ready"
        DISPATCH_CONFIRMED = "DISPATCH_CONFIRMED", "Dispatch confirmed"
        DRIVER_ACCEPTED = "DRIVER_ACCEPTED", "Driver accepted"
        SOS_ACTIVE = "SOS_ACTIVE", "SOS active"
        INSPECTION_ATTENTION = "INSPECTION_ATTENTION", "Inspection attention"
        MAINTENANCE_COMPLETED = "MAINTENANCE_COMPLETED", "Maintenance completed"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ftms_notifications",
    )
    notification_type = models.CharField(max_length=32, choices=Type.choices)
    title = models.CharField(max_length=160)
    message = models.CharField(max_length=500)
    target_url = models.CharField(max_length=300)
    source_key = models.CharField(max_length=180)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        constraints = [
            models.UniqueConstraint(
                fields=("recipient", "source_key"),
                name="accounts_unique_notification_source_per_recipient",
            )
        ]
        indexes = [
            models.Index(
                fields=("recipient", "is_read", "created_at"),
                name="accounts_notif_inbox_idx",
            )
        ]

    def __str__(self):
        return f"{self.recipient_id}: {self.title}"

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values(
                *self.IMMUTABLE_FIELDS
            ).first()
            if original and any(
                original[field] != getattr(self, field) for field in self.IMMUTABLE_FIELDS
            ):
                raise ValidationError(
                    "Notification content is immutable; only read state may change."
                )
        return super().save(*args, **kwargs)
