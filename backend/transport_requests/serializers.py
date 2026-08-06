from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from fleet.models import Vehicle
from fleet.serializers import StrictFieldsMixin

from .models import TransportRequest, TransportRequestEvent
from .services import planning_end, record_event

BASE_FIELDS = [
    "id", "request_number", "source_system", "external_reference", "request_type",
    "requester_name", "requester_contact", "pickup_name", "pickup_address",
    "pickup_latitude", "pickup_longitude", "destination_name", "destination_address",
    "destination_latitude", "destination_longitude", "scheduled_pickup_at",
    "required_vehicle_type", "estimated_duration_minutes", "passenger_count",
    "luggage_count", "priority", "notes", "status", "assigned_vehicle", "created_by",
    "approved_by", "approved_at", "created_at", "updated_at",
]
IMMUTABLE_FIELDS = {
    "id", "request_number", "status", "assigned_vehicle", "created_by", "approved_by",
    "approved_at", "created_at", "updated_at", "events",
}


class EventSerializer(serializers.ModelSerializer):
    performed_by = serializers.SerializerMethodField()

    class Meta:
        model = TransportRequestEvent
        fields = [
            "id",
            "event_type",
            "previous_status",
            "new_status",
            "performed_by",
            "note",
            "created_at",
        ]

    def get_performed_by(self, event):
        return event.performed_by.get_full_name().strip() or event.performed_by.username


class AssignedVehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = [
            "device_id",
            "plate_number",
            "display_name",
            "vehicle_type",
            "passenger_capacity",
            "is_active",
        ]


class TransportRequestBaseSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    assigned_vehicle = AssignedVehicleSerializer(read_only=True)
    created_by = serializers.SerializerMethodField()
    approved_by = serializers.SerializerMethodField()

    immutable_fields = IMMUTABLE_FIELDS

    class Meta:
        model = TransportRequest
        validators = []
        fields = BASE_FIELDS
        read_only_fields = list(IMMUTABLE_FIELDS)

    def get_created_by(self, request):
        return request.created_by.get_full_name().strip() or request.created_by.username

    def get_approved_by(self, request):
        if not request.approved_by:
            return None
        return request.approved_by.get_full_name().strip() or request.approved_by.username

    def validate(self, attrs):
        attrs = super().validate(attrs)
        immutable_errors = {
            field: "This field is read-only."
            for field in self.immutable_fields
            if field in self.initial_data
        }
        if immutable_errors:
            raise serializers.ValidationError(immutable_errors)
        for field in (
            "external_reference",
            "requester_name",
            "requester_contact",
            "pickup_name",
            "pickup_address",
            "destination_name",
            "destination_address",
            "notes",
        ):
            if field in attrs:
                attrs[field] = attrs[field].strip()
        required_text = (
            "requester_name",
            "pickup_name",
            "pickup_address",
            "destination_name",
            "destination_address",
        )
        errors = {
            field: "Must not be blank."
            for field in required_text
            if field in attrs and not attrs[field]
        }
        source = attrs.get("source_system", getattr(self.instance, "source_system", None))
        external = attrs.get(
            "external_reference", getattr(self.instance, "external_reference", "")
        )
        if source and external:
            duplicate = TransportRequest.objects.filter(
                source_system=source, external_reference=external
            )
            if self.instance:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                errors["external_reference"] = (
                    "This subsystem request has already been imported."
                )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        user = self.context["request"].user
        try:
            request = TransportRequest.objects.create(created_by=user, **validated_data)
        except IntegrityError as error:
            raise serializers.ValidationError({
                "external_reference": "This subsystem request has already been imported."
            }) from error
        record_event(request, "CREATED", user)
        return request

    @transaction.atomic
    def update(self, instance, validated_data):
        previous = instance.status
        request = super().update(instance, validated_data)
        record_event(request, "EDITED", self.context["request"].user, previous)
        return request


class TransportRequestListSerializer(TransportRequestBaseSerializer):
    latest_event_type = serializers.CharField(read_only=True, allow_null=True)
    latest_event_at = serializers.DateTimeField(read_only=True, allow_null=True)

    class Meta(TransportRequestBaseSerializer.Meta):
        fields = BASE_FIELDS + [
            "latest_event_type", "latest_event_at",
        ]


class TransportRequestDetailSerializer(TransportRequestBaseSerializer):
    events = EventSerializer(many=True, read_only=True)

    class Meta(TransportRequestBaseSerializer.Meta):
        fields = BASE_FIELDS + ["events"]


class CalendarTransportRequestSerializer(TransportRequestBaseSerializer):
    calendar_date = serializers.SerializerMethodField()
    planning_end_at = serializers.SerializerMethodField()
    vehicle_conflict = serializers.SerializerMethodField()
    conflicting_requests = serializers.SerializerMethodField()

    class Meta(TransportRequestBaseSerializer.Meta):
        fields = BASE_FIELDS + [
            "calendar_date", "planning_end_at", "vehicle_conflict",
            "conflicting_requests",
        ]

    def get_calendar_date(self, request):
        return request.scheduled_pickup_at.astimezone(
            timezone.get_current_timezone()
        ).date()

    def get_planning_end_at(self, request):
        return planning_end(request)

    def get_vehicle_conflict(self, request):
        return bool(self.context.get("conflicts", {}).get(request.pk))

    def get_conflicting_requests(self, request):
        return self.context.get("conflicts", {}).get(request.pk, [])


class NoteSerializer(StrictFieldsMixin, serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")


class VehicleAssignmentSerializer(NoteSerializer):
    vehicle_device_id = serializers.CharField(max_length=64)
