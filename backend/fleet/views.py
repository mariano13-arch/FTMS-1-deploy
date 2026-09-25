import mimetypes
from decimal import Decimal
from hashlib import sha256

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import UserNotification
from accounts.notifications import notify_capability_users
from accounts.permissions import (
    CanChangeVehicleStatus,
    CanCreateVehicle,
    CanEditVehicle,
    ModuleActionAccess,
    StaffAccess,
)
from accounts.roles import can_create, can_edit, has_module_permission
from telemetry.models import TelemetryDeviceBinding

from .driver_onboarding import (
    DriverUsernameConflict,
    create_driver_with_account,
    send_driver_setup_email,
)
from .fuel_price_imports import ImportFileError, import_fuel_prices
from .maintenance import transition_maintenance
from .models import (
    Driver,
    DriverDocument,
    FuelPriceRecord,
    NumberCodingRule,
    NumberCodingSuspension,
    Vehicle,
    VehicleCodingExemption,
    VehicleDocument,
    VehicleInspection,
    VehicleMaintenanceRecord,
)
from .partner_fuel_prices import GRADE_FUEL_TYPES, record_preferred_partner_price
from .safety import safety_metrics_for_drivers
from .serializers import (
    DriverDocumentSerializer,
    DriverSerializer,
    MaintenanceTransitionSerializer,
    NumberCodingRuleSerializer,
    NumberCodingSuspensionSerializer,
    VehicleCodingExemptionSerializer,
    VehicleDocumentSerializer,
    VehicleInspectionSerializer,
    VehicleMaintenanceRecordSerializer,
    VehicleSerializer,
    driver_eligibility,
)

PARTNER_GRADE_LABELS = {
    Vehicle.FuelGrade.UNLEADED_91: "Unleaded 91",
    Vehicle.FuelGrade.PREMIUM_95: "Premium 95",
    Vehicle.FuelGrade.PREMIUM_97: "Premium 97",
    Vehicle.FuelGrade.REGULAR_DIESEL: "Regular Diesel",
    Vehicle.FuelGrade.PREMIUM_DIESEL: "Premium Diesel",
}


class PartnerFuelPriceInputSerializer(serializers.Serializer):
    fuel_grade = serializers.ChoiceField(choices=tuple(PARTNER_GRADE_LABELS))
    price_per_liter = serializers.DecimalField(
        max_digits=10, decimal_places=4, min_value=Decimal("0.0001")
    )
    effective_at = serializers.DateTimeField()

    def validate_effective_at(self, value):
        if value > timezone.now():
            raise serializers.ValidationError("Effective date/time cannot be in the future.")
        return value


def partner_price_data(record):
    if record is None:
        return None
    return {
        "id": record.pk,
        "fuel_type": record.fuel_type,
        "fuel_grade": record.fuel_grade,
        "price_per_liter": str(record.price_per_liter),
        "currency": record.currency,
        "provider": record.provider,
        "source_mode": record.source_mode,
        "effective_at": record.effective_at,
        "recorded_at": record.retrieved_at,
        "is_active": record.is_active,
    }


class PartnerFuelPriceSettingsView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "SYSTEM_SETTINGS"
    permission_actions = {"GET": "VIEW", "POST": "MANAGE_PRICES"}
    http_method_names = ["get", "post", "options"]

    def get(self, request):
        records = FuelPriceRecord.objects.filter(provider="ShellPH").order_by(
            "-effective_at", "-retrieved_at", "-pk"
        )
        current = records.filter(is_active=True, effective_at__lte=timezone.now())
        vehicle_counts = dict(
            Vehicle.objects.filter(fuel_grade__in=PARTNER_GRADE_LABELS)
            .values_list("fuel_grade")
            .annotate(total=Count("pk"))
        )
        products = []
        for grade, label in PARTNER_GRADE_LABELS.items():
            products.append(
                {
                    "fuel_grade": grade,
                    "label": label,
                    "fuel_type": GRADE_FUEL_TYPES[grade],
                    "vehicle_count": vehicle_counts.get(grade, 0),
                    "current_price": partner_price_data(current.filter(fuel_grade=grade).first()),
                    "history": [
                        partner_price_data(record)
                        for record in records.filter(fuel_grade=grade)[:5]
                    ],
                }
            )
        return Response({"provider": "ShellPH", "provider_label": "Shell", "products": products})

    def post(self, request):
        serializer = PartnerFuelPriceInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = record_preferred_partner_price(**serializer.validated_data)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        return Response(partner_price_data(record), status=status.HTTP_201_CREATED)


class FuelPriceImportView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "SYSTEM_SETTINGS"
    permission_action = "MANAGE_PRICES"
    parser_classes = [MultiPartParser]
    http_method_names = ["post", "options"]

    def post(self, request):
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response(
                {"detail": "Upload a CSV or XLSX file in the file field."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            return Response(import_fuel_prices(uploaded_file), status=status.HTTP_200_OK)
        except ImportFileError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class NumberCodingCollectionView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "SYSTEM_SETTINGS"
    permission_actions = {"GET": "VIEW", "POST": "MANAGE_NUMBER_CODING"}
    http_method_names = ["get", "post", "options"]
    model = None
    serializer_class = None
    select_related = ()

    def queryset(self):
        return self.model.objects.select_related(*self.select_related).order_by("pk")

    def get(self, request):
        return Response(self.serializer_class(self.queryset(), many=True).data)

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        save_kwargs = {}
        if self.model is NumberCodingSuspension:
            save_kwargs["created_by"] = request.user
        elif self.model is VehicleCodingExemption:
            save_kwargs["verified_by"] = request.user
        serializer.save(**save_kwargs)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class NumberCodingDetailView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "SYSTEM_SETTINGS"
    permission_actions = {"GET": "VIEW", "PATCH": "MANAGE_NUMBER_CODING"}
    http_method_names = ["get", "patch", "options"]
    model = None
    serializer_class = None
    select_related = ()

    def get_object(self, record_id):
        return get_object_or_404(
            self.model.objects.select_related(*self.select_related), pk=record_id
        )

    def get(self, request, record_id):
        return Response(self.serializer_class(self.get_object(record_id)).data)

    def patch(self, request, record_id):
        serializer = self.serializer_class(
            self.get_object(record_id), data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class NumberCodingRuleListView(NumberCodingCollectionView):
    model = NumberCodingRule
    serializer_class = NumberCodingRuleSerializer


class NumberCodingRuleDetailView(NumberCodingDetailView):
    model = NumberCodingRule
    serializer_class = NumberCodingRuleSerializer


class NumberCodingSuspensionListView(NumberCodingCollectionView):
    model = NumberCodingSuspension
    serializer_class = NumberCodingSuspensionSerializer
    select_related = ("created_by",)


class NumberCodingSuspensionDetailView(NumberCodingDetailView):
    model = NumberCodingSuspension
    serializer_class = NumberCodingSuspensionSerializer
    select_related = ("created_by",)


class VehicleCodingExemptionListView(NumberCodingCollectionView):
    model = VehicleCodingExemption
    serializer_class = VehicleCodingExemptionSerializer
    select_related = ("vehicle", "verified_by")


class VehicleCodingExemptionDetailView(NumberCodingDetailView):
    model = VehicleCodingExemption
    serializer_class = VehicleCodingExemptionSerializer
    select_related = ("vehicle", "verified_by")


def vehicle_queryset():
    return Vehicle.objects.prefetch_related(
        "inspections",
        "documents",
        Prefetch(
            "telemetry_device_bindings",
            queryset=TelemetryDeviceBinding.objects.select_related("device").filter(
                unpaired_at__isnull=True
            ),
            to_attr="current_telemetry_device_bindings",
        ),
    ).annotate(document_count=Count("documents", distinct=True))


class VehiclePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class VehicleListView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "VEHICLES"
    permission_actions = {"GET": "VIEW", "POST": "CREATE"}
    parser_classes = [MultiPartParser, FormParser, JSONParser]
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
                Q(device_id__icontains=search)
                | Q(plate_number__icontains=search)
                | Q(display_name__icontains=search)
                | Q(manufacturer__icontains=search)
                | Q(model__icontains=search)
                | Q(vin__icontains=search)
                | Q(engine_number__icontains=search)
                | Q(chassis_number__icontains=search)
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
        serializer = VehicleSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def check_permissions_for(self, request, permissions):
        for permission in permissions:
            if not permission.has_permission(request, self):
                self.permission_denied(request)


class VehicleDetailView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "VEHICLES"
    permission_actions = {"GET": "VIEW", "PATCH": "EDIT"}
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "patch", "options"]

    def get_object(self, device_id):
        return get_object_or_404(vehicle_queryset(), device_id=device_id)

    def get(self, request, device_id):
        return Response(VehicleSerializer(self.get_object(device_id)).data)

    def patch(self, request, device_id):
        if not CanEditVehicle().has_permission(request, self):
            self.permission_denied(request)
        serializer = VehicleSerializer(
            self.get_object(device_id),
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class VehiclePhotoView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "VEHICLES"
    permission_action = "VIEW"
    http_method_names = ["get", "options"]

    def get(self, request, device_id):
        vehicle = get_object_or_404(Vehicle, device_id=device_id)
        if not vehicle.photo:
            raise Http404
        content_type = mimetypes.guess_type(vehicle.photo.name)[0] or "application/octet-stream"
        return FileResponse(vehicle.photo.open("rb"), content_type=content_type)


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


class VehicleInspectionDefinitionView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "INSPECTIONS"
    permission_action = "VIEW"
    http_method_names = ["get", "options"]

    def get(self, request):
        checklist = []
        for field_name in VehicleInspection.CHECKLIST_FIELDS:
            field = VehicleInspection._meta.get_field(field_name)
            checklist.append(
                {
                    "field": field_name,
                    "label": str(field.verbose_name).capitalize(),
                    "required": not field.blank,
                    "choices": [{"value": value, "label": label} for value, label in field.choices],
                }
            )
        return Response(
            {
                "inspection_types": [
                    {"value": value, "label": label}
                    for value, label in VehicleInspection.InspectionType.choices
                ],
                "results": [
                    {"value": value, "label": label}
                    for value, label in VehicleInspection.Result.choices
                ],
                "checklist": checklist,
            }
        )


class VehicleInspectionListView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "INSPECTIONS"
    permission_actions = {"GET": "VIEW", "POST": "CREATE"}
    http_method_names = ["get", "post", "options"]

    def get_vehicle(self, device_id):
        return get_object_or_404(Vehicle, device_id=device_id)

    def get(self, request, device_id):
        vehicle = self.get_vehicle(device_id)
        queryset = VehicleInspection.objects.filter(vehicle=vehicle).select_related("inspected_by")
        paginator = VehicleInspectionPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(VehicleInspectionSerializer(page, many=True).data)

    def post(self, request, device_id):
        serializer = VehicleInspectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if len(idempotency_key) > 128:
            raise serializers.ValidationError(
                {"idempotency_key": "Must not exceed 128 characters."}
            )
        cache_key = None
        if idempotency_key:
            digest = sha256(f"{request.user.pk}:{device_id}:{idempotency_key}".encode()).hexdigest()
            cache_key = f"fleet:inspection-submission:{digest}"
            if not cache.add(cache_key, "pending", timeout=300):
                inspection_id = cache.get(cache_key)
                if inspection_id != "pending":
                    inspection = (
                        VehicleInspection.objects.select_related("inspected_by")
                        .filter(
                            pk=inspection_id,
                            vehicle__device_id=device_id,
                            inspected_by=request.user,
                        )
                        .first()
                    )
                    if inspection is not None:
                        return Response(VehicleInspectionSerializer(inspection).data)
                    cache.delete(cache_key)
                    cache.add(cache_key, "pending", timeout=300)
                else:
                    return Response(
                        {"detail": "This inspection submission is already in progress."},
                        status=status.HTTP_409_CONFLICT,
                    )
        try:
            with transaction.atomic():
                vehicle = get_object_or_404(
                    Vehicle.objects.select_for_update(), device_id=device_id
                )
                serializer.save(
                    vehicle=vehicle,
                    inspected_by=request.user,
                    inspection_date=serializer.validated_data.get(
                        "inspection_date", timezone.localdate()
                    ),
                )
                if serializer.instance.result in {
                    VehicleInspection.Result.FAILED,
                    VehicleInspection.Result.NEEDS_ATTENTION,
                }:
                    inspection = serializer.instance
                    transaction.on_commit(
                        lambda: notify_capability_users(
                            module="INSPECTIONS",
                            action="VIEW",
                            notification_type=UserNotification.Type.INSPECTION_ATTENTION,
                            title="Vehicle Inspection Requires Attention",
                            message=(
                                f"{vehicle.display_name} inspection result: "
                                f"{inspection.get_result_display()}."
                            ),
                            target_url=f"/vehicles/{vehicle.device_id}",
                            source_key=(
                                f"vehicle-inspection:{inspection.pk}:{inspection.result.lower()}"
                            ),
                        ),
                        robust=True,
                    )
        except Exception:
            if cache_key:
                cache.delete(cache_key)
            raise
        if cache_key:
            cache.set(cache_key, serializer.instance.pk, timeout=86400)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class VehicleInspectionDetailView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "INSPECTIONS"
    permission_actions = {"GET": "VIEW", "PATCH": "CORRECT"}
    http_method_names = ["get", "patch", "options"]

    def get_object(self, device_id, inspection_id):
        return get_object_or_404(
            VehicleInspection.objects.select_related("vehicle", "inspected_by"),
            pk=inspection_id,
            vehicle__device_id=device_id,
        )

    def get(self, request, device_id, inspection_id):
        return Response(VehicleInspectionSerializer(self.get_object(device_id, inspection_id)).data)

    def patch(self, request, device_id, inspection_id):
        serializer = VehicleInspectionSerializer(
            self.get_object(device_id, inspection_id),
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class VehicleMaintenancePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class VehicleMaintenanceListView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "MAINTENANCE"
    permission_actions = {"GET": "VIEW", "POST": "CREATE"}
    http_method_names = ["get", "post", "options"]

    def get(self, request):
        allowed = {"vehicle", "status", "page", "page_size"}
        unknown = set(request.query_params) - allowed
        if unknown:
            raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
        queryset = VehicleMaintenanceRecord.objects.select_related(
            "vehicle", "inspection", "created_by"
        )
        vehicle = request.query_params.get("vehicle")
        if vehicle:
            queryset = queryset.filter(vehicle__device_id=vehicle)
        record_status = request.query_params.get("status")
        if record_status:
            if record_status not in VehicleMaintenanceRecord.Status.values:
                raise serializers.ValidationError({"status": "Invalid maintenance status."})
            queryset = queryset.filter(status=record_status)
        paginator = VehicleMaintenancePagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        response = paginator.get_paginated_response(
            VehicleMaintenanceRecordSerializer(page, many=True).data
        )
        response.data["can_manage"] = any(
            has_module_permission(request.user, "MAINTENANCE", action)
            for action in ("CREATE", "SCHEDULE", "START", "COMPLETE", "CANCEL")
        )
        return response

    def post(self, request):
        serializer = VehicleMaintenanceRecordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class VehicleMaintenanceDetailView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "MAINTENANCE"
    permission_action = "VIEW"
    http_method_names = ["get", "options"]

    def get(self, request, record_id):
        record = get_object_or_404(
            VehicleMaintenanceRecord.objects.select_related("vehicle", "inspection", "created_by"),
            pk=record_id,
        )
        return Response(VehicleMaintenanceRecordSerializer(record).data)


class VehicleMaintenanceTransitionView(APIView):
    permission_classes = [StaffAccess]
    http_method_names = ["post", "options"]

    def post(self, request, record_id):
        serializer = MaintenanceTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        required_action = {
            VehicleMaintenanceRecord.Status.SCHEDULED: "SCHEDULE",
            VehicleMaintenanceRecord.Status.IN_PROGRESS: "START",
            VehicleMaintenanceRecord.Status.COMPLETED: "COMPLETE",
            VehicleMaintenanceRecord.Status.CANCELLED: "CANCEL",
        }.get(serializer.validated_data["status"])
        if not required_action or not has_module_permission(
            request.user, "MAINTENANCE", required_action
        ):
            self.permission_denied(request)
        record = get_object_or_404(VehicleMaintenanceRecord, pk=record_id)
        updated = transition_maintenance(
            record.pk,
            serializer.validated_data["status"],
            serializer.validated_data.get("scheduled_at"),
        )
        updated = VehicleMaintenanceRecord.objects.select_related(
            "vehicle", "inspection", "created_by"
        ).get(pk=updated.pk)
        return Response(VehicleMaintenanceRecordSerializer(updated).data)


class VehicleDocumentPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


class VehicleDocumentListView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "VEHICLES"
    permission_action = "MANAGE_DOCUMENTS"
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
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "VEHICLES"
    permission_action = "MANAGE_DOCUMENTS"
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
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "VEHICLES"
    permission_action = "MANAGE_DOCUMENTS"
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


class DriverPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class DriverListView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DRIVERS"
    permission_actions = {"GET": "VIEW", "POST": "CREATE"}
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ["get", "post", "options"]

    def get(self, request):
        allowed = {
            "search",
            "employment_status",
            "eligibility_status",
            "work_shift",
            "rest_day",
            "page",
            "page_size",
        }
        unknown = set(request.query_params) - allowed
        if unknown:
            raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
        queryset = Driver.objects.select_related("linked_user").all()
        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(driver_code__icontains=search)
                | Q(first_name__icontains=search)
                | Q(middle_name__icontains=search)
                | Q(last_name__icontains=search)
            )
        employment = request.query_params.get("employment_status")
        if employment:
            if employment not in Driver.EmploymentStatus.values:
                raise serializers.ValidationError({"employment_status": "Invalid status."})
            queryset = queryset.filter(employment_status=employment)
        work_shift = request.query_params.get("work_shift")
        if work_shift:
            if work_shift not in Driver.WorkShift.values:
                raise serializers.ValidationError({"work_shift": "Invalid shift."})
            queryset = queryset.filter(work_shift=work_shift)
        rest_day = request.query_params.get("rest_day")
        if rest_day:
            from fleet.schedules import WEEKDAYS

            if rest_day not in WEEKDAYS:
                raise serializers.ValidationError({"rest_day": "Invalid weekday."})
            queryset = queryset.filter(weekly_rest_days__contains=[rest_day])
        eligibility = request.query_params.get("eligibility_status")
        if eligibility:
            if eligibility not in {"ELIGIBLE", "RESTRICTED", "NOT_ELIGIBLE"}:
                raise serializers.ValidationError({"eligibility_status": "Invalid status."})
            matching = [
                driver.pk for driver in queryset if driver_eligibility(driver)[0] == eligibility
            ]
            queryset = queryset.filter(pk__in=matching)
        paginator = DriverPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        safety_metrics = safety_metrics_for_drivers(driver.pk for driver in page)
        return paginator.get_paginated_response(
            DriverSerializer(
                page,
                many=True,
                context={"request": request, "safety_metrics": safety_metrics},
            ).data
        )

    def post(self, request):
        if not can_create(request.user):
            self.permission_denied(request)
        if request.data.get("linked_user") not in (None, ""):
            raise serializers.ValidationError(
                {"linked_user": "A Driver Mobile account is provisioned automatically."}
            )
        serializer = DriverSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            driver = create_driver_with_account(serializer)
        except DriverUsernameConflict:
            return Response(
                {"driver_code": ["This driver code is already used by an account."]},
                status=status.HTTP_409_CONFLICT,
            )
        email_status = send_driver_setup_email(driver)
        return Response(
            {
                **serializer.data,
                "onboarding": {
                    "account_provisioned": True,
                    "email_status": email_status,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class DriverDetailView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DRIVERS"
    permission_actions = {"GET": "VIEW", "PATCH": "EDIT"}
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ["get", "patch", "options"]

    def get_object(self, driver_id):
        return get_object_or_404(Driver.objects.select_related("linked_user"), pk=driver_id)

    def get(self, request, driver_id):
        driver = self.get_object(driver_id)
        return Response(
            DriverSerializer(
                driver,
                context={"safety_metrics": safety_metrics_for_drivers([driver.pk])},
            ).data
        )

    def patch(self, request, driver_id):
        if not can_edit(request.user):
            self.permission_denied(request)
        serializer = DriverSerializer(
            self.get_object(driver_id),
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class DriverPhotoView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DRIVERS"
    permission_action = "VIEW"
    http_method_names = ["get", "options"]

    def get(self, request, driver_id):
        driver = get_object_or_404(Driver, pk=driver_id)
        if not driver.photo:
            raise Http404
        content_type = mimetypes.guess_type(driver.photo.name)[0] or "application/octet-stream"
        return FileResponse(
            driver.photo.open("rb"),
            content_type=content_type,
            as_attachment=False,
            filename=driver.photo.name.rsplit("/", 1)[-1],
        )


class DriverDocumentListView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DRIVERS"
    permission_action = "MANAGE_DOCUMENTS"
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ["get", "post", "options"]

    def get_driver(self, driver_id):
        return get_object_or_404(Driver, pk=driver_id)

    def get(self, request, driver_id):
        driver = self.get_driver(driver_id)
        queryset = DriverDocument.objects.filter(driver=driver).select_related("uploaded_by")
        paginator = VehicleDocumentPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(DriverDocumentSerializer(page, many=True).data)

    def post(self, request, driver_id):
        if not can_edit(request.user):
            self.permission_denied(request)
        driver = self.get_driver(driver_id)
        serializer = DriverDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(driver=driver, uploaded_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class DriverDocumentDetailView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DRIVERS"
    permission_action = "MANAGE_DOCUMENTS"
    http_method_names = ["get", "options"]

    def get(self, request, driver_id, document_id):
        document = get_object_or_404(
            DriverDocument.objects.select_related("uploaded_by"),
            pk=document_id,
            driver_id=driver_id,
        )
        return Response(DriverDocumentSerializer(document).data)


class DriverDocumentFileView(APIView):
    permission_classes = [StaffAccess, ModuleActionAccess]
    permission_module = "DRIVERS"
    permission_action = "MANAGE_DOCUMENTS"
    http_method_names = ["get", "options"]

    def get(self, request, driver_id, document_id):
        document = get_object_or_404(DriverDocument, pk=document_id, driver_id=driver_id)
        content_type = mimetypes.guess_type(document.file.name)[0] or "application/octet-stream"
        return FileResponse(
            document.file.open("rb"),
            content_type=content_type,
            as_attachment=False,
            filename=document.file.name.rsplit("/", 1)[-1],
        )
