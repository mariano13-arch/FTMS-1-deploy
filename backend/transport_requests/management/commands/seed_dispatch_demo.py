from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from accounts.models import StaffProfile
from fleet.models import Driver, Vehicle
from fleet.serializers import driver_eligibility
from transport_requests import dispatch, services
from transport_requests.models import DispatchAssignment, TransportRequest

DRIVERS = (
    ("DEV-DRV-001", "Elena", "Santos", "ACTIVE", "DEV-LIC-001", 365, 365),
    ("DEV-DRV-002", "Marco", "Reyes", "ACTIVE", "DEV-LIC-002", 300, 300),
    ("DEV-DRV-003", "Rina", "Cruz", "ACTIVE", "", None, None),
    ("DEV-DRV-004", "Tomas", "Garcia", "ACTIVE", "DEV-LIC-004", -1, 180),
)

REQUESTS = (
    ("DEV-DISPATCH-001", "AIRPORT_PICKUP", "VAN", 4, 1),
    ("DEV-DISPATCH-002", "GUEST_TRANSFER", "SUV", 3, 2),
    ("DEV-DISPATCH-003", "AIRPORT_DROPOFF", "SEDAN", 2, 3),
    ("DEV-DISPATCH-004", "STAFF_SHUTTLE", "SHUTTLE_BUS", 12, 4),
    ("DEV-DISPATCH-005", "VIP_TRANSPORT", "VAN", 5, 5),
)

LOCATIONS = (
    ("Oxford Suites Makati", "14.565200", "121.028600"),
    ("Ninoy Aquino International Airport", "14.508600", "121.019800"),
    ("BGC Corporate Center", "14.549300", "121.045800"),
    ("SM Aura", "14.546800", "121.054900"),
)


class Command(BaseCommand):
    help = "Create deterministic Drivers and approved requests for Dispatch Board development."

    def handle(self, *args, **options):
        operator = (
            get_user_model()
            .objects.filter(is_staff=True, is_active=True)
            .filter(
                Q(is_superuser=True)
                | Q(staff_profile__role=StaffProfile.Role.FLEET_MANAGER)
            )
            .order_by("pk")
            .first()
        )
        if not operator:
            raise CommandError(
                "Create an active Super Admin or Fleet Manager before seeding dispatch demo data."
            )

        today = timezone.localdate()
        driver_created = 0
        for (
            code,
            first_name,
            last_name,
            employment,
            license_number,
            license_days,
            medical_days,
        ) in DRIVERS:
            _, created = Driver.objects.get_or_create(
                driver_code=code,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "employment_status": employment,
                    "license_number": license_number,
                    "license_category": "Professional",
                    "license_expiry_date": (
                        today + timedelta(days=license_days)
                        if license_days is not None
                        else None
                    ),
                    "medical_certificate_expiry_date": (
                        today + timedelta(days=medical_days)
                        if medical_days is not None
                        else None
                    ),
                },
            )
            driver_created += int(created)

        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        request_created = 0
        seeded_requests = []
        for index, (reference, request_type, vehicle_type, passengers, offset) in enumerate(
            REQUESTS
        ):
            pickup = LOCATIONS[index % len(LOCATIONS)]
            destination = LOCATIONS[(index + 1) % len(LOCATIONS)]
            item, created = TransportRequest.objects.get_or_create(
                source_system=TransportRequest.SourceSystem.MANUAL_STAFF_ENTRY,
                external_reference=reference,
                defaults={
                    "request_type": request_type,
                    "request_category": TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
                    "requester_name": "Dispatch Development Operations",
                    "pickup_name": pickup[0],
                    "pickup_address": f"{pickup[0]}, Metro Manila",
                    "pickup_latitude": pickup[1],
                    "pickup_longitude": pickup[2],
                    "destination_name": destination[0],
                    "destination_address": f"{destination[0]}, Metro Manila",
                    "destination_latitude": destination[1],
                    "destination_longitude": destination[2],
                    "scheduled_pickup_at": now + timedelta(hours=offset),
                    "estimated_duration_minutes": 60,
                    "required_vehicle_type": vehicle_type,
                    "passenger_count": passengers,
                    "luggage_count": min(passengers, 4),
                    "priority": TransportRequest.Priority.NORMAL,
                    "notes": "Synthetic development record for Dispatch Board testing.",
                    "created_by": operator,
                },
            )
            if created:
                services.record_event(item, "CREATED", operator)
                services.approve(item, operator, "Approved deterministic dispatch demo request.")
                item.refresh_from_db()
                request_created += 1
            seeded_requests.append(item)

        assignment_created = 0
        assignment_request = seeded_requests[0]
        assignment_driver = Driver.objects.get(driver_code="DEV-DRV-001")
        assignment_vehicle = Vehicle.objects.filter(
            device_id="DEV-PAX-006", is_active=True
        ).first()
        if (
            assignment_vehicle
            and assignment_request.status == TransportRequest.Status.APPROVED
            and not DispatchAssignment.objects.filter(
                transport_request=assignment_request
            ).exists()
            and driver_eligibility(assignment_driver)[0] == "ELIGIBLE"
        ):
            dispatch.confirm_assignment(
                transport_request_id=assignment_request.pk,
                vehicle_id=assignment_vehicle.pk,
                driver_id=assignment_driver.pk,
                selection_mode=DispatchAssignment.SelectionMode.MANUAL,
                user=operator,
                override_reason="Deterministic development schedule-conflict fixture.",
            )
            assignment_created = 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Drivers: {driver_created} created, {len(DRIVERS) - driver_created} existing; "
                f"requests: {request_created} created, {len(REQUESTS) - request_created} existing; "
                f"assignments: {assignment_created} created."
            )
        )
