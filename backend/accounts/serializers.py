from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(trim_whitespace=False)
    password = serializers.CharField(trim_whitespace=False, write_only=True)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError({"non_field_errors": ["Expected a JSON object."]})
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {field: ["Unknown field."] for field in sorted(unknown)}
            )
        errors = {
            field: ["Must be a string."]
            for field in self.fields
            if field in data and not isinstance(data[field], str)
        }
        if errors:
            raise serializers.ValidationError(errors)
        return super().to_internal_value(data)
