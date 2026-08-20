from rest_framework import serializers

from fleet.models import Vehicle
from fleet.serializers import StrictFieldsMixin

from .execution import allowed_driver_actions
from .models import DispatchAssignment, DispatchExecutionEvent


class DriverTripVehicleSerializer(serializers.ModelSerializer):
    vehicle_type_label = serializers.CharField(source="get_vehicle_type_display", read_only=True)

    class Meta:
        model = Vehicle
        fields = ["id", "display_name", "plate_number", "vehicle_type", "vehicle_type_label"]


class DriverExecutionSerializer(serializers.ModelSerializer):
    assignment_id = serializers.IntegerField(source="pk", read_only=True)
    trip_id = serializers.UUIDField(source="transport_request_id", read_only=True)
    status = serializers.CharField(source="execution_status", read_only=True)
    status_label = serializers.CharField(source="get_execution_status_display", read_only=True)
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = DispatchAssignment
        fields = [
            "assignment_id",
            "trip_id",
            "status",
            "status_label",
            "allowed_actions",
            "execution_started_at",
            "pickup_arrived_at",
            "pickup_departed_at",
            "destination_arrived_at",
            "completed_at",
        ]

    def get_allowed_actions(self, assignment):
        return allowed_driver_actions(assignment)


class DriverExecutionTransitionSerializer(StrictFieldsMixin, serializers.Serializer):
    action = serializers.ChoiceField(choices=DispatchExecutionEvent.Action.choices)


class DriverRouteGeometrySerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["LineString"])
    coordinates = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2),
        min_length=2,
    )


class DriverRouteSerializer(serializers.Serializer):
    geometry = DriverRouteGeometrySerializer()
    distance_meters = serializers.IntegerField(min_value=0)
    duration_seconds = serializers.IntegerField(min_value=0)
    traffic_delay_seconds = serializers.IntegerField(min_value=0)
    departure_time = serializers.CharField()
    arrival_time = serializers.CharField()
    traffic_mode = serializers.ChoiceField(choices=["live"])


class DriverVehiclePositionSerializer(serializers.Serializer):
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    recorded_at = serializers.DateTimeField()
    is_stale = serializers.BooleanField()


class DriverTripSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="transport_request_id", read_only=True)
    request_number = serializers.CharField(
        source="transport_request.request_number", read_only=True
    )
    request_type = serializers.CharField(source="transport_request.request_type", read_only=True)
    request_type_label = serializers.CharField(
        source="transport_request.get_request_type_display", read_only=True
    )
    request_category = serializers.CharField(
        source="transport_request.request_category", read_only=True, allow_null=True
    )
    request_category_label = serializers.CharField(
        source="transport_request.get_request_category_display",
        read_only=True,
        allow_null=True,
    )
    priority = serializers.CharField(source="transport_request.priority", read_only=True)
    priority_label = serializers.CharField(
        source="transport_request.get_priority_display", read_only=True
    )
    status = serializers.CharField(source="transport_request.status", read_only=True)
    status_label = serializers.CharField(
        source="transport_request.get_status_display", read_only=True
    )
    scheduled_pickup_at = serializers.DateTimeField(
        source="transport_request.scheduled_pickup_at", read_only=True
    )
    estimated_duration_minutes = serializers.IntegerField(
        source="transport_request.estimated_duration_minutes", read_only=True
    )
    passenger_count = serializers.IntegerField(
        source="transport_request.passenger_count", read_only=True
    )
    luggage_count = serializers.IntegerField(
        source="transport_request.luggage_count", read_only=True
    )
    pickup = serializers.SerializerMethodField()
    destination = serializers.SerializerMethodField()
    vehicle = DriverTripVehicleSerializer(read_only=True)
    handling_instructions = serializers.CharField(
        source="transport_request.handling_instructions", read_only=True
    )
    load_description = serializers.CharField(
        source="transport_request.load_description", read_only=True
    )
    load_quantity = serializers.IntegerField(
        source="transport_request.load_quantity", read_only=True, allow_null=True
    )
    estimated_weight_kg = serializers.DecimalField(
        source="transport_request.estimated_weight_kg",
        max_digits=10,
        decimal_places=2,
        read_only=True,
        allow_null=True,
    )
    temperature_requirement = serializers.CharField(
        source="transport_request.temperature_requirement", read_only=True
    )
    execution = DriverExecutionSerializer(source="*", read_only=True)

    class Meta:
        model = DispatchAssignment
        fields = [
            "id",
            "request_number",
            "request_type",
            "request_type_label",
            "request_category",
            "request_category_label",
            "priority",
            "priority_label",
            "status",
            "status_label",
            "scheduled_pickup_at",
            "estimated_duration_minutes",
            "passenger_count",
            "luggage_count",
            "pickup",
            "destination",
            "vehicle",
            "handling_instructions",
            "load_description",
            "load_quantity",
            "estimated_weight_kg",
            "temperature_requirement",
            "execution",
        ]

    def get_pickup(self, assignment):
        item = assignment.transport_request
        return {"name": item.pickup_name, "address": item.pickup_address}

    def get_destination(self, assignment):
        item = assignment.transport_request
        return {"name": item.destination_name, "address": item.destination_address}
