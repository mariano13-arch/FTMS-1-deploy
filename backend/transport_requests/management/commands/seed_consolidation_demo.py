from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from accounts.models import StaffProfile
from fleet.models import Driver, Vehicle
from fleet.serializers import driver_eligibility
from telemetry.models import TelemetryEvent
from transport_requests import matrix, services
from transport_requests.models import DispatchAssignment, TransportRequest

DRIVERS = (
    ("DEV-CONS-DRV-001", "Maya", "Santos", "DEV-CONS-LIC-001", 365, 365),
    ("DEV-CONS-DRV-002", "Luis", "Reyes", "DEV-CONS-LIC-002", 300, 300),
    ("DEV-CONS-DRV-003", "Rico", "Mendoza", "", None, 300),
)
LOCATIONS = (
    ("Oxford Suites Makati", "14.565200", "121.028600"),
    ("BGC Corporate Center", "14.549300", "121.045800"),
    ("SM Aura", "14.546800", "121.054900"),
    ("Ninoy Aquino International Airport", "14.508600", "121.019800"),
)
MONEY_PRECISION = Decimal("0.01")


def _scaled_load(capacity, ratio):
    return max(MONEY_PRECISION, (capacity * ratio).quantize(MONEY_PRECISION, ROUND_HALF_UP))


def _safe_schedule(drivers, vehicle):
    base = timezone.now().replace(second=0, microsecond=0) + timedelta(hours=2)
    assignments = list(
        DispatchAssignment.objects.filter(
            Q(driver__in=drivers) | Q(vehicle=vehicle),
            transport_request__status__in=(
                TransportRequest.Status.APPROVED,
                TransportRequest.Status.READY_FOR_DISPATCH,
            ),
        ).select_related("transport_request")
    )
    for shift in range(30):
        first_start = base + timedelta(hours=shift * 2)
        group_end = first_start + timedelta(minutes=75)
        if not any(
            item.transport_request.scheduled_pickup_at < group_end
            and services.planning_end(item.transport_request) > first_start
            for item in assignments
        ):
            return first_start
    raise CommandError("No conflict-free development window was found in the next 60 hours.")


class Command(BaseCommand):
    help = "Create deterministic development data for Smart Dispatch Consolidation."

    def handle(self, *args, **options):
        operator = (
            get_user_model()
            .objects.filter(is_staff=True, is_active=True)
            .filter(Q(is_superuser=True) | Q(staff_profile__role=StaffProfile.Role.FLEET_MANAGER))
            .order_by("pk")
            .first()
        )
        if not operator:
            raise CommandError(
                "Create an active Super Admin or Fleet Manager before seeding "
                "consolidation demo data."
            )

        today = timezone.localdate()
        driver_created = 0
        for code, first_name, last_name, license_number, license_days, medical_days in DRIVERS:
            driver, created = Driver.objects.get_or_create(
                driver_code=code,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "employment_status": Driver.EmploymentStatus.ACTIVE,
                    "license_number": license_number,
                    "license_category": "Professional" if license_number else "",
                    "license_expiry_date": (
                        today + timedelta(days=license_days) if license_days is not None else None
                    ),
                    "medical_certificate_expiry_date": (
                        today + timedelta(days=medical_days) if medical_days is not None else None
                    ),
                },
            )
            readiness = {
                "employment_status": Driver.EmploymentStatus.ACTIVE,
                "license_number": license_number,
                "license_category": "Professional" if license_number else "",
                "license_expiry_date": (
                    today + timedelta(days=license_days) if license_days is not None else None
                ),
                "medical_certificate_expiry_date": (
                    today + timedelta(days=medical_days) if medical_days is not None else None
                ),
            }
            for field, value in readiness.items():
                setattr(driver, field, value)
            driver.save(update_fields=[*readiness, "updated_at"])
            driver_created += int(created)

        fresh_origins = matrix.eligible_vehicle_origins()
        fresh_by_device = {item["vehicle_id"]: item for item in fresh_origins}
        vehicle = (
            Vehicle.objects.filter(
                device_id__in=fresh_by_device,
                is_active=True,
                payload_capacity_kg__gt=0,
            )
            .order_by("device_id")
            .first()
        )
        gis_ready = vehicle is not None
        vehicle_created = False
        if vehicle is None:
            vehicle = (
                Vehicle.objects.filter(
                    device_id__startswith="DEV-LOG-",
                    is_active=True,
                    payload_capacity_kg__gt=0,
                )
                .order_by("device_id")
                .first()
            )
        if vehicle is None:
            vehicle, vehicle_created = Vehicle.objects.get_or_create(
                device_id="DEV-CONS-VEH-001",
                defaults={
                    "plate_number": "DCV-001",
                    "display_name": "Development Consolidation Truck",
                    "vehicle_type": Vehicle.VehicleType.SERVICE_TRUCK,
                    "passenger_capacity": 3,
                    "payload_capacity_kg": Decimal("1000.00"),
                    "gvwr_kg": Decimal("3500.00"),
                    "is_active": True,
                },
            )
        if not vehicle.is_active or vehicle.payload_capacity_kg is None:
            raise CommandError(
                f"Development vehicle {vehicle.device_id} is no longer active/cargo-capable; "
                "preserving it without overwrite."
            )

        positive_first = _scaled_load(vehicle.payload_capacity_kg, Decimal("0.25"))
        positive_second = _scaled_load(vehicle.payload_capacity_kg, Decimal("0.20"))
        overflow_weight = (
            vehicle.payload_capacity_kg
            - positive_first
            - positive_second
            + _scaled_load(vehicle.payload_capacity_kg, Decimal("0.10"))
        )
        request_specs = (
            ("DEV-CONS-REQ-001", "SUPPLIER_PICKUP", positive_first, None, 0),
            ("DEV-CONS-REQ-002", "BRANCH_TRANSFER", positive_second, None, 15),
            ("DEV-CONS-REQ-003", "CATERING_DELIVERY", overflow_weight, None, 30),
            ("DEV-CONS-REQ-004", "FOOD_DELIVERY", None, 12, 45),
        )
        positive_drivers = list(
            Driver.objects.filter(driver_code__in=("DEV-CONS-DRV-001", "DEV-CONS-DRV-002"))
        )
        now = _safe_schedule(positive_drivers, vehicle)
        request_created = request_existing = request_preserved = 0
        seeded_requests = []
        for index, (reference, request_type, weight, quantity, offset_minutes) in enumerate(
            request_specs
        ):
            pickup = LOCATIONS[index % len(LOCATIONS)]
            destination = LOCATIONS[(index + 1) % len(LOCATIONS)]
            item, created = TransportRequest.objects.get_or_create(
                source_system=TransportRequest.SourceSystem.MANUAL_STAFF_ENTRY,
                external_reference=reference,
                defaults={
                    "request_type": request_type,
                    "request_category": TransportRequest.RequestCategory.DELIVERY_LOGISTICS,
                    "requester_name": "Smart Consolidation Development Operations",
                    "pickup_name": pickup[0],
                    "pickup_address": f"{pickup[0]}, Metro Manila",
                    "pickup_latitude": pickup[1],
                    "pickup_longitude": pickup[2],
                    "destination_name": destination[0],
                    "destination_address": f"{destination[0]}, Metro Manila",
                    "destination_latitude": destination[1],
                    "destination_longitude": destination[2],
                    "scheduled_pickup_at": now + timedelta(minutes=offset_minutes),
                    "estimated_duration_minutes": 60,
                    "required_vehicle_type": vehicle.vehicle_type,
                    "passenger_count": 0,
                    "luggage_count": 0,
                    "load_description": "Synthetic development logistics load",
                    "load_quantity": quantity,
                    "estimated_weight_kg": weight,
                    "priority": TransportRequest.Priority.NORMAL,
                    "notes": "Synthetic development record for consolidation testing.",
                    "created_by": operator,
                },
            )
            if created:
                services.record_event(item, "CREATED", operator)
                services.approve(item, operator, "Approved consolidation development fixture.")
                request_created += 1
            elif (
                item.status == TransportRequest.Status.APPROVED
                and not DispatchAssignment.objects.filter(transport_request=item).exists()
                and not item.dispatch_plan_stops.exists()
            ):
                controlled = {
                    "request_type": request_type,
                    "request_category": TransportRequest.RequestCategory.DELIVERY_LOGISTICS,
                    "scheduled_pickup_at": now + timedelta(minutes=offset_minutes),
                    "estimated_duration_minutes": 60,
                    "required_vehicle_type": vehicle.vehicle_type,
                    "passenger_count": 0,
                    "luggage_count": 0,
                    "load_description": "Synthetic development logistics load",
                    "load_quantity": quantity,
                    "estimated_weight_kg": weight,
                }
                for field, value in controlled.items():
                    setattr(item, field, value)
                item.save(update_fields=[*controlled, "updated_at"])
                request_existing += 1
            else:
                request_preserved += 1
            item.refresh_from_db()
            seeded_requests.append(item)

        passenger, passenger_created = TransportRequest.objects.get_or_create(
            source_system=TransportRequest.SourceSystem.MANUAL_STAFF_ENTRY,
            external_reference="DEV-CONS-PAX-001",
            defaults={
                "request_type": TransportRequest.RequestType.GUEST_TRANSFER,
                "request_category": TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
                "requester_name": "Smart Consolidation Development Operations",
                "pickup_name": LOCATIONS[0][0],
                "pickup_address": f"{LOCATIONS[0][0]}, Metro Manila",
                "pickup_latitude": LOCATIONS[0][1],
                "pickup_longitude": LOCATIONS[0][2],
                "destination_name": LOCATIONS[3][0],
                "destination_address": f"{LOCATIONS[3][0]}, Metro Manila",
                "destination_latitude": LOCATIONS[3][1],
                "destination_longitude": LOCATIONS[3][2],
                "scheduled_pickup_at": now + timedelta(minutes=180),
                "estimated_duration_minutes": 60,
                "required_vehicle_type": Vehicle.VehicleType.VAN,
                "passenger_count": 2,
                "luggage_count": 1,
                "priority": TransportRequest.Priority.NORMAL,
                "notes": "Synthetic passenger negative control for consolidation testing.",
                "created_by": operator,
            },
        )
        if passenger_created:
            services.record_event(passenger, "CREATED", operator)
            services.approve(passenger, operator, "Approved passenger negative-control fixture.")

        fresh_vehicle_count = len(fresh_origins)
        eligibility = {
            code: driver_eligibility(Driver.objects.get(driver_code=code))[0]
            for code, *_ in DRIVERS
        }
        self.stdout.write(self.style.SUCCESS("DEVELOPMENT Smart Consolidation demo data ready."))
        self.stdout.write(
            f"Drivers: {driver_created} created, {len(DRIVERS) - driver_created} existing "
            f"({', '.join(f'{code}={status}' for code, status in eligibility.items())})."
        )
        latest_telemetry = (
            TelemetryEvent.objects.filter(vehicle=vehicle)
            .order_by("-recorded_at", "-sequence_number", "-received_at", "-pk")
            .values_list("recorded_at", flat=True)
            .first()
        )
        self.stdout.write(
            f"Selected {'real GIS' if gis_ready else 'database-only'} Vehicle: "
            f"device_id={vehicle.device_id}; plate={vehicle.plate_number}; "
            f"vehicle_type={vehicle.vehicle_type}; payload_capacity_kg="
            f"{vehicle.payload_capacity_kg}; telemetry_recorded_at="
            f"{latest_telemetry.isoformat() if latest_telemetry else 'unavailable'}; "
            f"state={'created' if vehicle_created else 'reused'}; fresh GIS vehicles="
            f"{fresh_vehicle_count}."
        )
        self.stdout.write(
            f"Delivery requests: {request_created} created, {request_existing} refreshed, "
            f"{request_preserved} preserved; passenger control: "
            f"{'created' if passenger_created else 'existing'}.",
        )
        if not gis_ready:
            self.stdout.write(
                self.style.WARNING(
                    "No fresh GIS-capable Vehicle is currently available. Publish real telemetry "
                    "before running the full Smart Consolidation demo."
                )
            )
        for item in seeded_requests:
            self.stdout.write(f"{item.external_reference} -> {item.request_number}")
        self.stdout.write(f"{passenger.external_reference} -> {passenger.request_number}")
