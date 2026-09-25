import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from .models import DispatchAssignment, IntegrationClient, SourceResultOutbox, TransportRequest

TRUSTED_SOURCE_SYSTEMS = frozenset(
    {
        TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
        TransportRequest.SourceSystem.RESTAURANT_MANAGEMENT_SYSTEM,
        TransportRequest.SourceSystem.SUPPLY_CHAIN_MANAGEMENT_SYSTEM,
    }
)

SOURCE_INGESTION_FIELDS = (
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
)


def _new_credential():
    key_identifier = secrets.token_urlsafe(12)
    secret = secrets.token_urlsafe(32)
    return key_identifier, f"{key_identifier}.{secret}"


@transaction.atomic
def create_integration_client(*, name, source_system):
    if source_system not in TRUSTED_SOURCE_SYSTEMS:
        raise ValueError(
            "Integration clients are limited to trusted HMS, RMS, and supply-chain sources."
        )
    key_identifier, credential = _new_credential()
    user_model = get_user_model()
    user = user_model(username=f"integration-{key_identifier}", is_active=True)
    user.set_unusable_password()
    user.save()
    client = IntegrationClient.objects.create(
        name=name.strip(),
        source_system=source_system,
        user=user,
        key_identifier=key_identifier,
        credential_hash=make_password(credential),
    )
    return client, credential


def credential_matches(client, credential):
    return check_password(credential, client.credential_hash)


@transaction.atomic
def rotate_integration_credential(client):
    current = IntegrationClient.objects.select_for_update().get(pk=client.pk)
    key_identifier, credential = _new_credential()
    current.key_identifier = key_identifier
    current.credential_hash = make_password(credential)
    current.rotated_at = timezone.now()
    current.save(
        update_fields=["key_identifier", "credential_hash", "rotated_at", "updated_at"]
    )
    return current, credential


def ingestion_values_match(instance, validated_data):
    flight_context = validated_data.get("flight_context", None)
    for field_name in SOURCE_INGESTION_FIELDS:
        if field_name in validated_data:
            expected = validated_data[field_name]
        else:
            field = TransportRequest._meta.get_field(field_name)
            expected = field.get_default() if field.has_default() else None
        if getattr(instance, field_name) != expected:
            return False
    if flight_context is not None:
        try:
            existing_flight = instance.flight_context
        except ObjectDoesNotExist:
            return False
        for field_name, expected in flight_context.items():
            if getattr(existing_flight, field_name) != expected:
                return False
    elif hasattr(instance, "flight_context"):
        return False
    return True


def derived_source_status(item):
    try:
        assignment = item.dispatch_assignment
    except DispatchAssignment.DoesNotExist:
        assignment = None
    if (
        assignment is not None
        and assignment.execution_status == DispatchAssignment.ExecutionStatus.COMPLETED
    ):
        return "COMPLETED"
    if item.status == TransportRequest.Status.REJECTED:
        return "REJECTED"
    if item.status == TransportRequest.Status.CANCELLED:
        return "CANCELLED"
    if item.status == TransportRequest.Status.NEEDS_MORE_DETAILS:
        return "NEEDS_MORE_DETAILS"
    if item.status == TransportRequest.Status.FOR_APPROVAL:
        return "RECEIVED"

    if assignment is not None:
        if assignment.execution_status in {
            DispatchAssignment.ExecutionStatus.EN_ROUTE_TO_PICKUP,
            DispatchAssignment.ExecutionStatus.AT_PICKUP,
            DispatchAssignment.ExecutionStatus.IN_TRANSIT,
            DispatchAssignment.ExecutionStatus.AT_DESTINATION,
        }:
            return "IN_PROGRESS"
        if assignment.accepted_at is not None:
            return "DRIVER_ACCEPTED"
        if item.status == TransportRequest.Status.READY_FOR_DISPATCH:
            return "READY_FOR_DISPATCH"
        return "ASSIGNED"

    if item.status == TransportRequest.Status.READY_FOR_DISPATCH:
        return "READY_FOR_DISPATCH"
    return "APPROVED"


def source_result(item):
    try:
        assignment = item.dispatch_assignment
    except DispatchAssignment.DoesNotExist:
        assignment = None
    status = derived_source_status(item)
    rejection_note = None
    if status == "REJECTED":
        event = item.events.filter(event_type="REJECTED").order_by("-created_at", "-pk").first()
        rejection_note = event.note if event and event.note else None
    delivery = item.source_result_outbox.filter(event_type="TRIP_COMPLETED").first()
    delivery_status = (
        delivery.delivery_status
        if delivery is not None
        else SourceResultOutbox.DeliveryStatus.UNCONFIGURED
    )
    return {
        "ftms_request_id": str(item.pk),
        "request_number": item.request_number,
        "external_reference": item.external_reference,
        "source_system": item.source_system,
        "status": status,
        "request_status": item.status,
        "execution_status": assignment.execution_status if assignment else None,
        "completion_timestamp": assignment.completed_at if status == "COMPLETED" else None,
        "rejection_note": rejection_note,
        "result_delivery": {
            "status": delivery_status,
            "attempts": delivery.delivery_attempts if delivery is not None else 0,
            "delivered_at": delivery.delivered_at if delivery is not None else None,
            "last_error": delivery.last_error if delivery is not None else "",
            "message": (
                "No source callback contract is configured; poll this result endpoint."
                if delivery_status == SourceResultOutbox.DeliveryStatus.UNCONFIGURED
                else "Completion delivery state is recorded in the FTMS outbox."
            ),
        },
    }
