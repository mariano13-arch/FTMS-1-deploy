from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .integration_authentication import (
    IntegrationBearerAuthentication,
    IntegrationClientAccess,
)
from .integration_serializers import TrustedTransportRequestSerializer
from .models import TransportRequest
from .source_integration import ingestion_values_match, source_result


class IntegrationView(APIView):
    authentication_classes = [IntegrationBearerAuthentication]
    permission_classes = [IntegrationClientAccess]


class SourceTransportRequestCreateView(IntegrationView):
    http_method_names = ["post", "options"]

    def post(self, request):
        if not isinstance(request.data, dict):
            raise serializers.ValidationError("A JSON object is required.")
        external_reference = request.data.get("external_reference")
        normalized_reference = (
            external_reference.strip() if isinstance(external_reference, str) else ""
        )
        existing = None
        if normalized_reference:
            existing = TransportRequest.objects.filter(
                source_system=request.auth.source_system,
                external_reference=normalized_reference,
            ).first()
        serializer = TrustedTransportRequestSerializer(
            existing,
            data=request.data,
            context={
                "request": request,
                "integration_client": request.auth,
            },
        )
        serializer.is_valid(raise_exception=True)
        if existing is not None:
            if not ingestion_values_match(existing, serializer.validated_data):
                return Response(
                    {
                        "detail": (
                            "This source reference already exists with different request data."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            return Response(source_result(existing), status=status.HTTP_200_OK)
        try:
            item = serializer.save()
        except serializers.ValidationError:
            # The database uniqueness constraint remains the race-safe authority.
            existing = TransportRequest.objects.filter(
                source_system=request.auth.source_system,
                external_reference=normalized_reference,
            ).first()
            if existing is None:
                raise
            if not ingestion_values_match(existing, serializer.validated_data):
                return Response(
                    {
                        "detail": (
                            "This source reference already exists with different request data."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            return Response(source_result(existing), status=status.HTTP_200_OK)
        return Response(source_result(item), status=status.HTTP_201_CREATED)


class SourceTransportRequestResultView(IntegrationView):
    http_method_names = ["get", "options"]

    def get(self, request, external_reference):
        item = get_object_or_404(
            TransportRequest.objects.select_related("dispatch_assignment").prefetch_related(
                "events"
            ),
            source_system=request.auth.source_system,
            external_reference=external_reference,
        )
        return Response(source_result(item))
