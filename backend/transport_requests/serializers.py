from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from fleet.models import Driver, Vehicle
from fleet.serializers import StrictFieldsMixin

from .domain import validate_request_semantics
from .models import (
    DispatchAssignment,
    DispatchPlan,
    DispatchPlanStop,
    TransportRequest,
    TransportRequestEvent,
    TransportRequestFlightContext,
)
from .services import planning_end, record_event

BASE_FIELDS = [
    "id",
    "request_number",
    "source_system",
    "external_reference",
    "request_type",
    "request_category",
    "requester_name",
    "requester_contact",
    "pickup_name",
    "pickup_address",
    "pickup_latitude",
    "pickup_longitude",
    "destination_name",
    "destination_address",
    "destination_latitude",
    "destination_longitude",
    "scheduled_pickup_at",
    "required_vehicle_type",
    "estimated_duration_minutes",
    "passenger_count",
    "luggage_count",
    "load_description",
    "load_quantity",
    "estimated_weight_kg",
    "handling_instructions",
    "temperature_requirement",
    "priority",
    "notes",
    "status",
    "assigned_vehicle",
    "created_by",
    "approved_by",
    "approved_at",
    "created_at",
    "updated_at",
    "flight_context",
]
IMMUTABLE_FIELDS = {
    "id",
    "request_number",
    "status",
    "assigned_vehicle",
    "created_by",
    "approved_by",
    "approved_at",
    "created_at",
    "updated_at",
    "events",
}


class FlightContextSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = TransportRequestFlightContext
        fields = [
            "provider",
            "flight_number",
            "flight_date",
            "origin_airport",
            "arrival_airport",
            "terminal",
            "scheduled_arrival_at",
            "estimated_arrival_at",
            "actual_arrival_at",
            "provider_flight_status",
            "refresh_status",
            "last_refresh_attempt_at",
            "last_successful_refresh_at",
            "refresh_message",
        ]
        read_only_fields = [
            "provider",
            "estimated_arrival_at",
            "actual_arrival_at",
            "provider_flight_status",
            "refresh_status",
            "last_refresh_attempt_at",
            "last_successful_refresh_at",
            "refresh_message",
        ]

    def validate_flight_number(self, value):
        normalized = value.strip().upper()
        if not normalized:
            raise serializers.ValidationError("Must not be blank.")
        return normalized


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
            "id",
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
    flight_context = FlightContextSerializer(required=False, allow_null=True)

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
            "load_description",
            "handling_instructions",
            "temperature_requirement",
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
        external = attrs.get("external_reference", getattr(self.instance, "external_reference", ""))
        semantic_values = {
            field: attrs.get(field, getattr(self.instance, field, None))
            for field in (
                "request_type",
                "request_category",
                "passenger_count",
                "load_description",
                "load_quantity",
                "estimated_weight_kg",
            )
        }
        resolved_category, semantic_errors = validate_request_semantics(semantic_values)
        errors.update(semantic_errors)
        if resolved_category and "request_category" not in semantic_errors:
            attrs["request_category"] = resolved_category
        if source and external:
            duplicate = TransportRequest.objects.filter(
                source_system=source, external_reference=external
            )
            if self.instance:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                errors["external_reference"] = "This subsystem request has already been imported."
        flight_context = attrs.get("flight_context", serializers.empty)
        request_type = attrs.get("request_type", getattr(self.instance, "request_type", None))
        if (
            flight_context not in (serializers.empty, None)
            and request_type != TransportRequest.RequestType.AIRPORT_PICKUP
        ):
            errors["flight_context"] = "Flight context is only valid for airport pickup requests."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        user = self.context["request"].user
        flight_context = validated_data.pop("flight_context", None)
        try:
            request = TransportRequest.objects.create(created_by=user, **validated_data)
        except IntegrityError as error:
            raise serializers.ValidationError(
                {"external_reference": "This subsystem request has already been imported."}
            ) from error
        if flight_context:
            TransportRequestFlightContext.objects.create(
                transport_request=request, **flight_context
            )
        record_event(request, "CREATED", user)
        return request

    @transaction.atomic
    def update(self, instance, validated_data):
        previous = instance.status
        flight_context = validated_data.pop("flight_context", serializers.empty)
        request = super().update(instance, validated_data)
        if request.request_type != TransportRequest.RequestType.AIRPORT_PICKUP:
            TransportRequestFlightContext.objects.filter(transport_request=request).delete()
        elif flight_context is not serializers.empty:
            if flight_context is None:
                TransportRequestFlightContext.objects.filter(transport_request=request).delete()
            else:
                TransportRequestFlightContext.objects.update_or_create(
                    transport_request=request, defaults=flight_context
                )
        record_event(request, "EDITED", self.context["request"].user, previous)
        return request


class TransportRequestListSerializer(TransportRequestBaseSerializer):
    latest_event_type = serializers.CharField(read_only=True, allow_null=True)
    latest_event_at = serializers.DateTimeField(read_only=True, allow_null=True)

    class Meta(TransportRequestBaseSerializer.Meta):
        fields = BASE_FIELDS + [
            "latest_event_type",
            "latest_event_at",
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
            "calendar_date",
            "planning_end_at",
            "vehicle_conflict",
            "conflicting_requests",
        ]

    def get_calendar_date(self, request):
        return request.scheduled_pickup_at.astimezone(timezone.get_current_timezone()).date()

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


class DispatchDriverSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    eligibility_status = serializers.SerializerMethodField()

    class Meta:
        model = Driver
        fields = ["id", "driver_code", "full_name", "eligibility_status"]

    def get_full_name(self, driver):
        from fleet.schedules import compact_driver_name

        return compact_driver_name(driver)

    def get_eligibility_status(self, driver):
        from fleet.serializers import driver_eligibility

        return driver_eligibility(driver)[0]


class DispatchAssignmentSerializer(serializers.ModelSerializer):
    transport_request_id = serializers.UUIDField(read_only=True)
    request_number = serializers.CharField(
        source="transport_request.request_number", read_only=True
    )
    vehicle = AssignedVehicleSerializer(read_only=True)
    driver = DispatchDriverSerializer(read_only=True)
    confirmed_by = serializers.SerializerMethodField()
    is_accepted = serializers.SerializerMethodField()
    execution_status_label = serializers.CharField(
        source="get_execution_status_display", read_only=True
    )

    class Meta:
        model = DispatchAssignment
        fields = [
            "id",
            "plan_id",
            "transport_request_id",
            "request_number",
            "vehicle",
            "driver",
            "selection_mode",
            "override_reason",
            "confirmed_by",
            "confirmed_at",
            "is_accepted",
            "accepted_at",
            "execution_status",
            "execution_status_label",
            "completed_at",
            "created_at",
            "updated_at",
        ]

    def get_confirmed_by(self, assignment):
        user = assignment.confirmed_by
        return user.get_full_name().strip() or user.username

    def get_is_accepted(self, assignment):
        return assignment.accepted_at is not None


class OperationalAssignmentSerializer(DispatchAssignmentSerializer):
    transport_request = TransportRequestListSerializer(read_only=True)

    class Meta(DispatchAssignmentSerializer.Meta):
        fields = [*DispatchAssignmentSerializer.Meta.fields, "transport_request"]


class DispatchConfirmationSerializer(StrictFieldsMixin, serializers.Serializer):
    transport_request_id = serializers.UUIDField()
    vehicle_id = serializers.IntegerField(min_value=1)
    driver_id = serializers.IntegerField(min_value=1)
    selection_mode = serializers.ChoiceField(choices=DispatchAssignment.SelectionMode.choices)
    override_reason = serializers.CharField(
        required=False, allow_blank=True, max_length=1000, default=""
    )
    recommendation_token = serializers.CharField(required=False, allow_blank=True, default="")


class DispatchPlanStopSerializer(serializers.ModelSerializer):
    request_number = serializers.CharField(
        source="transport_request.request_number", read_only=True
    )
    label = serializers.SerializerMethodField()

    class Meta:
        model = DispatchPlanStop
        fields = ["sequence", "transport_request_id", "request_number", "stop_type", "label"]

    def get_label(self, stop):
        if stop.stop_type == DispatchPlanStop.StopType.PICKUP:
            return stop.transport_request.pickup_name
        return stop.transport_request.destination_name


class DispatchPlanSerializer(serializers.ModelSerializer):
    vehicle = AssignedVehicleSerializer(read_only=True)
    driver = DispatchDriverSerializer(read_only=True)
    stops = DispatchPlanStopSerializer(many=True, read_only=True)
    confirmed_by = serializers.SerializerMethodField()

    class Meta:
        model = DispatchPlan
        fields = [
            "id", "plan_type", "vehicle", "driver", "stops", "confirmed_by",
            "confirmed_at", "created_at", "updated_at",
        ]

    def get_confirmed_by(self, plan):
        return plan.confirmed_by.get_full_name().strip() or plan.confirmed_by.username
