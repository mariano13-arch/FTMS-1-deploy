from dataclasses import dataclass

from django.db.models import OuterRef, QuerySet, Subquery

from .models import Vehicle, VehicleInspection


@dataclass(frozen=True)
class InspectionReadiness:
    eligible: bool
    reason: str
    result: str | None


def with_latest_inspection(queryset: QuerySet[Vehicle]) -> QuerySet[Vehicle]:
    latest = VehicleInspection.objects.filter(vehicle_id=OuterRef("pk")).order_by(
        *VehicleInspection._meta.ordering
    )
    return queryset.annotate(
        dispatch_inspection_result=Subquery(latest.values("result")[:1]),
    )


def inspection_readiness(vehicle: Vehicle) -> InspectionReadiness:
    if hasattr(vehicle, "dispatch_inspection_result"):
        result = vehicle.dispatch_inspection_result
    else:
        result = (
            VehicleInspection.objects.filter(vehicle=vehicle)
            .order_by(*VehicleInspection._meta.ordering)
            .values_list("result", flat=True)
            .first()
        )
    if result is None:
        return InspectionReadiness(False, "Inspection required.", None)
    if result == VehicleInspection.Result.PASSED:
        return InspectionReadiness(True, "", result)
    if result == VehicleInspection.Result.NEEDS_ATTENTION:
        return InspectionReadiness(False, "Inspection needs attention.", result)
    if result == VehicleInspection.Result.FAILED:
        return InspectionReadiness(False, "Inspection failed.", result)
    return InspectionReadiness(False, "Inspection result is not dispatch eligible.", result)
