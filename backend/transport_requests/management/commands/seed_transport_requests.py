from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from accounts.models import StaffProfile
from fleet.models import Vehicle
from transport_requests import services
from transport_requests.models import TransportRequest


class Command(BaseCommand):
    help = "Create idempotent, workflow-valid Sprint 4 transport request data."

    def handle(self, *args, **options):
        creator = (
            get_user_model().objects.filter(is_staff=True, is_active=True)
            .filter(
                Q(is_superuser=True)
                | Q(staff_profile__role=StaffProfile.Role.FLEET_MANAGER)
            )
            .order_by("pk")
            .first()
        )
        if not creator:
            raise CommandError(
                "Create an active Super Admin or Fleet Manager before seeding requests."
            )
        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        examples = [
            {
                "external": "SEED-AIRPORT-001", "kind": "AIRPORT_PICKUP",
                "pickup": "Ninoy Aquino International Airport",
                "destination": "Oxford Suites Makati", "priority": "HIGH",
                "target": "APPROVED", "passengers": 2, "luggage": 2, "hours": 2,
                "duration": 75, "assign": False,
            },
            {
                "external": "SEED-GUEST-001", "kind": "GUEST_TRANSFER",
                "pickup": "Oxford Suites Makati", "destination": "SM Aura",
                "priority": "NORMAL", "target": "FOR_APPROVAL", "passengers": 4,
                "luggage": 1, "hours": 5, "duration": 60, "assign": False,
            },
            {
                "external": "SEED-SUPPLIER-001", "kind": "SUPPLIER_PICKUP",
                "pickup": "Pasay Logistics Hub", "destination": "Oxford Suites Makati",
                "priority": "NORMAL", "target": "READY_FOR_DISPATCH", "passengers": 1,
                "luggage": 3, "hours": 8, "duration": 90, "assign": True,
            },
            {
                "external": "SEED-FOOD-001", "kind": "CATERING_DELIVERY",
                "pickup": "Oxford Suites Makati", "destination": "BGC Corporate Center",
                "priority": "HIGH", "target": "NEEDS_MORE_DETAILS", "passengers": 1,
                "luggage": 0, "hours": 11, "duration": 45, "assign": False,
            },
            {
                "external": "SEED-BRANCH-001", "kind": "BRANCH_TRANSFER",
                "pickup": "Oxford Suites Makati",
                "destination": "Oxford Suites Quezon City", "priority": "NORMAL",
                "target": "APPROVED", "passengers": 6, "luggage": 4, "hours": 26,
                "duration": 120, "assign": True,
            },
        ]
        active_vehicles = list(
            Vehicle.objects.filter(is_active=True).order_by("device_id")
        )
        created_count = 0
        warned = False
        for index, example in enumerate(examples):
            request, created = TransportRequest.objects.get_or_create(
                source_system=TransportRequest.SourceSystem.MANUAL_STAFF_ENTRY,
                external_reference=example["external"],
                defaults={
                    "request_type": example["kind"],
                    "requester_name": "Oxford Suites Operations",
                    "requester_contact": "+63 2 8000 0000",
                    "pickup_name": example["pickup"],
                    "pickup_address": f"{example['pickup']}, Metro Manila",
                    "pickup_latitude": 14.554700 + index / 1000,
                    "pickup_longitude": 121.024400 + index / 1000,
                    "destination_name": example["destination"],
                    "destination_address": f"{example['destination']}, Metro Manila",
                    "destination_latitude": 14.537800 + index / 1000,
                    "destination_longitude": 121.001400 + index / 1000,
                    "scheduled_pickup_at": now + timedelta(hours=example["hours"]),
                    "estimated_duration_minutes": example["duration"],
                    "passenger_count": example["passengers"],
                    "luggage_count": example["luggage"],
                    "priority": example["priority"],
                    "notes": "Sprint 4 development seed record.",
                    "created_by": creator,
                },
            )
            if created:
                services.record_event(request, "CREATED", creator)
                created_count += 1
            target = example["target"]
            if (
                target == TransportRequest.Status.NEEDS_MORE_DETAILS
                and request.status == TransportRequest.Status.FOR_APPROVAL
            ):
                request = services.request_more_details(
                    request, creator, "Please confirm catering handling instructions."
                )
            if target in {
                TransportRequest.Status.APPROVED,
                TransportRequest.Status.READY_FOR_DISPATCH,
            } and request.status == TransportRequest.Status.FOR_APPROVAL:
                request = services.approve(request, creator, "Approved seed request.")
            if example["assign"] and request.status == TransportRequest.Status.APPROVED:
                if not request.assigned_vehicle_id:
                    vehicle = None
                    for candidate in active_vehicles:
                        if (
                            candidate.passenger_capacity is not None
                            and candidate.passenger_capacity < request.passenger_count
                        ):
                            continue
                        try:
                            request = services.assign_vehicle(
                                request,
                                candidate,
                                creator,
                                "Manual development assignment.",
                            )
                        except (services.AllocationConflict, serializers.ValidationError):
                            continue
                        vehicle = candidate
                        break
                    if not vehicle and not warned:
                        self.stderr.write(self.style.WARNING(
                            "No eligible conflict-free active vehicle was available; "
                            "assignment examples remain APPROVED and unassigned."
                        ))
                        warned = True
                if (
                    target == TransportRequest.Status.READY_FOR_DISPATCH
                    and request.assigned_vehicle_id
                ):
                    try:
                        services.prepare_dispatch(
                            request, creator, "Prepared development handoff."
                        )
                    except (services.AllocationConflict, serializers.ValidationError):
                        if not warned:
                            self.stderr.write(self.style.WARNING(
                                "The ready-for-dispatch seed remained APPROVED because its "
                                "vehicle allocation is no longer valid."
                            ))
                            warned = True
        self.stdout.write(self.style.SUCCESS(
            f"Created {created_count}; {len(examples)} seed records available."
        ))
