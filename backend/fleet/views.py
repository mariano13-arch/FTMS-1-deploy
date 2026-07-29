from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import (
    CanChangeVehicleStatus,
    CanCreateVehicle,
    CanEditVehicle,
    StaffAccess,
)

from .models import Vehicle
from .serializers import VehicleSerializer


class VehiclePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class VehicleListView(APIView):
    permission_classes = [StaffAccess]
    http_method_names = ["get", "post", "options"]

    def get(self, request):
        allowed = {"search", "is_active", "vehicle_type", "page", "page_size"}
        unknown = set(request.query_params) - allowed
        if unknown:
            raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
        for key in ("page", "page_size"):
            value = request.query_params.get(key)
            if value is not None and (not value.isdigit() or int(value) < 1):
                raise serializers.ValidationError({key: "Must be a positive integer."})
        if int(request.query_params.get("page_size", 20)) > 100:
            raise serializers.ValidationError({"page_size": "Must not exceed 100."})
        queryset = Vehicle.objects.order_by("device_id")
        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(device_id__icontains=search) | Q(plate_number__icontains=search)
                | Q(display_name__icontains=search) | Q(manufacturer__icontains=search)
                | Q(model__icontains=search)
            )
        active = request.query_params.get("is_active")
        if active is not None:
            if active not in {"true", "false"}:
                raise serializers.ValidationError({"is_active": "Must be true or false."})
            queryset = queryset.filter(is_active=active == "true")
        vehicle_type = request.query_params.get("vehicle_type")
        if vehicle_type is not None:
            if vehicle_type not in Vehicle.VehicleType.values:
                raise serializers.ValidationError({"vehicle_type": "Invalid vehicle type."})
            queryset = queryset.filter(vehicle_type=vehicle_type)
        paginator = VehiclePagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(VehicleSerializer(page, many=True).data)

    def post(self, request):
        self.check_permissions_for(request, [CanCreateVehicle()])
        serializer = VehicleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def check_permissions_for(self, request, permissions):
        for permission in permissions:
            if not permission.has_permission(request, self):
                self.permission_denied(request)


class VehicleDetailView(APIView):
    permission_classes = [StaffAccess]
    http_method_names = ["get", "patch", "options"]

    def get_object(self, device_id):
        return get_object_or_404(Vehicle, device_id=device_id)

    def get(self, request, device_id):
        return Response(VehicleSerializer(self.get_object(device_id)).data)

    def patch(self, request, device_id):
        if not CanEditVehicle().has_permission(request, self):
            self.permission_denied(request)
        serializer = VehicleSerializer(
            self.get_object(device_id), data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class VehicleStatusActionView(APIView):
    permission_classes = [StaffAccess, CanChangeVehicleStatus]
    http_method_names = ["post", "options"]
    active = True

    def post(self, request, device_id):
        if request.data:
            raise serializers.ValidationError("Request body must be empty.")
        vehicle = get_object_or_404(Vehicle, device_id=device_id)
        if vehicle.is_active != self.active:
            vehicle.is_active = self.active
            vehicle.save(update_fields=["is_active", "updated_at"])
        return Response(VehicleSerializer(vehicle).data)


class DeactivateVehicleView(VehicleStatusActionView):
    active = False


class ReactivateVehicleView(VehicleStatusActionView):
    active = True
