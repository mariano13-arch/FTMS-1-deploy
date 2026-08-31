from rest_framework import serializers

from .models import (
    VALID_MODULE_ACTIONS,
    PermissionAction,
    StaffProfile,
)


class StrictFieldsSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError(
                {"non_field_errors": ["Expected a JSON object."]}
            )
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {field: ["Unknown field."] for field in sorted(unknown)}
            )
        return super().to_internal_value(data)


class LoginSerializer(StrictFieldsSerializer):
    username = serializers.CharField(trim_whitespace=False)
    password = serializers.CharField(trim_whitespace=False, write_only=True)

    def to_internal_value(self, data):
        errors = {
            field: ["Must be a string."]
            for field in self.fields
            if field in data and not isinstance(data[field], str)
        }
        if errors:
            raise serializers.ValidationError(errors)
        return super().to_internal_value(data)


class DriverPasswordSetupSerializer(StrictFieldsSerializer):
    uid = serializers.CharField(trim_whitespace=False)
    token = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False, write_only=True)
    confirm_password = serializers.CharField(trim_whitespace=False, write_only=True)

    def to_internal_value(self, data):
        errors = {
            field: ["Must be a string."]
            for field in self.fields
            if field in data and not isinstance(data[field], str)
        }
        if errors:
            raise serializers.ValidationError(errors)
        return super().to_internal_value(data)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": ["Passwords do not match."]}
            )
        return attrs


class ManagedStaffCreateSerializer(StrictFieldsSerializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=StaffProfile.Role.choices)


class ManagedStaffRoleSerializer(StrictFieldsSerializer):
    role = serializers.ChoiceField(choices=StaffProfile.Role.choices)


class ManagedStaffStatusSerializer(StrictFieldsSerializer):
    is_active = serializers.BooleanField()

    def to_internal_value(self, data):
        if (
            isinstance(data, dict)
            and "is_active" in data
            and type(data["is_active"]) is not bool
        ):
            raise serializers.ValidationError({"is_active": ["Must be a boolean."]})
        return super().to_internal_value(data)


class StaffPasswordSetupSerializer(DriverPasswordSetupSerializer):
    pass


class RolePermissionEntrySerializer(StrictFieldsSerializer):
    module = serializers.CharField()
    action = serializers.CharField()

    def validate(self, attrs):
        if attrs["module"] not in VALID_MODULE_ACTIONS:
            raise serializers.ValidationError({"module": ["Unknown module."]})
        if attrs["action"] not in PermissionAction.values:
            raise serializers.ValidationError({"action": ["Unknown action."]})
        if attrs["action"] not in VALID_MODULE_ACTIONS[attrs["module"]]:
            raise serializers.ValidationError(
                {"action": ["Action is not valid for the selected module."]}
            )
        return attrs


class RolePermissionReplaceSerializer(StrictFieldsSerializer):
    permissions = RolePermissionEntrySerializer(many=True)

    def validate_permissions(self, permissions):
        keys = [(item["module"], item["action"]) for item in permissions]
        if len(keys) != len(set(keys)):
            raise serializers.ValidationError(
                "Duplicate module/action permissions are not allowed."
            )
        return permissions
