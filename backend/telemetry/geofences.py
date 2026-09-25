from django.contrib.gis.geos import Point, Polygon
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from fleet.models import Vehicle
from telemetry.models import Geofence, GeofenceEvent, TelemetryEvent


class CoordinateSerializer(serializers.Serializer):
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)


class GeofenceWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    description = serializers.CharField(
        max_length=500, allow_blank=True, required=False, default=""
    )
    category = serializers.ChoiceField(
        choices=Geofence.Category.values,
        required=False,
        default=Geofence.Category.CUSTOM,
    )
    shape_type = serializers.ChoiceField(choices=Geofence.ShapeType.values)
    vertices = CoordinateSerializer(many=True, min_length=3, max_length=100)
    center = CoordinateSerializer()
    radius_meters = serializers.IntegerField(
        min_value=25, max_value=5000, allow_null=True, required=False
    )
    color = serializers.RegexField(r"^#[0-9A-Fa-f]{6}$", required=False, default="#008F8C")
    show_on_map = serializers.BooleanField(required=False, default=True)
    is_active = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        if (
            attrs.get("shape_type") == Geofence.ShapeType.CIRCLE
            and attrs.get("radius_meters") is None
        ):
            raise serializers.ValidationError(
                {"radius_meters": "A circular geofence requires a radius."}
            )
        points = [(item["longitude"], item["latitude"]) for item in attrs["vertices"]]
        if points[0] != points[-1]:
            points.append(points[0])
        polygon = Polygon(points, srid=4326)
        if not polygon.valid:
            raise serializers.ValidationError(
                {"vertices": "The boundary crosses itself or is otherwise invalid."}
            )
        attrs["boundary"] = polygon
        center = attrs["center"]
        attrs["center_point"] = Point(center["longitude"], center["latitude"], srid=4326)
        return attrs

    def save(self, *, user, instance=None):
        data = dict(self.validated_data)
        boundary = data.pop("boundary")
        center = data.pop("center_point")
        data.pop("vertices")
        data.pop("center")
        if instance is None:
            return Geofence.objects.create(
                boundary=boundary, center=center, created_by=user, **data
            )
        for field, value in data.items():
            setattr(instance, field, value)
        instance.boundary = boundary
        instance.center = center
        instance.save()
        return instance


def boundary_vertices(geofence):
    return [
        {"longitude": point[0], "latitude": point[1]}
        for point in geofence.boundary.coords[0][:-1]
    ]


def event_payload(event):
    return {
        "id": event.pk,
        "event_type": event.event_type,
        "occurred_at": event.occurred_at,
        "latitude": event.location.y,
        "longitude": event.location.x,
        "vehicle_id": event.vehicle_id,
        "device_id": event.vehicle.device_id,
        "vehicle_name": event.vehicle.display_name,
        "plate_number": event.vehicle.plate_number,
        "geofence_id": event.geofence_id,
        "geofence_name": event.geofence.name,
        "geofence_category": event.geofence.category,
        "geofence_shape_type": event.geofence.shape_type,
        "geofence_radius_meters": event.geofence.radius_meters,
        "telemetry_event_id": event.telemetry_event.event_id,
        "telemetry_position_source": event.telemetry_event.position_source,
        "telemetry_recorded_at": event.telemetry_event.recorded_at,
        "created_at": event.created_at,
        "is_restricted_entry": (
            event.event_type == GeofenceEvent.EventType.ENTER
            and event.geofence.category == Geofence.Category.RESTRICTED
        ),
    }


def latest_vehicle_events():
    return TelemetryEvent.objects.select_related("vehicle").order_by(
        "vehicle_id", "-recorded_at", "-sequence_number", "-received_at", "-pk"
    ).distinct("vehicle_id")


def current_vehicles(geofence):
    return [
        {
            "vehicle_id": event.vehicle_id,
            "device_id": event.vehicle.device_id,
            "vehicle_name": event.vehicle.display_name,
            "plate_number": event.vehicle.plate_number,
            "recorded_at": event.recorded_at,
        }
        for event in latest_vehicle_events()
        if geofence.boundary.covers(event.location)
    ]


def geofence_payload(geofence, *, include_activity=False):
    events = geofence.events.select_related("vehicle", "geofence")
    latest = events.first()
    inside = current_vehicles(geofence)
    today = timezone.localdate()
    payload = {
        "id": geofence.pk,
        "name": geofence.name,
        "description": geofence.description,
        "category": geofence.category,
        "shape_type": geofence.shape_type,
        "vertices": boundary_vertices(geofence),
        "center": {"longitude": geofence.center.x, "latitude": geofence.center.y},
        "radius_meters": geofence.radius_meters,
        "color": geofence.color,
        "show_on_map": geofence.show_on_map,
        "is_active": geofence.is_active,
        "current_vehicle_count": len(inside),
        "event_count": geofence.events.count(),
        "entries_today": events.filter(
            event_type=GeofenceEvent.EventType.ENTER,
            occurred_at__date=today,
        ).count(),
        "exits_today": events.filter(
            event_type=GeofenceEvent.EventType.EXIT,
            occurred_at__date=today,
        ).count(),
        "latest_event": event_payload(latest) if latest else None,
        "created_at": geofence.created_at,
        "updated_at": geofence.updated_at,
    }
    if include_activity:
        payload["current_vehicles"] = inside
        payload["events"] = [
            event_payload(event)
            for event in events[:100]
        ]
    return payload


def evaluate_geofence_transitions(event):
    previous = (
        TelemetryEvent.objects.filter(vehicle=event.vehicle)
        .filter(
            Q(recorded_at__lt=event.recorded_at)
            | Q(
                recorded_at=event.recorded_at,
                sequence_number__lt=event.sequence_number,
            )
        )
        .order_by("-recorded_at", "-sequence_number", "-received_at", "-pk")
        .first()
    )
    for geofence in Geofence.objects.filter(is_active=True):
        is_inside = geofence.boundary.covers(event.location)
        was_inside = bool(previous and geofence.boundary.covers(previous.location))
        if is_inside == was_inside:
            continue
        GeofenceEvent.objects.get_or_create(
            geofence=geofence,
            vehicle=event.vehicle,
            telemetry_event=event,
            event_type=GeofenceEvent.EventType.ENTER if is_inside else GeofenceEvent.EventType.EXIT,
            defaults={"occurred_at": event.recorded_at, "location": event.location},
        )


def rebuild_geofence_activity(geofence):
    geofence.events.all().delete()
    derived = []
    for vehicle in Vehicle.objects.all():
        was_inside = False
        events = list(
            vehicle.telemetry_events.order_by(
                "-recorded_at", "-sequence_number", "-received_at", "-pk"
            )[:5000]
        )
        events.reverse()
        for event in events:
            is_inside = geofence.boundary.covers(event.location)
            if is_inside != was_inside:
                derived.append(
                    GeofenceEvent(
                        geofence=geofence,
                        vehicle=vehicle,
                        telemetry_event=event,
                        event_type=(
                            GeofenceEvent.EventType.ENTER
                            if is_inside
                            else GeofenceEvent.EventType.EXIT
                        ),
                        occurred_at=event.recorded_at,
                        location=event.location,
                    )
                )
            was_inside = is_inside
    GeofenceEvent.objects.bulk_create(derived, ignore_conflicts=True)
