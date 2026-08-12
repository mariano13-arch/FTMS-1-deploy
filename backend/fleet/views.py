import mimetypes

from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import (
    CanChangeVehicleStatus,
    CanCreateVehicle,
    CanEditVehicle,
    StaffAccess,
)

from .models import Vehicle, VehicleDocument, VehicleInspection
from .serializers import (
    VehicleDocumentSerializer,
    VehicleInspectionSerializer,
    VehicleSerializer,
)


def vehicle_queryset():
    return Vehicle.objects.prefetch_related("inspections", "documents").annotate(
        document_count=Count("documents", distinct=True)
    )


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
        queryset = vehicle_queryset().order_by("device_id")
        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(device_id__icontains=search) | Q(plate_number__icontains=search)
                | Q(display_name__icontains=search) | Q(manufacturer__icontains=search)
                | Q(model__icontains=search) | Q(vin__icontains=search)
                | Q(engine_number__icontains=search) | Q(chassis_number__icontains=search)
                | Q(supplier_name__icontains=search)
                | Q(purchase_order_number__icontains=search)
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
        return get_object_or_404(
            vehicle_queryset(), device_id=device_id
        )

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


class VehicleInspectionPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


class VehicleInspectionListView(APIView):
    permission_classes = [StaffAccess]
    http_method_names = ["get", "post", "options"]

    def get_vehicle(self, device_id):
        return get_object_or_404(Vehicle, device_id=device_id)

    def get(self, request, device_id):
        vehicle = self.get_vehicle(device_id)
        queryset = VehicleInspection.objects.filter(vehicle=vehicle).select_related(
            "inspected_by"
        )
        paginator = VehicleInspectionPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            VehicleInspectionSerializer(page, many=True).data
        )

    def post(self, request, device_id):
        if not CanEditVehicle().has_permission(request, self):
            self.permission_denied(request)
        vehicle = self.get_vehicle(device_id)
        serializer = VehicleInspectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(vehicle=vehicle, inspected_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class VehicleInspectionDetailView(APIView):
    permission_classes = [StaffAccess]
    http_method_names = ["get", "patch", "options"]

    def get_object(self, device_id, inspection_id):
        return get_object_or_404(
            VehicleInspection.objects.select_related("vehicle", "inspected_by"),
            pk=inspection_id,
            vehicle__device_id=device_id,
        )

    def get(self, request, device_id, inspection_id):
        return Response(
            VehicleInspectionSerializer(
                self.get_object(device_id, inspection_id)
            ).data
        )

    def patch(self, request, device_id, inspection_id):
        if not CanEditVehicle().has_permission(request, self):
            self.permission_denied(request)
        serializer = VehicleInspectionSerializer(
            self.get_object(device_id, inspection_id),
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class VehicleDocumentPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


class VehicleDocumentListView(APIView):
    permission_classes = [StaffAccess]
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ["get", "post", "options"]

    def get_vehicle(self, device_id):
        return get_object_or_404(Vehicle, device_id=device_id)

    def get(self, request, device_id):
        vehicle = self.get_vehicle(device_id)
        document_type = request.query_params.get("document_type")
        allowed = {"page", "page_size", "document_type"}
        unknown = set(request.query_params) - allowed
        if unknown:
            raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
        queryset = VehicleDocument.objects.filter(vehicle=vehicle).select_related(
            "vehicle", "uploaded_by"
        )
        if document_type:
            if document_type not in VehicleDocument.DocumentType.values:
                raise serializers.ValidationError({"document_type": "Invalid document type."})
            queryset = queryset.filter(document_type=document_type)
        paginator = VehicleDocumentPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(VehicleDocumentSerializer(page, many=True).data)

    def post(self, request, device_id):
        if not CanEditVehicle().has_permission(request, self):
            self.permission_denied(request)
        vehicle = self.get_vehicle(device_id)
        serializer = VehicleDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(vehicle=vehicle, uploaded_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class VehicleDocumentDetailView(APIView):
    permission_classes = [StaffAccess]
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ["get", "patch", "options"]

    def get_object(self, device_id, document_id):
        return get_object_or_404(
            VehicleDocument.objects.select_related("vehicle", "uploaded_by"),
            pk=document_id,
            vehicle__device_id=device_id,
        )

    def get(self, request, device_id, document_id):
        return Response(VehicleDocumentSerializer(self.get_object(device_id, document_id)).data)

    def patch(self, request, device_id, document_id):
        if not CanEditVehicle().has_permission(request, self):
            self.permission_denied(request)
        serializer = VehicleDocumentSerializer(
            self.get_object(device_id, document_id), data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class VehicleDocumentFileView(APIView):
    permission_classes = [StaffAccess]
    http_method_names = ["get", "options"]

    def get(self, request, device_id, document_id):
        document = get_object_or_404(
            VehicleDocument,
            pk=document_id,
            vehicle__device_id=device_id,
        )
        content_type = mimetypes.guess_type(document.file.name)[0] or "application/octet-stream"
        return FileResponse(
            document.file.open("rb"),
            content_type=content_type,
            as_attachment=False,
            filename=document.file.name.rsplit("/", 1)[-1],
        )
