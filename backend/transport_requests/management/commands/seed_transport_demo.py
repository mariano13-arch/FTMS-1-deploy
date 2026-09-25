from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import NamedTuple

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from accounts.models import StaffProfile
from fleet.models import (
    Driver,
    DriverDocument,
    Vehicle,
    VehicleDocument,
    VehicleInspection,
    VehicleMaintenanceRecord,
)
from telemetry.models import TelemetryDevice, TelemetryDeviceBinding, TelemetryEvent
from transport_requests import services
from transport_requests.models import (
    DispatchAssignment,
    DispatchAssignmentEvent,
    DispatchExecutionEvent,
    DispatchPlan,
    DispatchPlanEvent,
    DispatchPlanStop,
    SourceResultOutbox,
    TransportRequest,
    TransportRequestEvent,
    TransportRequestFlightContext,
)

DEMO_MARKER = "SIMULATED DEVELOPMENT TEST DATA"
REQUEST_PREFIXES = ("HMS-TR-2026-", "SCM-TR-2026-")
LEGACY_REQUEST_PREFIXES = ("DEMO-HMS-", "DEMO-SCM-")
VEHICLE_PREFIX = "DEMO-V"
DRIVER_PREFIX = "DEMO-DRIVER-"
USER_PREFIX = "demo-transport-driver-"
POSITION_EVENT_PREFIX = "DEMO-TRANSPORT-POSITION-"
DEMO_BASE_TIME = datetime(2026, 10, 5, 8, 0, tzinfo=UTC)

class Location(NamedTuple):
    name: str
    address: str
    latitude: str
    longitude: str


# Coordinates were resolved through the project's TomTom Places integration and are
# intentionally fixed so seeding never depends on a live geocoder.
LOCATION_CATALOG = {
    "OXFORD": Location("Oxford Suites Makati", "P. Burgos Street, Poblacion, Makati City, 1210, Metro Manila", "14.563578", "121.030017"),
    "OXFORD_RECEIVING": Location("Oxford Suites Makati Receiving Area", "P. Burgos Street, Poblacion, Makati City, 1210, Metro Manila", "14.563578", "121.030017"),
    "NAIA_T1": Location("Ninoy Aquino International Airport Terminal 1", "Ninoy Aquino Avenue, NAIA, Vitalez, Pasay City, 1406, Metro Manila", "14.506935", "121.004803"),
    "NAIA_T2": Location("Ninoy Aquino International Airport Terminal 2", "NAIA Road, NAIA, Barangay 201, Pasay City, 1300, Metro Manila", "14.510590", "121.012268"),
    "NAIA_T3": Location("Ninoy Aquino International Airport Terminal 3", "Andrews Avenue, NAIA, Barangay 201, Pasay City, 1300, Metro Manila", "14.520258", "121.013858"),
    "SM_MAKATI": Location("SM Makati", "Hi-way Drive, San Lorenzo, Makati City, 1200, Metro Manila", "14.549353", "121.027070"),
    "GLORIETTA": Location("Glorietta", "Ayala Avenue, San Lorenzo, Makati City, 1200, Metro Manila", "14.552208", "121.026973"),
    "GREENBELT": Location("Greenbelt", "Esperanza Street, San Lorenzo, Makati City, 1224, Metro Manila", "14.551613", "121.021558"),
    "BGC": Location("Bonifacio Global City", "3rd Avenue, Post Proper Northside, Taguig City, 1630, Metro Manila", "14.550976", "121.046380"),
    "SM_AURA": Location("SM Aura Premier", "McKinley Road, Post Proper Northside, Taguig City, 1630, Metro Manila", "14.546846", "121.054377"),
    "MOA": Location("SM Mall of Asia", "Pacific Drive, San Rafael, Pasay City, 1302, Metro Manila", "14.534844", "120.982840"),
    "ORTIGAS": Location("Ortigas Center", "Ortigas Avenue, Santo Tomas, Pasig City, 1604, Metro Manila", "14.589427", "121.068165"),
    "ALABANG": Location("Alabang Commercial District", "Alabang-Zapote Road, Cupang, Muntinlupa City, 1820, Metro Manila", "14.424570", "121.030685"),
    "PASAY_SUPPLIER": Location("Supplier Warehouse - Pasay", "Pacific Drive, San Rafael, Pasay City, 1302, Metro Manila", "14.534844", "120.982840"),
    "PARANAQUE_SUPPLIER": Location("Supplier Warehouse - Parañaque", "San Antonio Avenue, San Antonio, Parañaque City, 1707, Metro Manila", "14.470606", "121.022263"),
    "TAGUIG_SUPPLIER": Location("Supplier Warehouse - Taguig", "McKinley Road, Post Proper Northside, Taguig City, 1630, Metro Manila", "14.546846", "121.054377"),
    "QC_STORAGE": Location("Central Storage Facility - Quezon City", "Quezon Avenue, Diliman, Quezon City, 1100, Metro Manila", "14.646670", "121.049800"),
    "MANDALUYONG_DISTRIBUTION": Location("Distribution Facility - Mandaluyong", "Boni Avenue, Plainview, Mandaluyong City, 1554, Metro Manila", "14.578130", "121.034361"),
    "MANILA_RECEIVING": Location("Receiving Facility - Manila", "Roxas Boulevard, Ermita, Manila, 1000, Metro Manila", "14.581495", "120.976562"),
}
LOCATIONS = tuple(LOCATION_CATALOG.values())
AIRPORTS = tuple(LOCATION_CATALOG[key] for key in ("NAIA_T1", "NAIA_T2", "NAIA_T3"))
GUEST_ROUTES = tuple(
    (LOCATION_CATALOG[pickup], LOCATION_CATALOG[destination])
    for pickup, destination in (
        ("OXFORD", "BGC"), ("OXFORD", "SM_AURA"), ("OXFORD", "MOA"),
        ("OXFORD", "ORTIGAS"), ("OXFORD", "ALABANG"), ("GREENBELT", "OXFORD"),
        ("BGC", "OXFORD"), ("ORTIGAS", "OXFORD"), ("SM_MAKATI", "OXFORD"),
        ("GLORIETTA", "BGC"), ("MOA", "OXFORD"), ("SM_AURA", "GREENBELT"),
    )
)
SUPPLIER_ORIGINS = tuple(
    LOCATION_CATALOG[key]
    for key in (
        "PASAY_SUPPLIER", "PARANAQUE_SUPPLIER", "TAGUIG_SUPPLIER",
        "QC_STORAGE", "MANDALUYONG_DISTRIBUTION", "MANILA_RECEIVING",
    )
)
BRANCH_ROUTES = tuple(
    (LOCATION_CATALOG[pickup], LOCATION_CATALOG[destination])
    for pickup, destination in (
        ("QC_STORAGE", "MANDALUYONG_DISTRIBUTION"),
        ("MANDALUYONG_DISTRIBUTION", "MANILA_RECEIVING"),
        ("MANILA_RECEIVING", "QC_STORAGE"),
        ("PASAY_SUPPLIER", "TAGUIG_SUPPLIER"),
    )
)
REQUEST_TYPES = (
    (TransportRequest.RequestType.GUEST_TRANSFER, 35),
    (TransportRequest.RequestType.AIRPORT_PICKUP, 15),
    (TransportRequest.RequestType.AIRPORT_DROPOFF, 10),
    (TransportRequest.RequestType.SUPPLIER_PICKUP, 30),
    (TransportRequest.RequestType.BRANCH_TRANSFER, 10),
)


def scaled_counts(total, weighted_items):
    raw = [(name, total * weight / 100) for name, weight in weighted_items]
    counts = {name: int(value) for name, value in raw}
    remainder = total - sum(counts.values())
    ranked = sorted(raw, key=lambda item: (-(item[1] - int(item[1])), str(item[0])))
    for name, _ in ranked[:remainder]:
        counts[name] += 1
    return counts


def expanded_distribution(total, weighted_items):
    counts = scaled_counts(total, weighted_items)
    return [name for name, _ in weighted_items for _ in range(counts[name])]


class Command(BaseCommand):
    help = "Create or safely reset deterministic local transport request data."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=100)
        parser.add_argument("--reset", action="store_true")
        parser.add_argument("--full-local-transport-reset", action="store_true")
        parser.add_argument("--confirm-local-demo-reset", action="store_true")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Transport demo seeding is restricted to DEBUG environments.")
        count = options["count"]
        if count < 5 or count > 500:
            raise CommandError("--count must be between 5 and 500.")
        if options["reset"] and options["full_local_transport_reset"]:
            raise CommandError(
                "Choose either --reset or --full-local-transport-reset, not both."
            )
        if options["confirm_local_demo_reset"] and not options["full_local_transport_reset"]:
            raise CommandError(
                "--confirm-local-demo-reset requires --full-local-transport-reset."
            )
        operator = self._operator()
        with transaction.atomic():
            if options["full_local_transport_reset"]:
                summary = self._transport_summary(TransportRequest.objects.all())
                self.stdout.write(
                    "FULL LOCAL TRANSPORT RESET would delete ALL local transport workflow "
                    f"data: {summary['requests']} requests, {summary['assignments']} "
                    f"assignments, {summary['plans']} related plans."
                )
                if not options["confirm_local_demo_reset"]:
                    raise CommandError(
                        "Refusing full local transport reset without "
                        "--confirm-local-demo-reset."
                    )
                self._delete_transport_workflow(TransportRequest.objects.all())
            elif options["reset"]:
                summary = self._reset_summary()
                self.stdout.write(
                    "Resetting local transport data: "
                    f"{summary['requests']} requests, {summary['vehicles']} vehicles, "
                    f"{summary['drivers']} drivers, {summary['assignments']} assignments."
                )
                self._reset()
            result = self._seed(operator, count)
        self.stdout.write(
            self.style.SUCCESS(
                f"Local transport dataset ready: {result['requests']} requests, "
                f"{result['vehicles']} vehicles, {result['drivers']} drivers; "
                f"{result['ready']} ready, {result['assigned']} assigned, "
                f"{result['completed']} completed. No route, ETA, or optimizer result was seeded."
            )
        )

    def _operator(self):
        operator = (
            get_user_model()
            .objects.filter(is_staff=True, is_active=True)
            .filter(Q(is_superuser=True) | Q(staff_profile__role=StaffProfile.Role.FLEET_MANAGER))
            .order_by("pk")
            .first()
        )
        if not operator:
            raise CommandError("Create an active Fleet Admin or Fleet Manager before seeding.")
        return operator

    def _demo_requests(self, operator=None):
        legacy = Q(external_reference__startswith=LEGACY_REQUEST_PREFIXES[0]) | Q(
            external_reference__startswith=LEGACY_REQUEST_PREFIXES[1]
        )
        professional = Q(external_reference__startswith=REQUEST_PREFIXES[0]) | Q(
            external_reference__startswith=REQUEST_PREFIXES[1]
        )
        if operator is not None:
            professional &= Q(created_by=operator)
        return TransportRequest.objects.filter(legacy | professional)

    def _reset_summary(self):
        requests = self._demo_requests(self._operator())
        summary = self._transport_summary(requests)
        return {
            **summary,
            "vehicles": Vehicle.objects.filter(device_id__startswith=VEHICLE_PREFIX).count(),
            "drivers": Driver.objects.filter(driver_code__startswith=DRIVER_PREFIX).count(),
        }

    def _transport_summary(self, requests):
        request_ids = list(requests.values_list("pk", flat=True))
        assignments = DispatchAssignment.objects.filter(transport_request_id__in=request_ids)
        plan_ids = set(
            DispatchPlanStop.objects.filter(transport_request_id__in=request_ids)
            .values_list("plan_id", flat=True)
        ) | set(assignments.exclude(plan_id=None).values_list("plan_id", flat=True))
        return {
            "requests": len(request_ids),
            "assignments": assignments.count(),
            "plans": len(plan_ids),
        }

    def _delete_transport_workflow(self, requests):
        request_ids = list(requests.values_list("pk", flat=True))
        assignments = DispatchAssignment.objects.filter(transport_request_id__in=request_ids)
        assignment_ids = list(assignments.values_list("pk", flat=True))
        plan_ids = set(
            DispatchPlanStop.objects.filter(transport_request_id__in=request_ids)
            .values_list("plan_id", flat=True)
        ) | set(assignments.exclude(plan_id=None).values_list("plan_id", flat=True))
        if plan_ids and DispatchPlanStop.objects.filter(plan_id__in=plan_ids).exclude(
            transport_request_id__in=request_ids
        ).exists():
            raise CommandError(
                "Reset refused: a demo request belongs to a mixed demo/non-demo plan."
            )

        try:
            DispatchExecutionEvent.objects.filter(assignment_id__in=assignment_ids).delete()
            DispatchAssignmentEvent.objects.filter(assignment_id__in=assignment_ids).delete()
            SourceResultOutbox.objects.filter(transport_request_id__in=request_ids).delete()
            assignments.delete()
            DispatchPlanEvent.objects.filter(plan_id__in=plan_ids).delete()
            DispatchPlanStop.objects.filter(plan_id__in=plan_ids).delete()
            DispatchPlan.objects.filter(pk__in=plan_ids).delete()
            TransportRequestFlightContext.objects.filter(
                transport_request_id__in=request_ids
            ).delete()
            TransportRequestEvent.objects.filter(request_id__in=request_ids).delete()
            requests.delete()
        except ProtectedError as error:
            blockers = ", ".join(
                f"{item._meta.label}:{item.pk}"
                for item in list(error.protected_objects)[:10]
            )
            raise CommandError(
                f"Transport reset refused because protected records remain: {blockers}"
            ) from error

    def _reset(self):
        self._delete_transport_workflow(self._demo_requests(self._operator()))
        self._clear_demo_positions()

        vehicles = Vehicle.objects.filter(device_id__startswith=VEHICLE_PREFIX)
        VehicleMaintenanceRecord.objects.filter(vehicle__in=vehicles).delete()
        VehicleDocument.objects.filter(vehicle__in=vehicles).delete()
        VehicleInspection.objects.filter(vehicle__in=vehicles).delete()
        TelemetryDeviceBinding.objects.filter(vehicle__in=vehicles).delete()
        drivers = Driver.objects.filter(driver_code__startswith=DRIVER_PREFIX)
        DriverDocument.objects.filter(driver__in=drivers).delete()
        try:
            vehicles.delete()
            drivers.delete()
            TelemetryDevice.objects.filter(device_id__startswith=VEHICLE_PREFIX).delete()
        except ProtectedError as error:
            raise CommandError(
                "Reset refused because a DEMO resource is referenced by non-demo data."
            ) from error
        get_user_model().objects.filter(username__startswith=USER_PREFIX).delete()

    def _seed(self, operator, count):
        vehicles = self._seed_vehicles(operator)
        self._seed_positions(vehicles)
        drivers = self._seed_drivers()
        request_types = expanded_distribution(count, REQUEST_TYPES)
        created_requests = []
        source_sequences = {"HMS": 0, "SCM": 0}
        for index, request_type in enumerate(request_types):
            source = "SCM" if request_type in {
                TransportRequest.RequestType.SUPPLIER_PICKUP,
                TransportRequest.RequestType.BRANCH_TRANSFER,
            } else "HMS"
            source_sequences[source] += 1
            sequence = source_sequences[source]
            item, created = self._request(operator, index, request_type, sequence)
            if created:
                services.record_event(item, "CREATED", operator)
            created_requests.append(item)
        return {
            "requests": len(created_requests),
            "vehicles": len(vehicles),
            "drivers": len(drivers),
            "ready": 0,
            "assigned": 0,
            "completed": 0,
        }

    def _clear_demo_positions(self):
        try:
            TelemetryEvent.objects.filter(
                event_id__startswith=POSITION_EVENT_PREFIX,
                position_source=TelemetryEvent.PositionSource.SIMULATED_TEST,
                vehicle__device_id__startswith=VEHICLE_PREFIX,
            ).delete()
        except ProtectedError as error:
            raise CommandError(
                "Demo position reset refused because a simulated event has protected history."
            ) from error

    def _seed_positions(self, vehicles):
        self._clear_demo_positions()
        now = timezone.now()
        for index, vehicle in enumerate([*vehicles[:5], *vehicles[6:11]]):
            location = LOCATIONS[index % len(LOCATIONS)]
            binding = TelemetryDeviceBinding.objects.get(
                vehicle=vehicle,
                unpaired_at__isnull=True,
            )
            TelemetryEvent.objects.create(
                schema_version="1.2",
                event_id=f"{POSITION_EVENT_PREFIX}{vehicle.device_id}",
                sequence_number=1,
                device=binding.device,
                vehicle=vehicle,
                recorded_at=now,
                location=Point(float(location.longitude), float(location.latitude), srid=4326),
                position_source=TelemetryEvent.PositionSource.SIMULATED_TEST,
                gnss_speed_kph=None,
                position_accuracy_m=None,
                obd_source=None,
                driving_event=None,
            )

    def _seed_vehicles(self, operator):
        today = datetime.now(tz=UTC).date()
        vehicles = []
        for number in range(1, 16):
            supply = number >= 7
            vehicle, _ = Vehicle.objects.update_or_create(
                device_id=f"{VEHICLE_PREFIX}{number:03d}",
                defaults={
                    "plate_number": f"DMO-{number:03d}",
                    "display_name": (
                        f"DEMO Supply Vehicle {number:02d}"
                        if supply else f"DEMO Passenger Vehicle {number:02d}"
                    ),
                    "vehicle_type": (
                        Vehicle.VehicleType.SERVICE_TRUCK if supply else Vehicle.VehicleType.VAN
                    ),
                    "passenger_capacity": 2 if number == 15 else (4 + number % 3 * 2),
                    "payload_capacity_kg": (
                        Decimal("200") if number == 15 else Decimal(str(500 + (number - 7) * 200))
                    ) if supply else None,
                    "is_active": number != 14,
                },
            )
            vehicles.append(vehicle)
            if not VehicleInspection.objects.filter(
                vehicle=vehicle,
                inspection_date=today,
                inspection_type=VehicleInspection.InspectionType.PRE_TRIP,
            ).exists():
                VehicleInspection.objects.create(
                    vehicle=vehicle,
                    inspection_date=today,
                    inspection_type=VehicleInspection.InspectionType.PRE_TRIP,
                    result=(
                        VehicleInspection.Result.FAILED
                        if number == 13
                        else VehicleInspection.Result.PASSED
                    ),
                    exterior_condition=VehicleInspection.Condition.OK,
                    interior_condition=VehicleInspection.Condition.OK,
                    tires_condition=VehicleInspection.Condition.OK,
                    lights_condition=VehicleInspection.Condition.OK,
                    brakes_condition=VehicleInspection.Condition.OK,
                    fluids_condition=VehicleInspection.Condition.OK,
                    safety_equipment_condition=VehicleInspection.Condition.OK,
                    notes=DEMO_MARKER,
                    inspected_by=operator,
                )
            if number == 12:
                VehicleMaintenanceRecord.objects.get_or_create(
                    vehicle=vehicle,
                    title="DEMO maintenance block",
                    defaults={
                        "status": VehicleMaintenanceRecord.Status.OPEN,
                        "notes": DEMO_MARKER,
                        "created_by": operator,
                    },
                )
        return vehicles

    def _seed_drivers(self):
        today = datetime.now(tz=UTC).date()
        drivers = []
        for number in range(1, 16):
            user, _ = get_user_model().objects.get_or_create(
                username=f"{USER_PREFIX}{number:03d}",
                defaults={"is_active": True},
            )
            driver, _ = Driver.objects.update_or_create(
                driver_code=f"{DRIVER_PREFIX}{number:03d}",
                defaults={
                    "first_name": "DEMO",
                    "last_name": f"Driver {number:03d}",
                    "employment_status": (
                        Driver.EmploymentStatus.ON_LEAVE
                        if number == 13
                        else (
                            Driver.EmploymentStatus.SUSPENDED
                            if number == 14
                            else Driver.EmploymentStatus.ACTIVE
                        )
                    ),
                    "linked_user": user,
                    "license_number": f"DEMO-LICENSE-{number:03d}",
                    "license_category": "Professional",
                    "license_expiry_date": today + timedelta(days=(-1 if number == 15 else 365)),
                    "medical_certificate_expiry_date": today + timedelta(days=365),
                },
            )
            drivers.append(driver)
        return drivers

    def _request(self, operator, index, request_type, sequence):
        supply = request_type in {
            TransportRequest.RequestType.SUPPLIER_PICKUP,
            TransportRequest.RequestType.BRANCH_TRANSFER,
        }
        source_code = "SCM" if supply else "HMS"
        if request_type == TransportRequest.RequestType.GUEST_TRANSFER:
            pickup, destination = GUEST_ROUTES[index % len(GUEST_ROUTES)]
        elif request_type == TransportRequest.RequestType.AIRPORT_PICKUP:
            pickup, destination = AIRPORTS[index % len(AIRPORTS)], LOCATION_CATALOG["OXFORD"]
        elif request_type == TransportRequest.RequestType.AIRPORT_DROPOFF:
            pickup, destination = LOCATION_CATALOG["OXFORD"], AIRPORTS[index % len(AIRPORTS)]
        elif request_type == TransportRequest.RequestType.SUPPLIER_PICKUP:
            pickup = SUPPLIER_ORIGINS[index % len(SUPPLIER_ORIGINS)]
            destination = LOCATION_CATALOG["OXFORD_RECEIVING"]
        else:
            pickup, destination = BRANCH_ROUTES[index % len(BRANCH_ROUTES)]
        weight = (100, 300, 600, 900, 1200)[index % 5] if supply else None
        load_descriptions = (
            "Housekeeping supplies",
            "Guest room amenities",
            "Hotel linen inventory",
            "Food service supplies",
            "Maintenance consumables",
        )
        item, created = TransportRequest.objects.get_or_create(
            source_system=(
                TransportRequest.SourceSystem.SUPPLY_CHAIN_MANAGEMENT_SYSTEM
                if supply else TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM
            ),
            external_reference=f"{source_code}-TR-2026-{sequence:04d}",
            defaults={
                "request_type": request_type,
                "request_category": (
                    TransportRequest.RequestCategory.DELIVERY_LOGISTICS
                    if supply else TransportRequest.RequestCategory.PASSENGER_TRANSPORT
                ),
                "requester_name": (
                    ("Procurement Office" if request_type == TransportRequest.RequestType.SUPPLIER_PICKUP else "Inventory Control")
                    if supply
                    else ("Front Office" if request_type != TransportRequest.RequestType.GUEST_TRANSFER else "Guest Services")
                ),
                "pickup_name": pickup.name,
                "pickup_address": pickup.address,
                "pickup_latitude": pickup.latitude,
                "pickup_longitude": pickup.longitude,
                "destination_name": destination.name,
                "destination_address": destination.address,
                "destination_latitude": destination.latitude,
                "destination_longitude": destination.longitude,
                "scheduled_pickup_at": DEMO_BASE_TIME + timedelta(days=index // 8, hours=(index % 8) * 2),
                "estimated_duration_minutes": (45, 60, 75)[index % 3],
                "required_vehicle_type": (
                    Vehicle.VehicleType.SERVICE_TRUCK if supply else Vehicle.VehicleType.VAN
                ),
                "passenger_count": 0 if supply else 1 + index % 5,
                "luggage_count": 0 if supply else index % 4,
                "load_description": (
                    load_descriptions[index % len(load_descriptions)] if supply else ""
                ),
                "load_quantity": 4 + index % 17 if supply else None,
                "estimated_weight_kg": weight,
                "handling_instructions": "Keep containers secured during transport." if supply and index % 3 == 0 else "",
                "priority": (
                    TransportRequest.Priority.HIGH
                    if index % 9 == 0
                    else TransportRequest.Priority.NORMAL
                ),
                "notes": (
                    "Scheduled supplier collection for hotel receiving."
                    if supply
                    else (
                        "Airport transfer requested through guest services."
                        if request_type in {
                            TransportRequest.RequestType.AIRPORT_PICKUP,
                            TransportRequest.RequestType.AIRPORT_DROPOFF,
                        }
                        else "Scheduled guest transportation request."
                    )
                ),
                "created_by": operator,
            },
        )
        return item, created
