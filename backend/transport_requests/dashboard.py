from datetime import timedelta

from django.conf import settings
from django.db.models import Count, OuterRef, Subquery
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import ModuleActionAccess, StaffAccess
from fleet.models import Driver, Vehicle, VehicleInspection, VehicleMaintenanceRecord
from ml.fuel_rate_resolver import resolve_vehicle_fuel_rate
from telemetry.models import (
    DriverSafetyEvent,
    Geofence,
    GeofenceEvent,
    TelemetryDevice,
    TelemetryDeviceBinding,
    TelemetryEvent,
    VehicleEmergencySOS,
)

from .models import DispatchAssignment, TransportRequest
from .views import dispatch_board_summary


def breakdown(queryset, field, choices):
    counts = dict(queryset.values_list(field).annotate(count=Count("pk")))
    return [
        {"value": value, "label": label, "count": counts.get(value, 0)} for value, label in choices
    ]


def widget(*, scope, classification, provenance, values, description, module_url, **extra):
    return {
        "scope": scope,
        "classification": classification,
        "provenance": provenance,
        "description": description,
        "module_url": module_url,
        "values": values,
        **extra,
    }


class DashboardSummaryView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DASHBOARD"
    permission_action = "VIEW"
    http_method_names = ["get", "options"]

    def get(self, request):
        now = timezone.now()
        today = timezone.localdate(now)
        requests = TransportRequest.objects.all()
        assignments = DispatchAssignment.objects.all()
        active_assignments = assignments.exclude(
            execution_status=DispatchAssignment.ExecutionStatus.COMPLETED
        )

        dispatch_summary = dispatch_board_summary(request)
        dispatch_values = [
            {"value": key, "label": label, "count": dispatch_summary[key]}
            for key, label in (
                ("awaiting_assignment", "Awaiting assignment"),
                ("optimizer_eligible", "Optimizer eligible"),
                ("needs_attention", "Needs attention"),
                ("no_eligible_driver", "No eligible driver"),
                ("no_gis_vehicle", "No GIS vehicle"),
                ("schedule_conflict", "Schedule conflict"),
                ("number_coding_blocked", "Number coding blocked"),
            )
        ]

        completed_start = today - timedelta(days=6)
        completed_daily = {
            row["day"]: row["count"]
            for row in assignments.filter(
                execution_status=DispatchAssignment.ExecutionStatus.COMPLETED,
                completed_at__date__gte=completed_start,
                completed_at__date__lte=today,
            )
            .annotate(day=TruncDate("completed_at"))
            .values("day")
            .annotate(count=Count("pk"))
        }
        completed_values = [
            {
                "value": (completed_start + timedelta(days=offset)).isoformat(),
                "label": (completed_start + timedelta(days=offset)).strftime("%b %d"),
                "count": completed_daily.get(completed_start + timedelta(days=offset), 0),
            }
            for offset in range(7)
        ]

        fleet_values = [
            {
                "value": "ACTIVE",
                "label": "Active",
                "count": Vehicle.objects.filter(is_active=True).count(),
            },
            {
                "value": "INACTIVE",
                "label": "Inactive",
                "count": Vehicle.objects.filter(is_active=False).count(),
            },
            {
                "value": "CURRENTLY_ASSIGNED",
                "label": "Currently assigned",
                "count": active_assignments.values("vehicle_id").distinct().count(),
            },
        ]
        driver_values = breakdown(
            Driver.objects.all(), "employment_status", Driver.EmploymentStatus.choices
        )
        driver_values.append(
            {
                "value": "CURRENTLY_ASSIGNED",
                "label": "Currently assigned",
                "count": active_assignments.values("driver_id").distinct().count(),
            }
        )

        inspections_today = VehicleInspection.objects.filter(inspection_date=today)
        maintenance_current = VehicleMaintenanceRecord.objects.exclude(
            status__in=(
                VehicleMaintenanceRecord.Status.COMPLETED,
                VehicleMaintenanceRecord.Status.CANCELLED,
            )
        )
        maintenance_values = breakdown(
            VehicleMaintenanceRecord.objects.all(),
            "status",
            (
                (VehicleMaintenanceRecord.Status.OPEN, "Open"),
                (VehicleMaintenanceRecord.Status.SCHEDULED, "Scheduled"),
                (VehicleMaintenanceRecord.Status.IN_PROGRESS, "In progress"),
            ),
        )
        maintenance_values.append(
            {
                "value": "COMPLETED_TODAY",
                "label": "Completed today",
                "count": VehicleMaintenanceRecord.objects.filter(completed_at__date=today).count(),
            }
        )

        safety = (
            DriverSafetyEvent.objects.filter(occurred_at__date=today)
            .exclude(telemetry_event__position_source=TelemetryEvent.PositionSource.SIMULATED_TEST)
            .exclude(telemetry_event__obd_source=TelemetryEvent.ObdSource.SIMULATED_TEST)
            .select_related("driver", "vehicle", "assignment__transport_request")
        )
        safety_values = breakdown(
            safety,
            "event_type",
            (
                (TelemetryEvent.DrivingEvent.HARSH_BRAKING, "Harsh braking"),
                (TelemetryEvent.DrivingEvent.HARSH_ACCELERATION, "Harsh acceleration"),
                (TelemetryEvent.DrivingEvent.SHARP_TURN, "Sharp turn"),
            ),
        )
        safety_recent = [
            {
                "id": event.pk,
                "label": event.get_event_type_display(),
                "detail": f"{event.driver} · {event.vehicle.display_name}",
                "occurred_at": event.occurred_at,
            }
            for event in safety.order_by("-occurred_at", "-pk")[:5]
        ]

        geofence = GeofenceEvent.objects.filter(occurred_at__date=today).select_related(
            "geofence", "vehicle", "telemetry_event"
        )
        geofence_values = [
            {
                "value": "ENTER",
                "label": "Entries",
                "count": geofence.filter(event_type=GeofenceEvent.EventType.ENTER).count(),
            },
            {
                "value": "EXIT",
                "label": "Exits",
                "count": geofence.filter(event_type=GeofenceEvent.EventType.EXIT).count(),
            },
            {
                "value": "RESTRICTED_ENTRY",
                "label": "Restricted entries",
                "count": geofence.filter(
                    event_type=GeofenceEvent.EventType.ENTER,
                    geofence__category=Geofence.Category.RESTRICTED,
                ).count(),
            },
        ]
        geofence_recent = [
            {
                "id": event.pk,
                "label": f"{event.get_event_type_display()} · {event.geofence.name}",
                "detail": event.vehicle.display_name,
                "occurred_at": event.occurred_at,
                "provenance": event.telemetry_event.get_position_source_display(),
            }
            for event in geofence.order_by("-occurred_at", "-pk")[:5]
        ]

        registered_devices = TelemetryDevice.objects.filter(
            registration_status=TelemetryDevice.RegistrationStatus.REGISTERED
        )
        active_bindings = TelemetryDeviceBinding.objects.filter(unpaired_at__isnull=True)
        bound_device_ids = active_bindings.values("device_id")
        latest_event = TelemetryEvent.objects.filter(device_id=OuterRef("pk")).order_by(
            "-recorded_at", "-sequence_number", "-received_at", "-pk"
        )
        annotated_devices = registered_devices.annotate(
            latest_recorded_at=Subquery(latest_event.values("recorded_at")[:1]),
            latest_position_source=Subquery(latest_event.values("position_source")[:1]),
            latest_obd_source=Subquery(latest_event.values("obd_source")[:1]),
        )
        fresh_cutoff = now - timedelta(seconds=settings.DISPATCH_TELEMETRY_MAX_AGE_SECONDS)
        genuine_recent = annotated_devices.filter(
            latest_recorded_at__gte=fresh_cutoff,
            latest_position_source__in=(
                TelemetryEvent.PositionSource.GNSS,
                TelemetryEvent.PositionSource.CELLULAR_LBS,
            ),
        ).exclude(latest_obd_source=TelemetryEvent.ObdSource.SIMULATED_TEST)
        device_values = [
            {"value": "REGISTERED", "label": "Registered", "count": registered_devices.count()},
            {
                "value": "BOUND",
                "label": "Currently bound",
                "count": active_bindings.filter(
                    device__registration_status=TelemetryDevice.RegistrationStatus.REGISTERED
                ).count(),
            },
            {
                "value": "UNBOUND",
                "label": "Unbound",
                "count": registered_devices.exclude(pk__in=bound_device_ids).count(),
            },
            {
                "value": "NEVER_RECEIVED",
                "label": "Never received telemetry",
                "count": annotated_devices.filter(latest_recorded_at__isnull=True).count(),
            },
            {
                "value": "GENUINE_RECENT",
                "label": "Genuine recent telemetry",
                "count": genuine_recent.count(),
            },
        ]

        fuel_counts = {
            "CURRENT_AI": 0,
            "HISTORICAL_AI_BASELINE": 0,
            "FLEET_REFERENCE_BASELINE": 0,
            "UNAVAILABLE": 0,
        }
        for vehicle in Vehicle.objects.filter(is_active=True):
            fuel_counts[resolve_vehicle_fuel_rate(vehicle, now=now).basis] += 1
        fuel_values = [
            {"value": basis, "label": label, "count": fuel_counts[basis]}
            for basis, label in (
                ("CURRENT_AI", "Current AI"),
                ("HISTORICAL_AI_BASELINE", "Historical AI baseline"),
                ("FLEET_REFERENCE_BASELINE", "Fleet reference baseline"),
                ("UNAVAILABLE", "Unavailable"),
            )
        ]

        active_sos = VehicleEmergencySOS.objects.filter(
            status=VehicleEmergencySOS.Status.ACTIVE
        ).select_related("device", "vehicle", "driver")
        sos_recent = [
            {
                "id": item.pk,
                "label": item.device.device_id,
                "detail": item.vehicle.display_name if item.vehicle else "Vehicle not attributed",
                "occurred_at": item.activated_at,
                "location": None,
            }
            for item in active_sos.order_by("-activated_at", "-pk")[:5]
        ]

        return Response(
            {
                "generated_at": now,
                "request_status": widget(
                    scope="Current",
                    classification="Operational",
                    provenance="TransportRequest.status",
                    values=breakdown(requests, "status", TransportRequest.Status.choices),
                    description="Current transport requests by authoritative workflow status.",
                    module_url="/transport-requests",
                    total=requests.count(),
                ),
                "dispatch_queue": widget(
                    scope="Current",
                    classification="Operational",
                    provenance="Dispatch Board eligibility logic",
                    values=dispatch_values,
                    description=(
                        "Dispatch-ready work and factual eligibility blockers; "
                        "recommendations are not assignments."
                    ),
                    module_url="/dispatch-board",
                    total=dispatch_summary["awaiting_assignment"],
                ),
                "trip_status": widget(
                    scope="Current",
                    classification="Operational",
                    provenance="DispatchAssignment.execution_status",
                    values=breakdown(
                        active_assignments,
                        "execution_status",
                        DispatchAssignment.ExecutionStatus.choices[:-1],
                    ),
                    description="Confirmed assignments that have not reached Completed.",
                    module_url="/transport-requests",
                    total=active_assignments.count(),
                ),
                "completed_trips": widget(
                    scope="Last 7 days",
                    classification="Operational",
                    provenance="DispatchAssignment.completed_at",
                    values=completed_values,
                    description="Persisted trip completions by completion date.",
                    module_url="/transport-requests",
                    total=assignments.filter(completed_at__date=today).count(),
                ),
                "fleet_state": widget(
                    scope="Current",
                    classification="Operational",
                    provenance="Vehicle registry and active assignments",
                    values=fleet_values,
                    description=(
                        "Registry state plus a separate overlapping "
                        "assigned-vehicle measure."
                    ),
                    module_url="/vehicles",
                    total=Vehicle.objects.count(),
                    secondary=breakdown(
                        Vehicle.objects.all(), "vehicle_type", Vehicle.VehicleType.choices
                    ),
                ),
                "driver_state": widget(
                    scope="Current",
                    classification="Operational",
                    provenance="Driver employment status and active assignments",
                    values=driver_values,
                    description="Employment states; Active is not a claim of dispatch eligibility.",
                    module_url="/drivers",
                    total=Driver.objects.count(),
                ),
                "inspection_results": widget(
                    scope="Today",
                    classification="Operational",
                    provenance="VehicleInspection.result",
                    values=breakdown(inspections_today, "result", VehicleInspection.Result.choices),
                    description="Persisted inspections recorded for today.",
                    module_url="/vehicles",
                    total=inspections_today.count(),
                ),
                "maintenance_activity": widget(
                    scope="Current / Today",
                    classification="Operational",
                    provenance="VehicleMaintenanceRecord.status and completed_at",
                    values=maintenance_values,
                    description=(
                        "Current maintenance workflow and factual completions today; "
                        "no predictive risk."
                    ),
                    module_url="/maintenance",
                    total=maintenance_current.count(),
                ),
                "safety_events": widget(
                    scope="Today",
                    classification="Operational",
                    provenance="DriverSafetyEvent with genuine linked telemetry",
                    values=safety_values,
                    description=(
                        "Attributed operational safety events excluding "
                        "simulated/test provenance."
                    ),
                    module_url="/alerts",
                    total=safety.count(),
                    recent=safety_recent,
                ),
                "geofence_activity": widget(
                    scope="Today",
                    classification="Operational",
                    provenance="Persisted GeofenceEvent",
                    values=geofence_values,
                    description=(
                        "Persisted entries and exits; restricted means ENTER "
                        "into a restricted geofence."
                    ),
                    module_url="/live-map",
                    total=geofence.count(),
                    recent=geofence_recent,
                ),
                "device_telemetry": widget(
                    scope="Current",
                    classification="Operational",
                    provenance="TelemetryDevice, active binding, latest TelemetryEvent",
                    values=device_values,
                    description=(
                        "Registry/binding coverage; genuine recent uses the configured "
                        f"{settings.DISPATCH_TELEMETRY_MAX_AGE_SECONDS}-second freshness window."
                    ),
                    module_url="/devices",
                    total=registered_devices.count(),
                ),
                "fuel_evidence": widget(
                    scope="Current",
                    classification="Predicted / Reference",
                    provenance="Fuel rate resolver",
                    values=fuel_values,
                    description=(
                        "Evidence basis only; predicted/reference estimates are not "
                        "actual consumption or cost."
                    ),
                    module_url="/fuel-analytics",
                    total=Vehicle.objects.filter(is_active=True).count(),
                ),
                "sos_activity": widget(
                    scope="Current",
                    classification="Operational",
                    provenance="VehicleEmergencySOS",
                    values=[
                        {"value": "ACTIVE", "label": "Active SOS", "count": active_sos.count()}
                    ],
                    description=(
                        "Active physical-button SOS records. SOS records do not store "
                        "a location."
                    ),
                    module_url="/alerts",
                    total=active_sos.count(),
                    recent=sos_recent,
                ),
            }
        )
