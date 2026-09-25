from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from accounts.models import StaffProfile
from transport_requests import services
from transport_requests.models import TransportRequest

LOCATIONS = (
    (
        "Ninoy Aquino International Airport",
        "Oxford Suites Makati",
        "14.554700",
        "121.024400",
        "14.537800",
        "121.001400",
    ),
    ("Oxford Suites Makati", "SM Aura", "14.555700", "121.025400", "14.538800", "121.002400"),
    (
        "Pasay Logistics Hub",
        "Oxford Suites Makati",
        "14.556700",
        "121.026400",
        "14.539800",
        "121.003400",
    ),
    (
        "Oxford Suites Makati",
        "BGC Corporate Center",
        "14.557700",
        "121.027400",
        "14.540800",
        "121.004400",
    ),
    (
        "Oxford Suites Makati",
        "Oxford Suites Quezon City",
        "14.558700",
        "121.028400",
        "14.541800",
        "121.005400",
    ),
)

EXAMPLES = (
    ("AIRPORT_PICKUP", "PASSENGER_TRANSPORT", "HIGH", "APPROVED", 2, 2, "", None, None),
    ("GUEST_TRANSFER", "PASSENGER_TRANSPORT", "NORMAL", "FOR_APPROVAL", 4, 1, "", None, None),
    ("AIRPORT_DROPOFF", "PASSENGER_TRANSPORT", "NORMAL", "FOR_APPROVAL", 3, 2, "", None, None),
    ("VIP_TRANSPORT", "PASSENGER_TRANSPORT", "URGENT", "APPROVED", 2, 1, "", None, None),
    ("STAFF_SHUTTLE", "PASSENGER_TRANSPORT", "NORMAL", "NEEDS_MORE_DETAILS", 12, 0, "", None, None),
    ("GUEST_TRANSFER", "PASSENGER_TRANSPORT", "LOW", "FOR_APPROVAL", 5, 3, "", None, None),
    ("AIRPORT_PICKUP", "PASSENGER_TRANSPORT", "HIGH", "REJECTED", 1, 1, "", None, None),
    ("STAFF_SHUTTLE", "PASSENGER_TRANSPORT", "NORMAL", "FOR_APPROVAL", 18, 0, "", None, None),
    ("VIP_TRANSPORT", "PASSENGER_TRANSPORT", "HIGH", "CANCELLED", 3, 2, "", None, None),
    ("AIRPORT_DROPOFF", "PASSENGER_TRANSPORT", "NORMAL", "APPROVED", 4, 4, "", None, None),
    ("GUEST_TRANSFER", "PASSENGER_TRANSPORT", "NORMAL", "NEEDS_MORE_DETAILS", 6, 1, "", None, None),
    ("AIRPORT_PICKUP", "PASSENGER_TRANSPORT", "HIGH", "FOR_APPROVAL", 2, 2, "", None, None),
    (
        "SUPPLIER_PICKUP",
        "DELIVERY_LOGISTICS",
        "NORMAL",
        "FOR_APPROVAL",
        0,
        0,
        "Hotel linen supplies",
        24,
        None,
    ),
    (
        "FOOD_DELIVERY",
        "DELIVERY_LOGISTICS",
        "HIGH",
        "APPROVED",
        0,
        0,
        "Prepared meal trays",
        18,
        None,
    ),
    (
        "CATERING_DELIVERY",
        "DELIVERY_LOGISTICS",
        "HIGH",
        "NEEDS_MORE_DETAILS",
        0,
        0,
        "Banquet catering equipment",
        None,
        "185.00",
    ),
    (
        "BANQUET_LOGISTICS",
        "DELIVERY_LOGISTICS",
        "NORMAL",
        "FOR_APPROVAL",
        0,
        0,
        "Event staging materials",
        36,
        None,
    ),
    (
        "SUPPLIER_PICKUP",
        "DELIVERY_LOGISTICS",
        "LOW",
        "REJECTED",
        0,
        0,
        "Housekeeping consumables",
        40,
        None,
    ),
    (
        "FOOD_DELIVERY",
        "DELIVERY_LOGISTICS",
        "URGENT",
        "FOR_APPROVAL",
        0,
        0,
        "Temperature-sensitive desserts",
        12,
        "28.50",
    ),
    (
        "CATERING_DELIVERY",
        "DELIVERY_LOGISTICS",
        "NORMAL",
        "CANCELLED",
        0,
        0,
        "Dining service ware",
        None,
        "96.00",
    ),
    (
        "BRANCH_TRANSFER",
        "DELIVERY_LOGISTICS",
        "NORMAL",
        "FOR_APPROVAL",
        0,
        0,
        "Branch operating supplies",
        15,
        None,
    ),
)


class Command(BaseCommand):
    help = "Create idempotent, workflow-valid development transport request data."

    def handle(self, *args, **options):
        creator = (
            get_user_model()
            .objects.filter(is_staff=True, is_active=True)
            .filter(Q(is_superuser=True) | Q(staff_profile__role=StaffProfile.Role.FLEET_MANAGER))
            .order_by("pk")
            .first()
        )
        if not creator:
            raise CommandError(
                "Create an active Fleet Admin or Fleet Manager before seeding requests."
            )

        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        created_count = 0
        for index, example in enumerate(EXAMPLES, start=1):
            (
                request_type,
                category,
                priority,
                target,
                passenger_count,
                luggage_count,
                load_description,
                load_quantity,
                estimated_weight_kg,
            ) = example
            pickup, destination, pickup_lat, pickup_lng, destination_lat, destination_lng = (
                LOCATIONS[(index - 1) % len(LOCATIONS)]
            )
            request, created = TransportRequest.objects.get_or_create(
                source_system=TransportRequest.SourceSystem.MANUAL_STAFF_ENTRY,
                external_reference=f"DEV-SEED-{index:03d}",
                defaults={
                    "request_type": request_type,
                    "request_category": category,
                    "requester_name": "Development Operations",
                    "requester_contact": "+63 2 8000 0000",
                    "pickup_name": pickup,
                    "pickup_address": f"{pickup}, Metro Manila",
                    "pickup_latitude": pickup_lat,
                    "pickup_longitude": pickup_lng,
                    "destination_name": destination,
                    "destination_address": f"{destination}, Metro Manila",
                    "destination_latitude": destination_lat,
                    "destination_longitude": destination_lng,
                    "scheduled_pickup_at": now + timedelta(hours=index * 2),
                    "estimated_duration_minutes": 45 + (index % 4) * 15,
                    "passenger_count": passenger_count,
                    "luggage_count": luggage_count,
                    "load_description": load_description,
                    "load_quantity": load_quantity,
                    "estimated_weight_kg": estimated_weight_kg,
                    "handling_instructions": (
                        "Keep upright and protected from moisture."
                        if category == TransportRequest.RequestCategory.DELIVERY_LOGISTICS
                        else ""
                    ),
                    "temperature_requirement": (
                        "Keep chilled."
                        if request_type == TransportRequest.RequestType.FOOD_DELIVERY
                        else ""
                    ),
                    "priority": priority,
                    "notes": "Development-only transport request seed record.",
                    "created_by": creator,
                },
            )
            if created:
                services.record_event(request, "CREATED", creator)
                created_count += 1
            if request.status != TransportRequest.Status.FOR_APPROVAL:
                continue
            if target == TransportRequest.Status.APPROVED:
                services.approve(request, creator, "Approved development seed request.")
            elif target == TransportRequest.Status.NEEDS_MORE_DETAILS:
                services.request_more_details(
                    request, creator, "Confirm the remaining development fixture details."
                )
            elif target == TransportRequest.Status.REJECTED:
                services.reject(request, creator, "Rejected development seed request.")
            elif target == TransportRequest.Status.CANCELLED:
                services.cancel(request, creator, "Cancelled development seed request.")

        self.stdout.write(
            self.style.SUCCESS(f"Created {created_count}; {len(EXAMPLES)} seed records available.")
        )
