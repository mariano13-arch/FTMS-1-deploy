from rest_framework import serializers

from .serializers import TransportRequestDetailSerializer


class TrustedTransportRequestSerializer(TransportRequestDetailSerializer):
    external_reference = serializers.CharField(
        max_length=120,
        allow_blank=False,
        trim_whitespace=True,
    )
    source_system = serializers.CharField(read_only=True)

    def validate(self, attrs):
        if "source_system" in self.initial_data:
            raise serializers.ValidationError(
                {"source_system": "Source system is determined by the integration credential."}
            )
        attrs["source_system"] = self.context["integration_client"].source_system
        return super().validate(attrs)
