from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from fleet.models import Vehicle
from fleet.serializers import StrictFieldsMixin

from .domain import is_supply_request
from .execution import allowed_driver_actions
from .models import DispatchAssignment, DispatchExecutionEvent, TripExpenseReceipt
from .serializers import FlightContextSerializer

RECEIPT_IMAGE_MAX_BYTES = 5 * 1024 * 1024
RECEIPT_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png"}
RECEIPT_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png"}
MONEY_TOLERANCE = Decimal("0.05")


class DriverTripVehicleSerializer(serializers.ModelSerializer):
    vehicle_type_label = serializers.CharField(source="get_vehicle_type_display", read_only=True)

    class Meta:
        model = Vehicle
        fields = [
            "id", "display_name", "plate_number", "vehicle_type", "vehicle_type_label",
            "passenger_capacity", "payload_capacity_kg",
        ]


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


class DriverAssignmentAcceptanceSerializer(StrictFieldsMixin, serializers.Serializer):
    confirmed_at = serializers.DateTimeField()


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
    source = serializers.ChoiceField(choices=["GNSS", "CELLULAR_LBS", "SIMULATED_TEST"])


class DriverRoutePlaceSerializer(serializers.Serializer):
    name = serializers.CharField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()


class DriverActiveRouteSerializer(serializers.Serializer):
    phase = serializers.ChoiceField(
        choices=["TO_PICKUP", "TO_DESTINATION", "ARRIVED", "COMPLETED"]
    )
    execution_status = serializers.CharField()
    route_status = serializers.ChoiceField(
        choices=["AVAILABLE", "POSITION_UNAVAILABLE", "TEMPORARILY_UNAVAILABLE", "NOT_ACTIVE"]
    )
    position_state = serializers.ChoiceField(choices=["CURRENT", "STALE", "UNAVAILABLE"])
    position_recorded_at = serializers.DateTimeField(allow_null=True)
    position_age_seconds = serializers.IntegerField(min_value=0, allow_null=True)
    route_basis = serializers.ChoiceField(
        choices=["CURRENT_VEHICLE_POSITION", "LAST_KNOWN_VEHICLE_POSITION", "PICKUP"],
        allow_null=True,
    )
    vehicle_position = DriverVehiclePositionSerializer(allow_null=True)
    pickup = DriverRoutePlaceSerializer()
    destination = DriverRoutePlaceSerializer()
    route = DriverRouteSerializer(allow_null=True)
    planned_route_status = serializers.ChoiceField(
        choices=["AVAILABLE", "TEMPORARILY_UNAVAILABLE", "NOT_APPLICABLE"]
    )
    planned_route = DriverRouteSerializer(allow_null=True)


class DriverTripSerializer(serializers.ModelSerializer):
    is_accepted = serializers.SerializerMethodField()
    assignment_confirmed_at = serializers.DateTimeField(source="confirmed_at", read_only=True)
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
    flight_context = FlightContextSerializer(
        source="transport_request.flight_context", read_only=True, allow_null=True
    )
    capacity_compatibility = serializers.SerializerMethodField()

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
            "is_accepted",
            "accepted_at",
            "assignment_confirmed_at",
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
            "flight_context",
            "capacity_compatibility",
            "execution",
        ]

    def get_pickup(self, assignment):
        item = assignment.transport_request
        return {"name": item.pickup_name, "address": item.pickup_address}

    def get_is_accepted(self, assignment):
        return assignment.accepted_at is not None

    def get_destination(self, assignment):
        item = assignment.transport_request
        return {"name": item.destination_name, "address": item.destination_address}

    def get_capacity_compatibility(self, assignment):
        item = assignment.transport_request
        if not is_supply_request(item):
            return {"status": "NOT_APPLICABLE", "message": "Passenger capacity rules apply."}
        if item.estimated_weight_kg is None:
            return {"status": "NOT_EVALUATED", "message": "Load weight is not recorded."}
        if assignment.vehicle.payload_capacity_kg is None:
            return {"status": "UNKNOWN", "message": "Vehicle payload capacity is not recorded."}
        compatible = assignment.vehicle.payload_capacity_kg >= item.estimated_weight_kg
        return {
            "status": "COMPATIBLE" if compatible else "INCOMPATIBLE",
            "message": (
                "Vehicle payload capacity covers the estimated load weight."
                if compatible
                else "Estimated load weight exceeds vehicle payload capacity."
            ),
        }


class DriverReceiptSerializer(serializers.ModelSerializer):
    assignment_id = serializers.IntegerField(source="dispatch_assignment_id", read_only=True)
    trip_id = serializers.UUIDField(
        source="dispatch_assignment.transport_request_id", read_only=True
    )
    vehicle_display = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    duplicate_warning = serializers.SerializerMethodField()

    class Meta:
        model = TripExpenseReceipt
        fields = [
            "id",
            "expense_type",
            "assignment_id",
            "trip_id",
            "vehicle_display",
            "transaction_at",
            "amount",
            "receipt_number",
            "merchant_or_operator",
            "liters",
            "unit_price",
            "fuel_type",
            "fuel_grade",
            "toll_plaza",
            "confirmed_at",
            "created_at",
            "image_url",
            "duplicate_warning",
        ]

    def get_vehicle_display(self, receipt):
        return f"{receipt.vehicle.display_name} · {receipt.vehicle.plate_number}"

    def get_image_url(self, receipt):
        return f"/api/v1/driver-receipts/{receipt.pk}/image/"

    def get_duplicate_warning(self, receipt):
        return bool(getattr(receipt, "_duplicate_warning", False))


class DriverReceiptCreateSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = TripExpenseReceipt
        fields = [
            "expense_type",
            "transaction_at",
            "amount",
            "receipt_number",
            "merchant_or_operator",
            "receipt_image",
            "liters",
            "unit_price",
            "fuel_type",
            "fuel_grade",
            "toll_plaza",
        ]
        extra_kwargs = {"receipt_image": {"write_only": True}}

    def validate_receipt_image(self, value):
        extension = value.name.rsplit(".", 1)[-1].lower() if "." in value.name else ""
        if (
            value.content_type not in RECEIPT_IMAGE_CONTENT_TYPES
            or extension not in RECEIPT_IMAGE_EXTENSIONS
        ):
            raise serializers.ValidationError("Only JPEG and PNG receipt images are allowed.")
        if value.size > RECEIPT_IMAGE_MAX_BYTES:
            raise serializers.ValidationError("Receipt image must not exceed 5 MB.")
        return value

    def validate_transaction_at(self, value):
        if value > timezone.now():
            raise serializers.ValidationError("Transaction date/time cannot be in the future.")
        return value

    def validate(self, attrs):
        errors = {}
        for field in ("driver", "vehicle", "dispatch_assignment", "confirmed_at"):
            if field in self.initial_data:
                errors[field] = "This field is not accepted."
        expense_type = attrs.get("expense_type")
        fuel_fields = ("liters", "unit_price", "fuel_type", "fuel_grade")
        if expense_type == TripExpenseReceipt.ExpenseType.TOLL:
            for field in fuel_fields:
                value = attrs.get(field)
                if value not in (None, ""):
                    errors[field] = "Fuel-specific fields are not accepted for toll receipts."
        if expense_type == TripExpenseReceipt.ExpenseType.FUEL:
            fuel_type = attrs.get("fuel_type", "")
            fuel_grade = attrs.get("fuel_grade", "")
            allowed_grades = {
                Vehicle.FuelType.GASOLINE: {
                    "",
                    Vehicle.FuelGrade.UNLEADED_91,
                    Vehicle.FuelGrade.PREMIUM_95,
                    Vehicle.FuelGrade.PREMIUM_97,
                },
                Vehicle.FuelType.DIESEL: {
                    "",
                    Vehicle.FuelGrade.REGULAR_DIESEL,
                    Vehicle.FuelGrade.PREMIUM_DIESEL,
                },
                "": {""},
            }
            if fuel_grade not in allowed_grades.get(fuel_type, set()):
                errors["fuel_grade"] = "Fuel grade is not compatible with the selected fuel type."
            liters = attrs.get("liters")
            unit_price = attrs.get("unit_price")
            amount = attrs.get("amount")
            if liters is not None and unit_price is not None and amount is not None:
                computed = (liters * unit_price).quantize(Decimal("0.01"))
                if abs(computed - amount) > MONEY_TOLERANCE:
                    errors["amount"] = "Amount is inconsistent with liters and unit price."
        if expense_type == TripExpenseReceipt.ExpenseType.TOLL and not attrs.get("toll_plaza"):
            attrs["toll_plaza"] = ""
        for field in ("receipt_number", "merchant_or_operator", "toll_plaza"):
            if field in attrs and isinstance(attrs[field], str):
                attrs[field] = attrs[field].strip()
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class DriverReceiptOcrPreviewSerializer(StrictFieldsMixin, serializers.Serializer):
    expense_type = serializers.ChoiceField(choices=TripExpenseReceipt.ExpenseType.choices)
    receipt_image = serializers.FileField(write_only=True)

    def validate_receipt_image(self, value):
        return DriverReceiptCreateSerializer().validate_receipt_image(value)
