import csv
import io
from datetime import datetime, time, timedelta
from xml.sax.saxutils import escape as xml_escape
from zipfile import ZIP_DEFLATED, ZipFile
from zoneinfo import ZoneInfo

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, OuterRef, Q, Subquery
from django.db.models.functions import TruncDate
from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import StaffAccess, module_action_access
from fleet.models import (
    Driver,
    FuelPriceRecord,
    Vehicle,
    VehicleFuelReferenceBaseline,
    VehicleInspection,
    VehicleMaintenanceRecord,
)
from fleet.safety import safety_calibration_summary
from ml.models import FuelPrediction
from telemetry.models import (
    DriverSafetyEvent,
    Geofence,
    GeofenceEvent,
    TelemetryDevice,
    TelemetryDeviceBinding,
    TelemetryEvent,
    VehicleEmergencySOS,
)

from .execution import ACTIVE_EXECUTION_STATUSES
from .models import DispatchAssignment, TransportRequest, TransportRequestEvent

REPORT_TIMEZONE_NAME = "Asia/Manila"
REPORT_TIMEZONE = ZoneInfo(REPORT_TIMEZONE_NAME)
OUTCOME_EVENTS = {
    "approved": "APPROVED",
    "rejected": "REJECTED",
    "cancelled": "CANCELLED",
}

ReportsViewAccess = module_action_access("REPORTS", "VIEW")
ReportsExportAccess = module_action_access("REPORTS", "EXPORT")


class DriverSafetyCalibrationFilterSerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    def validate(self, attrs):
        if (
            attrs.get("date_from") is not None
            and attrs.get("date_to") is not None
            and attrs["date_from"] > attrs["date_to"]
        ):
            raise serializers.ValidationError({"date_to": "Must be on or after date_from."})
        return attrs


class DriverSafetyCalibrationReportView(APIView):
    permission_classes = [StaffAccess, ReportsViewAccess]
    http_method_names = ["get", "options"]

    def get(self, request):
        allowed = {"date_from", "date_to"}
        unknown = set(request.query_params) - allowed
        if unknown:
            raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
        serializer = DriverSafetyCalibrationFilterSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        filters = serializer.validated_data
        date_from = filters.get("date_from")
        date_to = filters.get("date_to")
        start = (
            timezone.make_aware(datetime.combine(date_from, time.min), REPORT_TIMEZONE)
            if date_from
            else None
        )
        end = (
            timezone.make_aware(
                datetime.combine(date_to + timedelta(days=1), time.min), REPORT_TIMEZONE
            )
            if date_to
            else None
        )
        summary = safety_calibration_summary(
            Driver.objects.values_list("pk", flat=True),
            completed_at_gte=start,
            completed_at_lt=end,
        )
        summary["total_eligible_driving_hours"] = round(summary["total_eligible_driving_hours"], 4)
        summary["events_per_driving_hour"] = {
            key: round(value, 4) if value is not None else None
            for key, value in summary["events_per_driving_hour"].items()
        }
        return Response(
            {
                "meta": {
                    "title": "Driver Safety Calibration",
                    "generated_at": timezone.now(),
                    "generated_by": (request.user.get_full_name().strip() or request.user.username),
                    "timezone": REPORT_TIMEZONE_NAME,
                    "date_basis": "DispatchAssignment.completed_at",
                    "period": "FILTERED" if date_from or date_to else "ALL_TIME",
                    "date_from": date_from,
                    "date_to": date_to,
                },
                "summary": summary,
            }
        )


class TransportReportFilterSerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    source = serializers.ChoiceField(choices=TransportRequest.SourceSystem.values, required=False)
    request_type = serializers.ChoiceField(
        choices=TransportRequest.RequestType.values, required=False
    )
    status = serializers.ChoiceField(choices=TransportRequest.Status.values, required=False)
    priority = serializers.ChoiceField(choices=TransportRequest.Priority.values, required=False)
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100, default=15)

    def validate(self, attrs):
        today = timezone.localdate(timezone=REPORT_TIMEZONE)
        attrs.setdefault("date_to", today)
        attrs.setdefault("date_from", attrs["date_to"] - timedelta(days=29))
        if attrs["date_from"] > attrs["date_to"]:
            raise serializers.ValidationError({"date_to": "Must be on or after date_from."})
        return attrs


class TransportReportPagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = "page_size"
    max_page_size = 100


def report_boundaries(filters):
    start = timezone.make_aware(datetime.combine(filters["date_from"], time.min), REPORT_TIMEZONE)
    end = timezone.make_aware(
        datetime.combine(filters["date_to"] + timedelta(days=1), time.min),
        REPORT_TIMEZONE,
    )
    return start, end


def apply_dimension_filters(queryset, filters, prefix=""):
    mapping = {
        "source": "source_system",
        "request_type": "request_type",
        "status": "status",
        "priority": "priority",
    }
    for parameter, field in mapping.items():
        if parameter in filters:
            queryset = queryset.filter(**{f"{prefix}{field}": filters[parameter]})
    return queryset


def choice_rows(queryset, field, choices):
    counts = {
        row[field]: row["count"]
        for row in queryset.values(field).annotate(count=Count("pk")).order_by(field)
    }
    return [
        {"value": value, "label": label, "count": counts.get(value, 0)} for value, label in choices
    ]


def request_row(item):
    return {
        "id": str(item.pk),
        "request_number": item.request_number,
        "source_system": item.source_system,
        "source_label": item.get_source_system_display(),
        "request_type": item.request_type,
        "request_type_label": item.get_request_type_display(),
        "request_category": item.request_category,
        "request_category_label": (
            item.get_request_category_display() if item.request_category else None
        ),
        "priority": item.priority,
        "priority_label": item.get_priority_display(),
        "status": item.status,
        "status_label": item.get_status_display(),
        "scheduled_pickup_at": item.scheduled_pickup_at,
        "created_at": item.created_at,
    }


def report_meta(request, filters):
    return {
        "title": "Transport Request Summary",
        "generated_at": timezone.now(),
        "generated_by": request.user.get_full_name().strip() or request.user.username,
        "timezone": REPORT_TIMEZONE_NAME,
        "date_basis": "TransportRequest.created_at",
        "date_from": filters["date_from"],
        "date_to": filters["date_to"],
        "filters": {
            key: filters.get(key)
            for key in ("source", "request_type", "status", "priority")
            if filters.get(key)
        },
    }


class TransportRequestReportView(APIView):
    permission_classes = [StaffAccess, ReportsViewAccess]
    http_method_names = ["get", "options"]

    def get(self, request):
        allowed = {
            "date_from",
            "date_to",
            "source",
            "request_type",
            "status",
            "priority",
            "page",
            "page_size",
        }
        unknown = set(request.query_params) - allowed
        if unknown:
            raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
        serializer = TransportReportFilterSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        filters = serializer.validated_data
        start, end = report_boundaries(filters)

        requests = apply_dimension_filters(
            TransportRequest.objects.filter(created_at__gte=start, created_at__lt=end),
            filters,
        )
        outcomes = apply_dimension_filters(
            TransportRequestEvent.objects.filter(created_at__gte=start, created_at__lt=end),
            filters,
            prefix="request__",
        )
        outcome_counts = {
            row["event_type"]: row["count"]
            for row in outcomes.filter(event_type__in=OUTCOME_EVENTS.values())
            .values("event_type")
            .annotate(count=Count("pk"))
        }
        current_dispatch_ready = TransportRequest.objects.filter(
            status=TransportRequest.Status.READY_FOR_DISPATCH
        ).count()
        trend = list(
            requests.annotate(day=TruncDate("created_at", tzinfo=REPORT_TIMEZONE))
            .values("day")
            .annotate(count=Count("pk"))
            .order_by("day")
        )

        paginator = TransportReportPagination()
        page = paginator.paginate_queryset(
            requests.order_by("-created_at", "-pk"), request, view=self
        )
        total_pages = paginator.page.paginator.num_pages
        return Response(
            {
                "meta": report_meta(request, filters),
                "summary": {
                    "requests_created": requests.count(),
                    "approved": outcome_counts.get(OUTCOME_EVENTS["approved"], 0),
                    "rejected": outcome_counts.get(OUTCOME_EVENTS["rejected"], 0),
                    "cancelled": outcome_counts.get(OUTCOME_EVENTS["cancelled"], 0),
                    "currently_dispatch_ready": current_dispatch_ready,
                },
                "trend": [{"date": row["day"], "count": row["count"]} for row in trend],
                "breakdowns": {
                    "by_source": choice_rows(
                        requests, "source_system", TransportRequest.SourceSystem.choices
                    ),
                    "by_status": choice_rows(requests, "status", TransportRequest.Status.choices),
                },
                "choices": {
                    "sources": [
                        {"value": value, "label": label}
                        for value, label in TransportRequest.SourceSystem.choices
                    ],
                    "request_types": [
                        {"value": value, "label": label}
                        for value, label in TransportRequest.RequestType.choices
                    ],
                    "statuses": [
                        {"value": value, "label": label}
                        for value, label in TransportRequest.Status.choices
                    ],
                    "priorities": [
                        {"value": value, "label": label}
                        for value, label in TransportRequest.Priority.choices
                    ],
                },
                "details": {
                    "count": paginator.page.paginator.count,
                    "page": paginator.page.number,
                    "page_size": paginator.get_page_size(request),
                    "total_pages": total_pages,
                    "results": [request_row(item) for item in page],
                },
            }
        )


class Echo:
    def write(self, value):
        return value


def safe_csv_cell(value):
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


TRANSPORT_EXPORT_HEADERS = [
    "Request Number",
    "Source System",
    "Request Type",
    "Category",
    "Priority",
    "Current Status",
    "Scheduled Pickup",
    "Created At",
]


def transport_export_filters(request):
    allowed = {"date_from", "date_to", "source", "request_type", "status", "priority"}
    unknown = set(request.query_params) - allowed
    if unknown:
        raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
    serializer = TransportReportFilterSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def transport_export_queryset(filters):
    start, end = report_boundaries(filters)
    return apply_dimension_filters(
        TransportRequest.objects.filter(created_at__gte=start, created_at__lt=end),
        filters,
    ).order_by("created_at", "pk")


def transport_export_row(item):
    return [
        safe_csv_cell(item.request_number),
        safe_csv_cell(item.get_source_system_display()),
        safe_csv_cell(item.get_request_type_display()),
        safe_csv_cell(item.get_request_category_display() if item.request_category else ""),
        safe_csv_cell(item.get_priority_display()),
        safe_csv_cell(item.get_status_display()),
        timezone.localtime(item.scheduled_pickup_at, REPORT_TIMEZONE).isoformat(),
        timezone.localtime(item.created_at, REPORT_TIMEZONE).isoformat(),
    ]


def transport_export_filename(filters, extension):
    return (
        f"ftms_transport_requests_{filters['date_from'].isoformat()}"
        f"_to_{filters['date_to'].isoformat()}.{extension}"
    )


def transport_export_rows(queryset):
    yield TRANSPORT_EXPORT_HEADERS
    for item in queryset.iterator(chunk_size=500):
        yield transport_export_row(item)


def xlsx_col_name(index):
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def xlsx_sheet_xml(rows):
    xml_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row, start=1):
            cell_ref = f"{xlsx_col_name(col_index)}{row_index}"
            cells.append(
                f'<c r="{cell_ref}" t="inlineStr"><is><t>{xml_escape(str(value))}</t></is></c>'
            )
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        f'{"".join(xml_rows)}'
        "</sheetData>"
        "</worksheet>"
    )


def build_xlsx(rows):
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as workbook:
        workbook.writestr(
            "[Content_Types].xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" '
                'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                "</Types>"
            ),
        )
        workbook.writestr(
            "_rels/.rels",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                'relationships/officeDocument" '
                'Target="xl/workbook.xml"/>'
                "</Relationships>"
            ),
        )
        workbook.writestr(
            "xl/workbook.xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Transport Requests" sheetId="1" r:id="rId1"/></sheets>'
                "</workbook>"
            ),
        )
        workbook.writestr(
            "xl/_rels/workbook.xml.rels",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                'relationships/worksheet" '
                'Target="worksheets/sheet1.xml"/>'
                "</Relationships>"
            ),
        )
        workbook.writestr("xl/worksheets/sheet1.xml", xlsx_sheet_xml(rows))
    return output.getvalue()


def pdf_escape(text):
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(title, rows):
    lines = [title, ""] + [" | ".join(str(cell) for cell in row) for row in rows]
    page_lines = [lines[index : index + 42] for index in range(0, len(lines), 42)] or [[]]
    objects = ["<< /Type /Catalog /Pages 2 0 R >>"]
    page_refs = []
    next_object = 3
    for page in page_lines:
        page_object = next_object
        content_object = next_object + 1
        next_object += 2
        page_refs.append(f"{page_object} 0 R")
        stream_lines = ["BT", "/F1 9 Tf", "36 800 Td", "12 TL"]
        for line in page:
            stream_lines.append(f"({pdf_escape(line[:120])}) Tj")
            stream_lines.append("T*")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("utf-8")
        objects.append(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
            f"/Contents {content_object} 0 R /Resources << /Font << /F1 {next_object} 0 R >> >> >>"
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream.decode('utf-8')}\nendstream")
    objects.insert(1, f'<< /Type /Pages /Kids [{" ".join(page_refs)}] /Count {len(page_refs)} >>')
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
    output = io.BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, item in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{index} 0 obj\n{item}\nendobj\n".encode("utf-8"))
    xref = output.tell()
    output.write(f"xref\n0 {len(offsets)}\n".encode("utf-8"))
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode("utf-8"))
    output.write(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode(
            "utf-8"
        )
    )
    return output.getvalue()


class TransportRequestReportCsvView(APIView):
    permission_classes = [StaffAccess, ReportsViewAccess, ReportsExportAccess]
    http_method_names = ["get", "options"]

    def get(self, request):
        filters = transport_export_filters(request)
        queryset = transport_export_queryset(filters)
        writer = csv.writer(Echo())

        def rows():
            for row in transport_export_rows(queryset):
                yield writer.writerow(row)

        response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="{transport_export_filename(filters, "csv")}"'
        )
        return response


class TransportRequestReportXlsxView(APIView):
    permission_classes = [StaffAccess, ReportsViewAccess, ReportsExportAccess]
    http_method_names = ["get", "options"]

    def get(self, request):
        filters = transport_export_filters(request)
        body = build_xlsx(list(transport_export_rows(transport_export_queryset(filters))))
        response = HttpResponse(
            body,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{transport_export_filename(filters, "xlsx")}"'
        )
        return response


class TransportRequestReportPdfView(APIView):
    permission_classes = [StaffAccess, ReportsViewAccess, ReportsExportAccess]
    http_method_names = ["get", "options"]

    def get(self, request):
        filters = transport_export_filters(request)
        rows = list(transport_export_rows(transport_export_queryset(filters)))
        title = (
            "FTMS Transport Request Summary "
            f"{filters['date_from'].isoformat()} to {filters['date_to'].isoformat()}"
        )
        body = build_pdf(title, rows)
        response = HttpResponse(body, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="{transport_export_filename(filters, "pdf")}"'
        )
        return response


class DispatchTripFilterSerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    vehicle = serializers.IntegerField(required=False, min_value=1)
    driver = serializers.IntegerField(required=False, min_value=1)
    execution_status = serializers.ChoiceField(
        choices=DispatchAssignment.ExecutionStatus.values, required=False
    )
    selection_mode = serializers.ChoiceField(
        choices=DispatchAssignment.SelectionMode.values, required=False
    )
    search = serializers.CharField(required=False, allow_blank=True, max_length=120)
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100, default=15)

    def validate(self, attrs):
        today = timezone.localdate(timezone=REPORT_TIMEZONE)
        attrs.setdefault("date_to", today)
        attrs.setdefault("date_from", attrs["date_to"] - timedelta(days=29))
        if attrs["date_from"] > attrs["date_to"]:
            raise serializers.ValidationError({"date_to": "Must be on or after date_from."})
        return attrs


def apply_assignment_filters(queryset, filters):
    for parameter, field in (
        ("vehicle", "vehicle_id"),
        ("driver", "driver_id"),
        ("execution_status", "execution_status"),
        ("selection_mode", "selection_mode"),
    ):
        if filters.get(parameter):
            queryset = queryset.filter(**{field: filters[parameter]})
    search = filters.get("search", "").strip()
    if search:
        queryset = queryset.filter(
            Q(transport_request__request_number__icontains=search)
            | Q(vehicle__device_id__icontains=search)
            | Q(vehicle__display_name__icontains=search)
            | Q(vehicle__plate_number__icontains=search)
            | Q(driver__driver_code__icontains=search)
            | Q(driver__first_name__icontains=search)
            | Q(driver__last_name__icontains=search)
        )
    return queryset


def duration_seconds(start, end):
    return int((end - start).total_seconds()) if start and end else None


def assignment_row(item):
    driver_name = f"{item.driver.first_name} {item.driver.last_name}".strip()
    return {
        "id": item.pk,
        "request_id": str(item.transport_request_id),
        "request_number": item.transport_request.request_number,
        "request_type_label": item.transport_request.get_request_type_display(),
        "driver": {"id": item.driver_id, "code": item.driver.driver_code, "name": driver_name},
        "vehicle": {
            "id": item.vehicle_id,
            "name": item.vehicle.display_name,
            "identifier": item.vehicle.device_id,
            "plate_number": item.vehicle.plate_number,
        },
        "selection_mode": item.selection_mode,
        "selection_mode_label": item.get_selection_mode_display(),
        "manual_override_reason": item.override_reason,
        "execution_status": item.execution_status,
        "execution_status_label": item.get_execution_status_display(),
        "confirmed_at": item.confirmed_at,
        "confirmed_by": item.confirmed_by.get_full_name().strip() or item.confirmed_by.username,
        "accepted_at": item.accepted_at,
        "execution_started_at": item.execution_started_at,
        "pickup_arrived_at": item.pickup_arrived_at,
        "pickup_departed_at": item.pickup_departed_at,
        "destination_arrived_at": item.destination_arrived_at,
        "completed_at": item.completed_at,
        "durations": {
            "assignment_to_acceptance": duration_seconds(item.confirmed_at, item.accepted_at),
            "acceptance_to_start": duration_seconds(item.accepted_at, item.execution_started_at),
            "start_to_pickup": duration_seconds(item.execution_started_at, item.pickup_arrived_at),
            "pickup_dwell": duration_seconds(item.pickup_arrived_at, item.pickup_departed_at),
            "pickup_to_destination": duration_seconds(
                item.pickup_departed_at, item.destination_arrived_at
            ),
            "destination_to_completion": duration_seconds(
                item.destination_arrived_at, item.completed_at
            ),
            "execution_duration": duration_seconds(item.execution_started_at, item.completed_at),
            "assignment_to_completion": duration_seconds(item.confirmed_at, item.completed_at),
        },
    }


def dispatch_query(request, allow_pagination=True):
    allowed = {
        "date_from",
        "date_to",
        "vehicle",
        "driver",
        "execution_status",
        "selection_mode",
        "search",
    }
    if allow_pagination:
        allowed |= {"page", "page_size"}
    unknown = set(request.query_params) - allowed
    if unknown:
        raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
    serializer = DispatchTripFilterSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    filters = serializer.validated_data
    start, end = report_boundaries(filters)
    base = DispatchAssignment.objects.select_related(
        "transport_request", "driver", "vehicle", "confirmed_by"
    )
    return filters, start, end, apply_assignment_filters(base, filters)


class DispatchTripReportView(APIView):
    permission_classes = [StaffAccess, ReportsViewAccess]
    http_method_names = ["get", "options"]

    def get(self, request):
        filters, start, end, filtered = dispatch_query(request)
        confirmed = filtered.filter(confirmed_at__gte=start, confirmed_at__lt=end)
        completed = filtered.filter(
            execution_status=DispatchAssignment.ExecutionStatus.COMPLETED,
            completed_at__gte=start,
            completed_at__lt=end,
        )
        average = completed.filter(execution_started_at__isnull=False).aggregate(
            value=Avg(
                ExpressionWrapper(
                    F("completed_at") - F("execution_started_at"), output_field=DurationField()
                )
            )
        )["value"]
        trend = list(
            confirmed.annotate(day=TruncDate("confirmed_at", tzinfo=REPORT_TIMEZONE))
            .values("day")
            .annotate(count=Count("pk"))
            .order_by("day")
        )
        paginator = TransportReportPagination()
        page = paginator.paginate_queryset(
            confirmed.order_by("-confirmed_at", "-pk"), request, view=self
        )
        return Response(
            {
                "meta": {
                    "title": "Dispatch & Trip Execution",
                    "generated_at": timezone.now(),
                    "generated_by": request.user.get_full_name().strip() or request.user.username,
                    "timezone": REPORT_TIMEZONE_NAME,
                    "date_basis": "DispatchAssignment.confirmed_at",
                    "date_from": filters["date_from"],
                    "date_to": filters["date_to"],
                },
                "summary": {
                    "assignments_confirmed": confirmed.count(),
                    "driver_acceptances": filtered.filter(
                        accepted_at__gte=start, accepted_at__lt=end
                    ).count(),
                    "trips_in_progress": filtered.filter(
                        execution_status__in=ACTIVE_EXECUTION_STATUSES
                    ).count(),
                    "completed_trips": completed.count(),
                    "average_execution_duration_seconds": int(average.total_seconds())
                    if average
                    else None,
                },
                "trend": [{"date": row["day"], "count": row["count"]} for row in trend],
                "breakdowns": {
                    "by_execution_status": choice_rows(
                        confirmed, "execution_status", DispatchAssignment.ExecutionStatus.choices
                    ),
                    "by_selection_mode": choice_rows(
                        confirmed, "selection_mode", DispatchAssignment.SelectionMode.choices
                    ),
                },
                "choices": {
                    "vehicles": [
                        {"value": row.pk, "label": f"{row.display_name} · {row.device_id}"}
                        for row in Vehicle.objects.order_by("display_name", "pk")
                    ],
                    "drivers": [
                        {
                            "value": row.pk,
                            "label": f"{row.driver_code} · {row.first_name} {row.last_name}",
                        }
                        for row in Driver.objects.order_by("driver_code", "pk")
                    ],
                    "execution_statuses": [
                        {"value": value, "label": label}
                        for value, label in DispatchAssignment.ExecutionStatus.choices
                    ],
                    "selection_modes": [
                        {"value": value, "label": label}
                        for value, label in DispatchAssignment.SelectionMode.choices
                    ],
                },
                "details": {
                    "count": paginator.page.paginator.count,
                    "page": paginator.page.number,
                    "page_size": paginator.get_page_size(request),
                    "total_pages": paginator.page.paginator.num_pages,
                    "results": [assignment_row(item) for item in page],
                },
            }
        )


class DispatchTripReportCsvView(APIView):
    permission_classes = [StaffAccess, ReportsViewAccess, ReportsExportAccess]
    http_method_names = ["get", "options"]

    def get(self, request):
        filters, start, end, filtered = dispatch_query(request, allow_pagination=False)
        queryset = filtered.filter(confirmed_at__gte=start, confirmed_at__lt=end).order_by(
            "confirmed_at", "pk"
        )
        writer = csv.writer(Echo())
        headers = [
            "Request Number",
            "Driver",
            "Driver Code",
            "Vehicle",
            "Vehicle Identifier",
            "Selection Mode",
            "Execution Status",
            "Confirmed At",
            "Accepted At",
            "Execution Started At",
            "Pickup Arrived At",
            "Pickup Departed At",
            "Destination Arrived At",
            "Completed At",
            "Execution Duration Seconds",
        ]

        def local(value):
            return timezone.localtime(value, REPORT_TIMEZONE).isoformat() if value else ""

        def rows():
            yield writer.writerow(headers)
            for item in queryset.iterator(chunk_size=500):
                row = assignment_row(item)
                yield writer.writerow(
                    [
                        safe_csv_cell(row["request_number"]),
                        safe_csv_cell(row["driver"]["name"]),
                        safe_csv_cell(row["driver"]["code"]),
                        safe_csv_cell(row["vehicle"]["name"]),
                        safe_csv_cell(row["vehicle"]["identifier"]),
                        row["selection_mode_label"],
                        row["execution_status_label"],
                        local(item.confirmed_at),
                        local(item.accepted_at),
                        local(item.execution_started_at),
                        local(item.pickup_arrived_at),
                        local(item.pickup_departed_at),
                        local(item.destination_arrived_at),
                        local(item.completed_at),
                        row["durations"]["execution_duration"]
                        if row["durations"]["execution_duration"] is not None
                        else "",
                    ]
                )

        response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
        filename = f"ftms_dispatch_trips_{filters['date_from']}_to_{filters['date_to']}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class FleetAssignmentFilterSerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    vehicle = serializers.IntegerField(required=False, min_value=1)
    vehicle_type = serializers.ChoiceField(choices=Vehicle.VehicleType.values, required=False)
    vehicle_active = serializers.BooleanField(required=False)
    vehicle_search = serializers.CharField(required=False, allow_blank=True, max_length=120)
    driver = serializers.IntegerField(required=False, min_value=1)
    employment_status = serializers.ChoiceField(
        choices=Driver.EmploymentStatus.values, required=False
    )
    driver_search = serializers.CharField(required=False, allow_blank=True, max_length=120)
    vehicle_page = serializers.IntegerField(required=False, min_value=1, default=1)
    driver_page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100, default=15)

    def validate(self, attrs):
        today = timezone.localdate(timezone=REPORT_TIMEZONE)
        attrs.setdefault("date_to", today)
        attrs.setdefault("date_from", attrs["date_to"] - timedelta(days=29))
        if attrs["date_from"] > attrs["date_to"]:
            raise serializers.ValidationError({"date_to": "Must be on or after date_from."})
        return attrs


def fleet_assignment_query(request, allow_pagination=True):
    allowed = set(FleetAssignmentFilterSerializer().fields)
    if not allow_pagination:
        allowed -= {"vehicle_page", "driver_page", "page_size"}
    unknown = set(request.query_params) - allowed
    if unknown:
        raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
    serializer = FleetAssignmentFilterSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    filters = serializer.validated_data
    start, end = report_boundaries(filters)
    vehicles = Vehicle.objects.all()
    drivers = Driver.objects.all()
    if filters.get("vehicle"):
        vehicles = vehicles.filter(pk=filters["vehicle"])
    if filters.get("vehicle_type"):
        vehicles = vehicles.filter(vehicle_type=filters["vehicle_type"])
    if "vehicle_active" in request.query_params:
        vehicles = vehicles.filter(is_active=filters["vehicle_active"])
    if filters.get("vehicle_search", "").strip():
        search = filters["vehicle_search"].strip()
        vehicles = vehicles.filter(
            Q(display_name__icontains=search)
            | Q(device_id__icontains=search)
            | Q(plate_number__icontains=search)
        )
    if filters.get("driver"):
        drivers = drivers.filter(pk=filters["driver"])
    if filters.get("employment_status"):
        drivers = drivers.filter(employment_status=filters["employment_status"])
    if filters.get("driver_search", "").strip():
        search = filters["driver_search"].strip()
        drivers = drivers.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(driver_code__icontains=search)
        )
    period_count = Count(
        "dispatch_assignments",
        filter=Q(
            dispatch_assignments__confirmed_at__gte=start,
            dispatch_assignments__confirmed_at__lt=end,
        ),
        distinct=True,
    )
    completed_count = Count(
        "dispatch_assignments",
        filter=Q(
            dispatch_assignments__execution_status=DispatchAssignment.ExecutionStatus.COMPLETED,
            dispatch_assignments__completed_at__gte=start,
            dispatch_assignments__completed_at__lt=end,
        ),
        distinct=True,
    )
    latest = DispatchAssignment.objects.filter(
        confirmed_at__gte=start, confirmed_at__lt=end
    ).order_by("-confirmed_at", "-pk")
    current = DispatchAssignment.objects.exclude(
        execution_status=DispatchAssignment.ExecutionStatus.COMPLETED
    ).order_by("-confirmed_at", "-pk")
    vehicles = vehicles.annotate(
        assignment_count=period_count,
        completed_count=completed_count,
        latest_assignment_id=Subquery(latest.filter(vehicle_id=OuterRef("pk")).values("pk")[:1]),
        current_assignment_id=Subquery(current.filter(vehicle_id=OuterRef("pk")).values("pk")[:1]),
    ).order_by("-assignment_count", "display_name", "device_id", "pk")
    drivers = drivers.annotate(
        assignment_count=period_count,
        completed_count=completed_count,
        latest_assignment_id=Subquery(latest.filter(driver_id=OuterRef("pk")).values("pk")[:1]),
        current_assignment_id=Subquery(current.filter(driver_id=OuterRef("pk")).values("pk")[:1]),
    ).order_by("-assignment_count", "last_name", "first_name", "driver_code", "pk")
    return filters, start, end, vehicles, drivers


def fleet_assignment_refs(rows):
    ids = {
        value
        for row in rows
        for value in (row.current_assignment_id, row.latest_assignment_id)
        if value
    }
    return {
        row.pk: row
        for row in DispatchAssignment.objects.filter(pk__in=ids).select_related(
            "transport_request", "vehicle", "driver"
        )
    }


def compact_assignment(item):
    if not item:
        return None
    return {
        "id": item.pk,
        "request_id": str(item.transport_request_id),
        "request_number": item.transport_request.request_number,
        "vehicle": {
            "id": item.vehicle_id,
            "name": item.vehicle.display_name,
            "identifier": item.vehicle.device_id,
        },
        "driver": {
            "id": item.driver_id,
            "code": item.driver.driver_code,
            "name": f"{item.driver.first_name} {item.driver.last_name}".strip(),
        },
        "selection_mode_label": item.get_selection_mode_display(),
        "execution_status": item.execution_status,
        "execution_status_label": item.get_execution_status_display(),
        "confirmed_at": item.confirmed_at,
    }


def vehicle_summary_row(item, refs):
    return {
        "id": item.pk,
        "name": item.display_name,
        "identifier": item.device_id,
        "plate_number": item.plate_number,
        "vehicle_type": item.vehicle_type,
        "vehicle_type_label": item.get_vehicle_type_display(),
        "is_active": item.is_active,
        "passenger_capacity": item.passenger_capacity,
        "payload_capacity_kg": item.payload_capacity_kg,
        "fuel_type": item.fuel_type,
        "fuel_type_label": item.get_fuel_type_display() if item.fuel_type else "Not recorded",
        "fuel_grade": item.fuel_grade,
        "fuel_grade_label": item.get_fuel_grade_display() if item.fuel_grade else "Not recorded",
        "assignments": item.assignment_count,
        "completed_trips": item.completed_count,
        "current_assignment": compact_assignment(refs.get(item.current_assignment_id)),
        "latest_assignment": compact_assignment(refs.get(item.latest_assignment_id)),
    }


def driver_summary_row(item, refs):
    return {
        "id": item.pk,
        "name": f"{item.first_name} {item.last_name}".strip(),
        "driver_code": item.driver_code,
        "employment_status": item.employment_status,
        "employment_status_label": item.get_employment_status_display(),
        "assignments": item.assignment_count,
        "completed_trips": item.completed_count,
        "current_assignment": compact_assignment(refs.get(item.current_assignment_id)),
        "latest_assignment": compact_assignment(refs.get(item.latest_assignment_id)),
    }


def fleet_page_payload(queryset, request, parameter, page_size, mapper):
    paginator, page = page_payload(queryset, request, parameter, page_size)
    rows = list(page)
    refs = fleet_assignment_refs(rows)
    return {
        "count": paginator.page.paginator.count,
        "page": paginator.page.number,
        "page_size": page_size,
        "total_pages": paginator.page.paginator.num_pages,
        "results": [mapper(row, refs) for row in rows],
    }


class FleetAssignmentReportView(APIView):
    permission_classes = [StaffAccess, ReportsViewAccess]
    http_method_names = ["get", "options"]

    def get(self, request):
        filters, start, end, vehicles, drivers = fleet_assignment_query(request)
        confirmed = DispatchAssignment.objects.filter(confirmed_at__gte=start, confirmed_at__lt=end)
        completed = DispatchAssignment.objects.filter(
            execution_status=DispatchAssignment.ExecutionStatus.COMPLETED,
            completed_at__gte=start,
            completed_at__lt=end,
        )
        trend = (
            confirmed.annotate(day=TruncDate("confirmed_at", tzinfo=REPORT_TIMEZONE))
            .values("day")
            .annotate(count=Count("pk"))
            .order_by("day")
        )
        by_vehicle = (
            confirmed.values("vehicle_id", "vehicle__display_name", "vehicle__device_id")
            .annotate(count=Count("pk"))
            .order_by("-count", "vehicle__display_name", "vehicle_id")[:10]
        )
        by_driver = (
            confirmed.values(
                "driver_id", "driver__driver_code", "driver__first_name", "driver__last_name"
            )
            .annotate(count=Count("pk"))
            .order_by("-count", "driver__driver_code", "driver_id")[:10]
        )
        by_type = (
            confirmed.values("vehicle__vehicle_type")
            .annotate(count=Count("pk"))
            .order_by("vehicle__vehicle_type")
        )
        type_labels = dict(Vehicle.VehicleType.choices)
        return Response(
            {
                "meta": {
                    "title": "Fleet Assignment Summary",
                    "generated_at": timezone.now(),
                    "generated_by": request.user.get_full_name().strip() or request.user.username,
                    "timezone": REPORT_TIMEZONE_NAME,
                    "date_basis": "DispatchAssignment.confirmed_at / completed_at",
                    "date_from": filters["date_from"],
                    "date_to": filters["date_to"],
                },
                "summary": {
                    "active_vehicles": Vehicle.objects.filter(is_active=True).count(),
                    "active_drivers": Driver.objects.filter(
                        employment_status=Driver.EmploymentStatus.ACTIVE
                    ).count(),
                    "assignments_confirmed": confirmed.count(),
                    "completed_trips": completed.count(),
                    "currently_assigned_vehicles": DispatchAssignment.objects.exclude(
                        execution_status=DispatchAssignment.ExecutionStatus.COMPLETED
                    )
                    .values("vehicle_id")
                    .distinct()
                    .count(),
                },
                "trend": [{"date": row["day"], "count": row["count"]} for row in trend],
                "breakdowns": {
                    "by_vehicle": [
                        {
                            "value": row["vehicle_id"],
                            "label": (
                                f"{row['vehicle__display_name']} · {row['vehicle__device_id']}"
                            ),
                            "count": row["count"],
                        }
                        for row in by_vehicle
                    ],
                    "by_driver": [
                        {
                            "value": row["driver_id"],
                            "label": (
                                f"{row['driver__driver_code']} · "
                                f"{row['driver__first_name']} {row['driver__last_name']}"
                            ),
                            "count": row["count"],
                        }
                        for row in by_driver
                    ],
                    "by_vehicle_type": [
                        {
                            "value": row["vehicle__vehicle_type"],
                            "label": type_labels[row["vehicle__vehicle_type"]],
                            "count": row["count"],
                        }
                        for row in by_type
                    ],
                },
                "choices": {
                    "vehicles": [
                        {"value": row.pk, "label": f"{row.display_name} · {row.device_id}"}
                        for row in Vehicle.objects.order_by("display_name", "pk")
                    ],
                    "vehicle_types": [
                        {"value": value, "label": label}
                        for value, label in Vehicle.VehicleType.choices
                    ],
                    "drivers": [
                        {
                            "value": row.pk,
                            "label": f"{row.driver_code} · {row.first_name} {row.last_name}",
                        }
                        for row in Driver.objects.order_by("driver_code", "pk")
                    ],
                    "employment_statuses": [
                        {"value": value, "label": label}
                        for value, label in Driver.EmploymentStatus.choices
                    ],
                },
                "vehicles": fleet_page_payload(
                    vehicles, request, "vehicle_page", filters["page_size"], vehicle_summary_row
                ),
                "drivers": fleet_page_payload(
                    drivers, request, "driver_page", filters["page_size"], driver_summary_row
                ),
            }
        )


class FleetAssignmentCsvView(APIView):
    permission_classes = [StaffAccess, ReportsViewAccess, ReportsExportAccess]
    http_method_names = ["get", "options"]

    def get(self, request, kind):
        if kind not in {"vehicles", "drivers"}:
            raise serializers.ValidationError({"kind": "Invalid export type."})
        filters, _, _, vehicles, drivers = fleet_assignment_query(request, allow_pagination=False)
        queryset = vehicles if kind == "vehicles" else drivers
        rows = list(queryset)
        refs = fleet_assignment_refs(rows)
        writer = csv.writer(Echo())

        def assignment_number(value):
            assignment = refs.get(value)
            return safe_csv_cell(assignment.transport_request.request_number) if assignment else ""

        def local(value):
            assignment = refs.get(value)
            return (
                timezone.localtime(assignment.confirmed_at, REPORT_TIMEZONE).isoformat()
                if assignment
                else ""
            )

        def content():
            if kind == "vehicles":
                yield writer.writerow(
                    [
                        "Vehicle",
                        "Vehicle Identifier",
                        "Vehicle Type",
                        "Fuel Type",
                        "Fuel Grade",
                        "Active State",
                        "Assignments in Period",
                        "Completed Trips in Period",
                        "Current Assignment",
                        "Current Execution Status",
                        "Latest Assignment in Period",
                        "Latest Assignment Confirmed At",
                    ]
                )
                for row in rows:
                    current = refs.get(row.current_assignment_id)
                    yield writer.writerow(
                        [
                            safe_csv_cell(row.display_name),
                            safe_csv_cell(row.device_id),
                            safe_csv_cell(row.get_vehicle_type_display()),
                            safe_csv_cell(
                                row.get_fuel_type_display() if row.fuel_type else "Not recorded"
                            ),
                            safe_csv_cell(
                                row.get_fuel_grade_display() if row.fuel_grade else "Not recorded"
                            ),
                            "Active" if row.is_active else "Inactive",
                            row.assignment_count,
                            row.completed_count,
                            assignment_number(row.current_assignment_id),
                            current.get_execution_status_display() if current else "",
                            assignment_number(row.latest_assignment_id),
                            local(row.latest_assignment_id),
                        ]
                    )
            else:
                yield writer.writerow(
                    [
                        "Driver",
                        "Driver Code",
                        "Employment Status",
                        "Assignments in Period",
                        "Completed Trips in Period",
                        "Current Assignment",
                        "Current Vehicle",
                        "Latest Assignment in Period",
                        "Latest Assignment Confirmed At",
                    ]
                )
                for row in rows:
                    current = refs.get(row.current_assignment_id)
                    yield writer.writerow(
                        [
                            safe_csv_cell(f"{row.first_name} {row.last_name}".strip()),
                            safe_csv_cell(row.driver_code),
                            safe_csv_cell(row.get_employment_status_display()),
                            row.assignment_count,
                            row.completed_count,
                            assignment_number(row.current_assignment_id),
                            safe_csv_cell(current.vehicle.display_name) if current else "",
                            assignment_number(row.latest_assignment_id),
                            local(row.latest_assignment_id),
                        ]
                    )

        response = StreamingHttpResponse(content(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="ftms_fleet_assignments_{kind}_'
            f'{filters["date_from"]}_to_{filters["date_to"]}.csv"'
        )
        return response


class InspectionMaintenanceFilterSerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    inspection_vehicle = serializers.IntegerField(required=False, min_value=1)
    inspection_type = serializers.ChoiceField(
        choices=VehicleInspection.InspectionType.values, required=False
    )
    inspection_result = serializers.ChoiceField(
        choices=VehicleInspection.Result.values, required=False
    )
    inspection_search = serializers.CharField(required=False, allow_blank=True, max_length=120)
    maintenance_vehicle = serializers.IntegerField(required=False, min_value=1)
    maintenance_status = serializers.ChoiceField(
        choices=VehicleMaintenanceRecord.Status.values, required=False
    )
    maintenance_source = serializers.ChoiceField(
        choices=VehicleMaintenanceRecord.Source.values, required=False
    )
    inspection_page = serializers.IntegerField(required=False, min_value=1, default=1)
    maintenance_page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100, default=15)

    def validate(self, attrs):
        today = timezone.localdate(timezone=REPORT_TIMEZONE)
        attrs.setdefault("date_to", today)
        attrs.setdefault("date_from", attrs["date_to"] - timedelta(days=29))
        if attrs["date_from"] > attrs["date_to"]:
            raise serializers.ValidationError({"date_to": "Must be on or after date_from."})
        return attrs


def maintenance_report_query(request):
    allowed = set(InspectionMaintenanceFilterSerializer().fields)
    unknown = set(request.query_params) - allowed
    if unknown:
        raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
    serializer = InspectionMaintenanceFilterSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    f = serializer.validated_data
    start, end = report_boundaries(f)
    inspections = VehicleInspection.objects.select_related("vehicle", "inspected_by").filter(
        inspection_date__gte=f["date_from"], inspection_date__lte=f["date_to"]
    )
    maintenance = VehicleMaintenanceRecord.objects.select_related(
        "vehicle", "inspection", "created_by"
    ).filter(created_at__gte=start, created_at__lt=end)
    if f.get("inspection_vehicle"):
        inspections = inspections.filter(vehicle_id=f["inspection_vehicle"])
    if f.get("inspection_type"):
        inspections = inspections.filter(inspection_type=f["inspection_type"])
    if f.get("inspection_result"):
        inspections = inspections.filter(result=f["inspection_result"])
    if f.get("inspection_search"):
        inspections = inspections.filter(
            Q(vehicle__display_name__icontains=f["inspection_search"])
            | Q(vehicle__device_id__icontains=f["inspection_search"])
        )
    if f.get("maintenance_vehicle"):
        maintenance = maintenance.filter(vehicle_id=f["maintenance_vehicle"])
    if f.get("maintenance_status"):
        maintenance = maintenance.filter(status=f["maintenance_status"])
    if f.get("maintenance_source"):
        maintenance = maintenance.filter(source=f["maintenance_source"])
    return f, start, end, inspections, maintenance


def inspection_row(item):
    checklist = {
        field.removesuffix("_condition"): {
            "value": getattr(item, field),
            "label": item._meta.get_field(field).choices
            and dict(item._meta.get_field(field).choices)[getattr(item, field)],
        }
        for field in VehicleInspection.CHECKLIST_FIELDS
    }
    return {
        "id": item.pk,
        "inspection_date": item.inspection_date,
        "inspection_type": item.inspection_type,
        "inspection_type_label": item.get_inspection_type_display(),
        "result": item.result,
        "result_label": item.get_result_display(),
        "vehicle": {
            "id": item.vehicle_id,
            "name": item.vehicle.display_name,
            "identifier": item.vehicle.device_id,
        },
        "inspector": item.inspected_by.get_full_name().strip() or item.inspected_by.username,
        "odometer_km": item.odometer_km,
        "fuel_level_percent": item.fuel_level_percent,
        "checklist": checklist,
        "exception_count": sum(
            value["value"] != VehicleInspection.Condition.OK for value in checklist.values()
        ),
        "issues_found": item.issues_found,
        "notes": item.notes,
        "related_maintenance": [
            {"id": row.pk, "title": row.title, "status_label": row.get_status_display()}
            for row in item.maintenance_records.all()
        ],
    }


def maintenance_row(item):
    linked = item.inspection
    return {
        "id": item.pk,
        "created_at": item.created_at,
        "vehicle": {
            "id": item.vehicle_id,
            "name": item.vehicle.display_name,
            "identifier": item.vehicle.device_id,
        },
        "title": item.title,
        "source": item.source,
        "source_label": item.get_source_display(),
        "status": item.status,
        "status_label": item.get_status_display(),
        "scheduled_at": item.scheduled_at,
        "started_at": item.started_at,
        "completed_at": item.completed_at,
        "notes": item.notes,
        "creator": item.created_by.get_full_name().strip() or item.created_by.username,
        "linked_inspection": {
            "id": linked.pk,
            "inspection_date": linked.inspection_date,
            "type_label": linked.get_inspection_type_display(),
            "result_label": linked.get_result_display(),
        }
        if linked
        else None,
    }


def page_payload(queryset, request, page_parameter, page_size):
    params = request.query_params.copy()
    params["page"] = params.get(page_parameter, 1)
    params["page_size"] = page_size
    request._request.GET = params
    paginator = TransportReportPagination()
    page = paginator.paginate_queryset(queryset, request)
    return paginator, page


class InspectionMaintenanceReportView(APIView):
    permission_classes = [StaffAccess, ReportsViewAccess]

    def get(self, request):
        f, start, end, inspections, maintenance = maintenance_report_query(request)
        current_maintenance = VehicleMaintenanceRecord.objects.all()
        completed = VehicleMaintenanceRecord.objects.filter(
            status="COMPLETED", completed_at__gte=start, completed_at__lt=end
        )
        inspection_counts = {
            row["result"]: row["count"]
            for row in inspections.values("result").annotate(count=Count("pk"))
        }
        checklist = [
            {
                "value": field,
                "label": field.removesuffix("_condition").replace("_", " ").title(),
                "count": inspections.filter(**{field: "NEEDS_ATTENTION"}).count(),
            }
            for field in VehicleInspection.CHECKLIST_FIELDS
        ]
        ip, inspection_page = page_payload(
            inspections.prefetch_related("maintenance_records").order_by("-inspection_date", "-pk"),
            request,
            "inspection_page",
            f["page_size"],
        )
        mp, maintenance_page = page_payload(
            maintenance.order_by("-created_at", "-pk"), request, "maintenance_page", f["page_size"]
        )

        def payload(paginator, page, mapper):
            return {
                "count": paginator.page.paginator.count,
                "page": paginator.page.number,
                "page_size": f["page_size"],
                "total_pages": paginator.page.paginator.num_pages,
                "results": [mapper(row) for row in page],
            }

        return Response(
            {
                "meta": {
                    "title": "Inspection & Maintenance",
                    "generated_at": timezone.now(),
                    "generated_by": request.user.get_full_name().strip() or request.user.username,
                    "timezone": REPORT_TIMEZONE_NAME,
                    "date_from": f["date_from"],
                    "date_to": f["date_to"],
                    "inspection_date_basis": "VehicleInspection.inspection_date",
                    "maintenance_date_basis": "VehicleMaintenanceRecord.created_at",
                },
                "summary": {
                    "inspections": inspections.count(),
                    "passed": inspection_counts.get("PASSED", 0),
                    "needs_attention": inspection_counts.get("NEEDS_ATTENTION", 0),
                    "failed": inspection_counts.get("FAILED", 0),
                    "active_maintenance": current_maintenance.filter(
                        status__in=("OPEN", "SCHEDULED", "IN_PROGRESS")
                    ).count(),
                    "completed_maintenance": completed.count(),
                },
                "trend": [
                    {"date": row["inspection_date"], "count": row["count"]}
                    for row in inspections.values("inspection_date")
                    .annotate(count=Count("pk"))
                    .order_by("inspection_date")
                ],
                "breakdowns": {
                    "inspection_results": choice_rows(
                        inspections, "result", VehicleInspection.Result.choices
                    ),
                    "checklist_attention": checklist,
                    "maintenance_status": choice_rows(
                        current_maintenance, "status", VehicleMaintenanceRecord.Status.choices
                    ),
                    "maintenance_source": choice_rows(
                        maintenance, "source", VehicleMaintenanceRecord.Source.choices
                    ),
                },
                "choices": {
                    "vehicles": [
                        {"value": row.pk, "label": f"{row.display_name} · {row.device_id}"}
                        for row in Vehicle.objects.order_by("display_name")
                    ],
                    "inspection_types": [
                        {"value": value, "label": label}
                        for value, label in VehicleInspection.InspectionType.choices
                    ],
                    "inspection_results": [
                        {"value": value, "label": label}
                        for value, label in VehicleInspection.Result.choices
                    ],
                    "maintenance_statuses": [
                        {"value": value, "label": label}
                        for value, label in VehicleMaintenanceRecord.Status.choices
                    ],
                    "maintenance_sources": [
                        {"value": value, "label": label}
                        for value, label in VehicleMaintenanceRecord.Source.choices
                    ],
                },
                "inspections": payload(ip, inspection_page, inspection_row),
                "maintenance": payload(mp, maintenance_page, maintenance_row),
            }
        )


class InspectionMaintenanceCsvView(APIView):
    permission_classes = [StaffAccess, ReportsViewAccess, ReportsExportAccess]

    def get(self, request, kind):
        f, _start, _end, inspections, maintenance = maintenance_report_query(request)
        writer = csv.writer(Echo())
        if kind == "inspections":
            headers = [
                "Inspection Date",
                "Vehicle",
                "Vehicle Identifier",
                "Inspection Type",
                "Result",
                "Inspector",
                "Odometer",
                "Fuel Percentage",
                "Exterior",
                "Interior",
                "Tires",
                "Lights",
                "Brakes",
                "Fluids",
                "Safety Equipment",
                "Issues Found",
                "Notes",
            ]
            rows = (
                [
                    item.inspection_date,
                    safe_csv_cell(item.vehicle.display_name),
                    safe_csv_cell(item.vehicle.device_id),
                    item.get_inspection_type_display(),
                    item.get_result_display(),
                    safe_csv_cell(
                        item.inspected_by.get_full_name().strip() or item.inspected_by.username
                    ),
                    item.odometer_km or "",
                    item.fuel_level_percent if item.fuel_level_percent is not None else "",
                    *[getattr(item, field) for field in VehicleInspection.CHECKLIST_FIELDS],
                    safe_csv_cell(item.issues_found),
                    safe_csv_cell(item.notes),
                ]
                for item in inspections.iterator(chunk_size=500)
            )
        elif kind == "maintenance":
            headers = [
                "Created At",
                "Vehicle",
                "Vehicle Identifier",
                "Title",
                "Source",
                "Status",
                "Scheduled At",
                "Started At",
                "Completed At",
                "Linked Inspection",
                "Notes",
            ]

            def local(value):
                return timezone.localtime(value, REPORT_TIMEZONE).isoformat() if value else ""

            rows = (
                [
                    local(item.created_at),
                    safe_csv_cell(item.vehicle.display_name),
                    safe_csv_cell(item.vehicle.device_id),
                    safe_csv_cell(item.title),
                    item.get_source_display(),
                    item.get_status_display(),
                    local(item.scheduled_at),
                    local(item.started_at),
                    local(item.completed_at),
                    item.inspection_id or "",
                    safe_csv_cell(item.notes),
                ]
                for item in maintenance.iterator(chunk_size=500)
            )
        else:
            raise serializers.ValidationError({"kind": "Use inspections or maintenance."})

        def csv_rows():
            yield writer.writerow(headers)
            for row in rows:
                yield writer.writerow(row)

        response = StreamingHttpResponse(csv_rows(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="ftms_{kind}_{f["date_from"]}_to_{f["date_to"]}.csv"'
        )
        return response


SAFETY_EVENT_VALUES = (
    TelemetryEvent.DrivingEvent.HARSH_BRAKING,
    TelemetryEvent.DrivingEvent.HARSH_ACCELERATION,
    TelemetryEvent.DrivingEvent.SHARP_TURN,
)


def telemetry_source_label(value):
    labels = {
        TelemetryEvent.PositionSource.GNSS: "GNSS",
        TelemetryEvent.PositionSource.CELLULAR_LBS: "Cellular LBS",
        TelemetryEvent.PositionSource.SIMULATED_TEST: "Simulated Test",
        TelemetryEvent.ObdSource.PHYSICAL_OBD: "Physical OBD",
        TelemetryEvent.ObdSource.SIMULATED_TEST: "Simulated Test",
    }
    return labels.get(value, value or "")


def geofence_event_label(value):
    return "Enter" if value == GeofenceEvent.EventType.ENTER else "Exit"


class SafetyGeofenceFilterSerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    safety_event_type = serializers.ChoiceField(choices=SAFETY_EVENT_VALUES, required=False)
    safety_vehicle = serializers.IntegerField(required=False, min_value=1)
    safety_driver = serializers.IntegerField(required=False, min_value=1)
    position_source = serializers.ChoiceField(
        choices=TelemetryEvent.PositionSource.values, required=False
    )
    obd_source = serializers.ChoiceField(choices=TelemetryEvent.ObdSource.values, required=False)
    safety_search = serializers.CharField(required=False, allow_blank=True, max_length=120)
    geofence_event_type = serializers.ChoiceField(
        choices=GeofenceEvent.EventType.values, required=False
    )
    category = serializers.ChoiceField(choices=Geofence.Category.values, required=False)
    geofence = serializers.UUIDField(required=False)
    geofence_vehicle = serializers.IntegerField(required=False, min_value=1)
    geofence_position_source = serializers.ChoiceField(
        choices=TelemetryEvent.PositionSource.values, required=False
    )
    geofence_search = serializers.CharField(required=False, allow_blank=True, max_length=120)
    sos_status = serializers.ChoiceField(choices=VehicleEmergencySOS.Status.values, required=False)
    sos_vehicle = serializers.IntegerField(required=False, min_value=1)
    sos_page = serializers.IntegerField(required=False, min_value=1, default=1)
    safety_page = serializers.IntegerField(required=False, min_value=1, default=1)
    geofence_page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100, default=15)

    def validate(self, attrs):
        today = timezone.localdate(timezone=REPORT_TIMEZONE)
        attrs.setdefault("date_to", today)
        attrs.setdefault("date_from", attrs["date_to"] - timedelta(days=29))
        if attrs["date_from"] > attrs["date_to"]:
            raise serializers.ValidationError({"date_to": "Must be on or after date_from."})
        return attrs


def safety_geofence_query(request, allow_pagination=True):
    allowed = set(SafetyGeofenceFilterSerializer().fields)
    if not allow_pagination:
        allowed -= {"safety_page", "geofence_page", "sos_page", "page_size"}
    unknown = set(request.query_params) - allowed
    if unknown:
        raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
    serializer = SafetyGeofenceFilterSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    filters = serializer.validated_data
    start, end = report_boundaries(filters)
    safety = (
        DriverSafetyEvent.objects.select_related(
            "driver", "vehicle", "assignment__transport_request", "telemetry_event__device"
        )
        .filter(occurred_at__gte=start, occurred_at__lt=end)
        .exclude(
            Q(telemetry_event__position_source=TelemetryEvent.PositionSource.SIMULATED_TEST)
            | Q(telemetry_event__obd_source=TelemetryEvent.ObdSource.SIMULATED_TEST)
        )
    )
    geofence = GeofenceEvent.objects.select_related(
        "geofence", "vehicle", "telemetry_event", "telemetry_event__device"
    ).filter(occurred_at__gte=start, occurred_at__lt=end)
    for parameter, field in (
        ("safety_event_type", "event_type"),
        ("safety_vehicle", "vehicle_id"),
        ("safety_driver", "driver_id"),
        ("position_source", "telemetry_event__position_source"),
        ("obd_source", "telemetry_event__obd_source"),
    ):
        if filters.get(parameter):
            safety = safety.filter(**{field: filters[parameter]})
    safety_search = filters.get("safety_search", "").strip()
    if safety_search:
        safety = safety.filter(
            Q(vehicle__display_name__icontains=safety_search)
            | Q(vehicle__device_id__icontains=safety_search)
            | Q(driver__driver_code__icontains=safety_search)
            | Q(driver__first_name__icontains=safety_search)
            | Q(driver__last_name__icontains=safety_search)
            | Q(assignment__transport_request__request_number__icontains=safety_search)
        )
    for parameter, field in (
        ("geofence_event_type", "event_type"),
        ("category", "geofence__category"),
        ("geofence", "geofence_id"),
        ("geofence_vehicle", "vehicle_id"),
        ("geofence_position_source", "telemetry_event__position_source"),
    ):
        if filters.get(parameter):
            geofence = geofence.filter(**{field: filters[parameter]})
    geofence_search = filters.get("geofence_search", "").strip()
    if geofence_search:
        geofence = geofence.filter(
            Q(geofence__name__icontains=geofence_search)
            | Q(vehicle__display_name__icontains=geofence_search)
            | Q(vehicle__device_id__icontains=geofence_search)
        )
    sos = VehicleEmergencySOS.objects.select_related("device", "vehicle", "driver").filter(
        activated_at__gte=start, activated_at__lt=end
    )
    if filters.get("sos_status"):
        sos = sos.filter(status=filters["sos_status"])
    if filters.get("sos_vehicle"):
        sos = sos.filter(vehicle_id=filters["sos_vehicle"])
    return filters, safety, geofence, sos


def safety_event_row(item):
    telemetry = item.telemetry_event
    return {
        "id": item.pk,
        "event_id": telemetry.event_id,
        "occurred_at": item.occurred_at,
        "event_type": item.event_type,
        "event_type_label": item.get_event_type_display().title(),
        "driver": {
            "id": item.driver_id,
            "code": item.driver.driver_code,
            "name": f"{item.driver.first_name} {item.driver.last_name}".strip(),
        },
        "assignment": {
            "id": item.assignment_id,
            "request_number": item.assignment.transport_request.request_number,
        },
        "vehicle": {
            "id": item.vehicle_id,
            "name": item.vehicle.display_name,
            "identifier": item.vehicle.device_id,
        },
        "device_id": telemetry.device.device_id,
        "position_source": telemetry.position_source,
        "position_source_label": telemetry_source_label(telemetry.position_source),
        "obd_source": telemetry.obd_source,
        "obd_source_label": telemetry_source_label(telemetry.obd_source)
        if telemetry.obd_source
        else None,
        "provenance": "OPERATIONAL",
    }


def sos_row(item):
    return {
        "id": item.pk,
        "status": item.status,
        "status_label": item.get_status_display(),
        "source": item.source,
        "source_label": item.get_source_display(),
        "activated_at": item.activated_at,
        "cleared_at": item.cleared_at,
        "device": {"id": item.device_id, "device_id": item.device.device_id},
        "vehicle": {
            "id": item.vehicle_id,
            "name": item.vehicle.display_name,
            "identifier": item.vehicle.device_id,
        }
        if item.vehicle
        else None,
        "driver": {
            "id": item.driver_id,
            "code": item.driver.driver_code,
            "name": f"{item.driver.first_name} {item.driver.last_name}".strip(),
        }
        if item.driver
        else None,
        "location": None,
        "location_label": "Location not stored",
    }


def geofence_event_row(item):
    restricted = (
        item.event_type == GeofenceEvent.EventType.ENTER
        and item.geofence.category == Geofence.Category.RESTRICTED
    )
    telemetry = item.telemetry_event
    return {
        "id": item.pk,
        "occurred_at": item.occurred_at,
        "created_at": item.created_at,
        "event_type": item.event_type,
        "event_type_label": geofence_event_label(item.event_type),
        "display_classification": "Restricted Zone Entry"
        if restricted
        else geofence_event_label(item.event_type),
        "geofence": {
            "id": item.geofence_id,
            "name": item.geofence.name,
            "category": item.geofence.category,
            "category_label": item.geofence.get_category_display(),
            "shape_type": item.geofence.shape_type,
            "shape_type_label": item.geofence.get_shape_type_display(),
            "radius_meters": item.geofence.radius_meters,
        },
        "vehicle": {
            "id": item.vehicle_id,
            "name": item.vehicle.display_name,
            "identifier": item.vehicle.device_id,
        },
        "latitude": item.location.y,
        "longitude": item.location.x,
        "telemetry": {
            "id": telemetry.pk,
            "event_id": telemetry.event_id,
            "recorded_at": telemetry.recorded_at,
            "position_source": telemetry.position_source,
            "position_source_label": telemetry_source_label(telemetry.position_source),
            "obd_source": telemetry.obd_source,
            "obd_source_label": telemetry_source_label(telemetry.obd_source)
            if telemetry.obd_source
            else None,
        },
    }


class SafetyGeofenceReportView(APIView):
    permission_classes = [StaffAccess, ReportsViewAccess]
    http_method_names = ["get", "options"]

    def get(self, request):
        filters, safety, geofence, sos = safety_geofence_query(request)
        safety_counts = {
            row["event_type"]: row["count"]
            for row in safety.values("event_type").annotate(count=Count("pk"))
        }
        geofence_counts = {
            row["event_type"]: row["count"]
            for row in geofence.values("event_type").annotate(count=Count("pk"))
        }
        restricted = geofence.filter(
            event_type=GeofenceEvent.EventType.ENTER,
            geofence__category=Geofence.Category.RESTRICTED,
        )
        safety_paginator, safety_page = page_payload(
            safety.order_by("-occurred_at", "-pk"),
            request,
            "safety_page",
            filters["page_size"],
        )
        geofence_paginator, geofence_page = page_payload(
            geofence.order_by("-occurred_at", "-pk"),
            request,
            "geofence_page",
            filters["page_size"],
        )
        sos_paginator, sos_page = page_payload(
            sos.order_by("-activated_at", "-pk"), request, "sos_page", filters["page_size"]
        )

        def payload(paginator, page, mapper):
            return {
                "count": paginator.page.paginator.count,
                "page": paginator.page.number,
                "page_size": filters["page_size"],
                "total_pages": paginator.page.paginator.num_pages,
                "results": [mapper(row) for row in page],
            }

        safety_choices = TelemetryEvent.DrivingEvent.choices[1:]
        return Response(
            {
                "meta": {
                    "title": "Safety, Geofence & SOS Activity",
                    "generated_at": timezone.now(),
                    "generated_by": request.user.get_full_name().strip() or request.user.username,
                    "timezone": REPORT_TIMEZONE_NAME,
                    "date_from": filters["date_from"],
                    "date_to": filters["date_to"],
                    "safety_date_basis": "DriverSafetyEvent.occurred_at",
                    "geofence_date_basis": "GeofenceEvent.occurred_at",
                    "sos_date_basis": "VehicleEmergencySOS.activated_at",
                },
                "summary": {
                    "safety_events": safety.count(),
                    "harsh_braking": safety_counts.get(
                        TelemetryEvent.DrivingEvent.HARSH_BRAKING, 0
                    ),
                    "harsh_acceleration": safety_counts.get(
                        TelemetryEvent.DrivingEvent.HARSH_ACCELERATION, 0
                    ),
                    "sharp_turns": safety_counts.get(TelemetryEvent.DrivingEvent.SHARP_TURN, 0),
                    "restricted_entries": restricted.count(),
                    "geofence_activity": geofence.count(),
                    "sos_activations": sos.count(),
                    "active_sos": sos.filter(status=VehicleEmergencySOS.Status.ACTIVE).count(),
                },
                "safety_trend": [
                    {"date": row["day"], "count": row["count"]}
                    for row in safety.annotate(day=TruncDate("occurred_at", tzinfo=REPORT_TIMEZONE))
                    .values("day")
                    .annotate(count=Count("pk"))
                    .order_by("day")
                ],
                "geofence_trend": [
                    {
                        "date": row["day"],
                        "enter": row["enter"],
                        "exit": row["exit"],
                        "count": row["enter"] + row["exit"],
                    }
                    for row in geofence.annotate(
                        day=TruncDate("occurred_at", tzinfo=REPORT_TIMEZONE)
                    )
                    .values("day")
                    .annotate(
                        enter=Count("pk", filter=Q(event_type=GeofenceEvent.EventType.ENTER)),
                        exit=Count("pk", filter=Q(event_type=GeofenceEvent.EventType.EXIT)),
                    )
                    .order_by("day")
                ],
                "breakdowns": {
                    "safety_types": [
                        {
                            "value": value,
                            "label": label.title(),
                            "count": safety_counts.get(value, 0),
                        }
                        for value, label in safety_choices
                    ],
                    "position_sources": [
                        {
                            "value": value,
                            "label": telemetry_source_label(value),
                            "count": safety.filter(telemetry_event__position_source=value).count(),
                        }
                        for value in TelemetryEvent.PositionSource.values
                    ],
                    "geofence_events": [
                        {
                            "value": value,
                            "label": geofence_event_label(value),
                            "count": geofence_counts.get(value, 0),
                        }
                        for value in GeofenceEvent.EventType.values
                    ],
                    "restricted_by_geofence": [
                        {
                            "value": row["geofence_id"],
                            "label": row["geofence__name"],
                            "count": row["count"],
                        }
                        for row in restricted.values("geofence_id", "geofence__name")
                        .annotate(count=Count("pk"))
                        .order_by("-count", "geofence__name")[:10]
                    ],
                },
                "choices": {
                    "safety_event_types": [
                        {"value": value, "label": label.title()} for value, label in safety_choices
                    ],
                    "vehicles": [
                        {"value": row.pk, "label": f"{row.display_name} · {row.device_id}"}
                        for row in Vehicle.objects.order_by("display_name", "pk")
                    ],
                    "drivers": [
                        {
                            "value": row.pk,
                            "label": f"{row.driver_code} · {row.first_name} {row.last_name}",
                        }
                        for row in Driver.objects.order_by("driver_code", "pk")
                    ],
                    "position_sources": [
                        {"value": value, "label": telemetry_source_label(value)}
                        for value in TelemetryEvent.PositionSource.values
                    ],
                    "obd_sources": [
                        {"value": value, "label": telemetry_source_label(value)}
                        for value in TelemetryEvent.ObdSource.values
                    ],
                    "geofence_event_types": [
                        {"value": value, "label": geofence_event_label(value)}
                        for value in GeofenceEvent.EventType.values
                    ],
                    "categories": [
                        {"value": value, "label": label}
                        for value, label in Geofence.Category.choices
                    ],
                    "geofences": [
                        {"value": row.pk, "label": row.name}
                        for row in Geofence.objects.order_by("name", "pk")
                    ],
                    "sos_statuses": [
                        {"value": value, "label": label}
                        for value, label in VehicleEmergencySOS.Status.choices
                    ],
                },
                "safety_events": payload(safety_paginator, safety_page, safety_event_row),
                "geofence_activity": payload(geofence_paginator, geofence_page, geofence_event_row),
                "sos_activity": payload(sos_paginator, sos_page, sos_row),
            }
        )


class SafetyGeofenceCsvView(APIView):
    permission_classes = [StaffAccess, ReportsViewAccess, ReportsExportAccess]
    http_method_names = ["get", "options"]

    def get(self, request, kind):
        if kind not in {"safety", "geofence", "sos"}:
            raise serializers.ValidationError({"kind": "Use safety, geofence, or sos."})
        filters, safety, geofence, sos = safety_geofence_query(request, allow_pagination=False)
        writer = csv.writer(Echo())

        def local(value):
            return timezone.localtime(value, REPORT_TIMEZONE).isoformat() if value else ""

        def rows():
            if kind == "safety":
                yield writer.writerow(
                    [
                        "Occurred At",
                        "Event Type",
                        "Driver",
                        "Driver Code",
                        "Request Number",
                        "Vehicle",
                        "Vehicle Identifier",
                        "Device ID",
                        "Position Source",
                        "OBD Source",
                        "Provenance",
                    ]
                )
                for item in safety.order_by("occurred_at", "pk").iterator(chunk_size=500):
                    telemetry = item.telemetry_event
                    yield writer.writerow(
                        [
                            local(item.occurred_at),
                            safe_csv_cell(item.get_event_type_display().title()),
                            safe_csv_cell(
                                f"{item.driver.first_name} {item.driver.last_name}".strip()
                            ),
                            safe_csv_cell(item.driver.driver_code),
                            safe_csv_cell(item.assignment.transport_request.request_number),
                            safe_csv_cell(item.vehicle.display_name),
                            safe_csv_cell(item.vehicle.device_id),
                            safe_csv_cell(telemetry.device.device_id),
                            safe_csv_cell(telemetry_source_label(telemetry.position_source)),
                            safe_csv_cell(
                                telemetry_source_label(telemetry.obd_source)
                                if telemetry.obd_source
                                else ""
                            ),
                            "Operational",
                        ]
                    )
            elif kind == "geofence":
                yield writer.writerow(
                    [
                        "Occurred At",
                        "Event Type",
                        "Display Classification",
                        "Geofence",
                        "Category",
                        "Vehicle",
                        "Vehicle Identifier",
                        "Position Source",
                        "Location Available",
                    ]
                )
                for item in geofence.order_by("occurred_at", "pk").iterator(chunk_size=500):
                    restricted = (
                        item.event_type == GeofenceEvent.EventType.ENTER
                        and item.geofence.category == Geofence.Category.RESTRICTED
                    )
                    yield writer.writerow(
                        [
                            local(item.occurred_at),
                            geofence_event_label(item.event_type),
                            "Restricted Zone Entry"
                            if restricted
                            else geofence_event_label(item.event_type),
                            safe_csv_cell(item.geofence.name),
                            safe_csv_cell(item.geofence.get_category_display()),
                            safe_csv_cell(item.vehicle.display_name),
                            safe_csv_cell(item.vehicle.device_id),
                            safe_csv_cell(
                                telemetry_source_label(item.telemetry_event.position_source)
                            ),
                            "Yes",
                        ]
                    )
            else:
                yield writer.writerow(
                    [
                        "Activated At",
                        "Cleared At",
                        "Status",
                        "Source",
                        "Device ID",
                        "Vehicle",
                        "Vehicle Identifier",
                        "Driver",
                        "Driver Code",
                        "Location",
                    ]
                )
                for item in sos.order_by("activated_at", "pk").iterator(chunk_size=500):
                    yield writer.writerow(
                        [
                            local(item.activated_at),
                            local(item.cleared_at),
                            item.get_status_display(),
                            item.get_source_display(),
                            safe_csv_cell(item.device.device_id),
                            safe_csv_cell(item.vehicle.display_name if item.vehicle else ""),
                            safe_csv_cell(item.vehicle.device_id if item.vehicle else ""),
                            safe_csv_cell(
                                f"{item.driver.first_name} {item.driver.last_name}".strip()
                                if item.driver
                                else ""
                            ),
                            safe_csv_cell(item.driver.driver_code if item.driver else ""),
                            "Location not stored",
                        ]
                    )

        response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="ftms_{kind}_activity_{filters["date_from"]}_to_'
            f'{filters["date_to"]}.csv"'
        )
        return response


class DeviceTelemetryFilterSerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    registry_status = serializers.ChoiceField(
        choices=TelemetryDevice.RegistrationStatus.values, required=False
    )
    binding_state = serializers.ChoiceField(choices=("PAIRED", "UNPAIRED"), required=False)
    telemetry_state = serializers.ChoiceField(choices=("RECEIVED", "NO_TELEMETRY"), required=False)
    position_source = serializers.ChoiceField(
        choices=TelemetryEvent.PositionSource.values, required=False
    )
    obd_source = serializers.ChoiceField(
        choices=(*TelemetryEvent.ObdSource.values, "NO_OBD_DATA"), required=False
    )
    vehicle = serializers.IntegerField(required=False, min_value=1)
    device_search = serializers.CharField(required=False, allow_blank=True, max_length=120)
    binding_device = serializers.IntegerField(required=False, min_value=1)
    binding_vehicle = serializers.IntegerField(required=False, min_value=1)
    binding_history_state = serializers.ChoiceField(
        choices=("ACTIVE", "HISTORICAL"), required=False
    )
    binding_search = serializers.CharField(required=False, allow_blank=True, max_length=120)
    device_page = serializers.IntegerField(required=False, min_value=1, default=1)
    binding_page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100, default=15)

    def validate(self, attrs):
        today = timezone.localdate(timezone=REPORT_TIMEZONE)
        attrs.setdefault("date_to", today)
        attrs.setdefault("date_from", attrs["date_to"] - timedelta(days=29))
        if attrs["date_from"] > attrs["date_to"]:
            raise serializers.ValidationError({"date_to": "Must be on or after date_from."})
        return attrs


def device_telemetry_query(request, allow_pagination=True):
    allowed = set(DeviceTelemetryFilterSerializer().fields)
    if not allow_pagination:
        allowed -= {"device_page", "binding_page", "page_size"}
    unknown = set(request.query_params) - allowed
    if unknown:
        raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
    serializer = DeviceTelemetryFilterSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    filters = serializer.validated_data
    start, end = report_boundaries(filters)
    active_binding = TelemetryDeviceBinding.objects.filter(
        device_id=OuterRef("pk"), unpaired_at__isnull=True
    ).order_by("-paired_at", "-pk")
    latest = TelemetryEvent.objects.filter(device_id=OuterRef("pk")).order_by(
        "-recorded_at", "-sequence_number", "-received_at", "-pk"
    )
    devices = TelemetryDevice.objects.annotate(
        active_binding_id=Subquery(active_binding.values("pk")[:1]),
        current_vehicle_id=Subquery(active_binding.values("vehicle_id")[:1]),
        latest_event_id=Subquery(latest.values("pk")[:1]),
        latest_recorded_at=Subquery(latest.values("recorded_at")[:1]),
        latest_position_source=Subquery(latest.values("position_source")[:1]),
        latest_obd_source=Subquery(latest.values("obd_source")[:1]),
        binding_count=Count("bindings", distinct=True),
    )
    if filters.get("registry_status"):
        devices = devices.filter(registration_status=filters["registry_status"])
    if filters.get("binding_state") == "PAIRED":
        devices = devices.filter(active_binding_id__isnull=False)
    elif filters.get("binding_state") == "UNPAIRED":
        devices = devices.filter(active_binding_id__isnull=True)
    if filters.get("telemetry_state") == "RECEIVED":
        devices = devices.filter(latest_event_id__isnull=False)
    elif filters.get("telemetry_state") == "NO_TELEMETRY":
        devices = devices.filter(latest_event_id__isnull=True)
    if filters.get("position_source"):
        devices = devices.filter(latest_position_source=filters["position_source"])
    if filters.get("obd_source") == "NO_OBD_DATA":
        devices = devices.filter(latest_event_id__isnull=False, latest_obd_source__isnull=True)
    elif filters.get("obd_source"):
        devices = devices.filter(latest_obd_source=filters["obd_source"])
    if filters.get("vehicle"):
        devices = devices.filter(current_vehicle_id=filters["vehicle"])
    search = filters.get("device_search", "").strip()
    if search:
        devices = devices.filter(
            Q(device_id__icontains=search)
            | Q(
                bindings__unpaired_at__isnull=True,
                bindings__vehicle__display_name__icontains=search,
            )
            | Q(
                bindings__unpaired_at__isnull=True,
                bindings__vehicle__device_id__icontains=search,
            )
        ).distinct()
    devices = devices.order_by("device_id", "pk")

    bindings = TelemetryDeviceBinding.objects.select_related(
        "device", "vehicle", "paired_by", "unpaired_by"
    ).filter(paired_at__gte=start, paired_at__lt=end)
    if filters.get("binding_device"):
        bindings = bindings.filter(device_id=filters["binding_device"])
    if filters.get("binding_vehicle"):
        bindings = bindings.filter(vehicle_id=filters["binding_vehicle"])
    if filters.get("binding_history_state") == "ACTIVE":
        bindings = bindings.filter(unpaired_at__isnull=True)
    elif filters.get("binding_history_state") == "HISTORICAL":
        bindings = bindings.filter(unpaired_at__isnull=False)
    binding_search = filters.get("binding_search", "").strip()
    if binding_search:
        bindings = bindings.filter(
            Q(device__device_id__icontains=binding_search)
            | Q(vehicle__display_name__icontains=binding_search)
            | Q(vehicle__device_id__icontains=binding_search)
        )
    return filters, start, end, devices, bindings.order_by("-paired_at", "-pk")


def device_summary_refs(rows):
    binding_ids = [row.active_binding_id for row in rows if row.active_binding_id]
    event_ids = [row.latest_event_id for row in rows if row.latest_event_id]
    return (
        {
            row.pk: row
            for row in TelemetryDeviceBinding.objects.filter(pk__in=binding_ids).select_related(
                "vehicle", "paired_by"
            )
        },
        {
            row.pk: row
            for row in TelemetryEvent.objects.filter(pk__in=event_ids).select_related("vehicle")
        },
    )


def safe_actor(user):
    if not user:
        return None
    return user.get_full_name().strip() or user.username


def device_summary_row(item, bindings, events):
    binding = bindings.get(item.active_binding_id)
    event = events.get(item.latest_event_id)
    return {
        "id": item.pk,
        "device_id": item.device_id,
        "registration_status": item.registration_status,
        "registration_status_label": item.get_registration_status_display(),
        "registered_at": item.created_at,
        "binding_state": "PAIRED" if binding else "UNPAIRED",
        "binding_state_label": "Paired" if binding else "Unpaired",
        "current_binding": {
            "id": binding.pk,
            "paired_at": binding.paired_at,
            "paired_by": safe_actor(binding.paired_by),
            "vehicle": {
                "id": binding.vehicle_id,
                "name": binding.vehicle.display_name,
                "identifier": binding.vehicle.device_id,
            },
        }
        if binding
        else None,
        "latest_telemetry": {
            "id": event.pk,
            "recorded_at": event.recorded_at,
            "received_at": event.received_at,
            "position_source": event.position_source,
            "position_source_label": telemetry_source_label(event.position_source),
            "position_accuracy_m": event.position_accuracy_m,
            "obd_source": event.obd_source,
            "obd_source_label": telemetry_source_label(event.obd_source)
            if event.obd_source
            else None,
            "latitude": event.location.y,
            "longitude": event.location.x,
        }
        if event
        else None,
        "telemetry_state": "RECEIVED" if event else "NO_TELEMETRY",
        "telemetry_state_label": "Telemetry Received" if event else "No Telemetry",
        "binding_count": item.binding_count,
    }


def binding_history_row(item):
    return {
        "id": item.pk,
        "device": {
            "id": item.device_id,
            "device_id": item.device.device_id,
            "registration_status": item.device.registration_status,
            "registration_status_label": item.device.get_registration_status_display(),
        },
        "vehicle": {
            "id": item.vehicle_id,
            "name": item.vehicle.display_name,
            "identifier": item.vehicle.device_id,
        },
        "paired_at": item.paired_at,
        "unpaired_at": item.unpaired_at,
        "binding_state": "ACTIVE" if item.unpaired_at is None else "HISTORICAL",
        "binding_state_label": "Active" if item.unpaired_at is None else "Historical",
        "paired_by": safe_actor(item.paired_by),
        "unpaired_by": safe_actor(item.unpaired_by),
    }


class DeviceTelemetryReportView(APIView):
    permission_classes = [StaffAccess, ReportsViewAccess]
    http_method_names = ["get", "options"]

    def get(self, request):
        filters, start, end, devices, bindings = device_telemetry_query(request)
        registered = TelemetryDevice.objects.filter(
            registration_status=TelemetryDevice.RegistrationStatus.REGISTERED
        )
        active_bindings = TelemetryDeviceBinding.objects.filter(unpaired_at__isnull=True)
        registered_with_telemetry = registered.filter(telemetry_events__isnull=False).distinct()
        latest = TelemetryEvent.objects.filter(device_id=OuterRef("pk")).order_by(
            "-recorded_at", "-sequence_number", "-received_at", "-pk"
        )
        registered_latest = registered.annotate(
            latest_position_source=Subquery(latest.values("position_source")[:1]),
            latest_obd_source=Subquery(latest.values("obd_source")[:1]),
            latest_event_id=Subquery(latest.values("pk")[:1]),
        )
        device_paginator, device_page = page_payload(
            devices, request, "device_page", filters["page_size"]
        )
        device_rows = list(device_page)
        binding_refs, event_refs = device_summary_refs(device_rows)
        binding_paginator, binding_page = page_payload(
            bindings, request, "binding_page", filters["page_size"]
        )
        trend = (
            TelemetryEvent.objects.filter(recorded_at__gte=start, recorded_at__lt=end)
            .annotate(day=TruncDate("recorded_at", tzinfo=REPORT_TIMEZONE))
            .values("day")
            .annotate(count=Count("pk"))
            .order_by("day")
        )
        registered_count = registered.count()
        paired_count = (
            active_bindings.filter(
                device__registration_status=TelemetryDevice.RegistrationStatus.REGISTERED
            )
            .values("device_id")
            .distinct()
            .count()
        )

        def provenance(field, choices, no_data=False):
            rows = [
                {
                    "value": value,
                    "label": telemetry_source_label(value),
                    "count": registered_latest.filter(**{field: value}).count(),
                }
                for value in choices
            ]
            if no_data:
                rows.append(
                    {
                        "value": "NO_OBD_DATA",
                        "label": "No OBD Data",
                        "count": registered_latest.filter(latest_obd_source__isnull=True).count(),
                    }
                )
            return rows

        return Response(
            {
                "meta": {
                    "title": "Device & Telemetry Availability",
                    "generated_at": timezone.now(),
                    "generated_by": request.user.get_full_name().strip() or request.user.username,
                    "timezone": REPORT_TIMEZONE_NAME,
                    "date_from": filters["date_from"],
                    "date_to": filters["date_to"],
                    "telemetry_date_basis": "TelemetryEvent.recorded_at",
                    "binding_date_basis": "TelemetryDeviceBinding.paired_at",
                    "freshness_rule": None,
                },
                "summary": {
                    "registered_devices": registered_count,
                    "paired_devices": paired_count,
                    "unpaired_devices": registered_count - paired_count,
                    "retired_devices": TelemetryDevice.objects.filter(
                        registration_status=TelemetryDevice.RegistrationStatus.RETIRED
                    ).count(),
                    "no_telemetry": registered_count - registered_with_telemetry.count(),
                },
                "trend": [{"date": row["day"], "count": row["count"]} for row in trend],
                "breakdowns": {
                    "availability": [
                        {
                            "value": "RECEIVED",
                            "label": "Telemetry Received",
                            "count": registered_with_telemetry.count(),
                        },
                        {
                            "value": "NO_TELEMETRY",
                            "label": "No Telemetry",
                            "count": registered_count - registered_with_telemetry.count(),
                        },
                    ],
                    "binding_state": [
                        {"value": "PAIRED", "label": "Paired", "count": paired_count},
                        {
                            "value": "UNPAIRED",
                            "label": "Unpaired",
                            "count": registered_count - paired_count,
                        },
                    ],
                    "position_sources": provenance(
                        "latest_position_source", TelemetryEvent.PositionSource.values
                    ),
                    "obd_sources": provenance(
                        "latest_obd_source", TelemetryEvent.ObdSource.values, no_data=True
                    ),
                },
                "choices": {
                    "registry_statuses": [
                        {"value": value, "label": label}
                        for value, label in TelemetryDevice.RegistrationStatus.choices
                    ],
                    "vehicles": [
                        {"value": row.pk, "label": f"{row.display_name} · {row.device_id}"}
                        for row in Vehicle.objects.order_by("display_name", "pk")
                    ],
                    "devices": [
                        {"value": row.pk, "label": row.device_id}
                        for row in TelemetryDevice.objects.order_by("device_id", "pk")
                    ],
                    "position_sources": [
                        {"value": value, "label": telemetry_source_label(value)}
                        for value in TelemetryEvent.PositionSource.values
                    ],
                    "obd_sources": [
                        {"value": value, "label": telemetry_source_label(value)}
                        for value in TelemetryEvent.ObdSource.values
                    ]
                    + [{"value": "NO_OBD_DATA", "label": "No OBD Data"}],
                },
                "devices": {
                    "count": device_paginator.page.paginator.count,
                    "page": device_paginator.page.number,
                    "page_size": filters["page_size"],
                    "total_pages": device_paginator.page.paginator.num_pages,
                    "results": [
                        device_summary_row(row, binding_refs, event_refs) for row in device_rows
                    ],
                },
                "bindings": {
                    "count": binding_paginator.page.paginator.count,
                    "page": binding_paginator.page.number,
                    "page_size": filters["page_size"],
                    "total_pages": binding_paginator.page.paginator.num_pages,
                    "results": [binding_history_row(row) for row in binding_page],
                },
            }
        )


class DeviceTelemetryCsvView(APIView):
    permission_classes = [StaffAccess, ReportsViewAccess, ReportsExportAccess]
    http_method_names = ["get", "options"]

    def get(self, request, kind):
        if kind not in {"devices", "bindings"}:
            raise serializers.ValidationError({"kind": "Use devices or bindings."})
        filters, _, _, devices, bindings = device_telemetry_query(request, allow_pagination=False)
        writer = csv.writer(Echo())

        def local(value):
            return timezone.localtime(value, REPORT_TIMEZONE).isoformat() if value else ""

        def rows():
            if kind == "devices":
                yield writer.writerow(
                    [
                        "Device ID",
                        "Registry State",
                        "Current Vehicle",
                        "Vehicle Identifier",
                        "Binding State",
                        "Last Telemetry",
                        "Position Source",
                        "OBD Source",
                        "Telemetry State",
                    ]
                )
                batch = list(devices)
                binding_refs, event_refs = device_summary_refs(batch)
                for item in batch:
                    row = device_summary_row(item, binding_refs, event_refs)
                    binding = row["current_binding"]
                    event = row["latest_telemetry"]
                    yield writer.writerow(
                        [
                            safe_csv_cell(row["device_id"]),
                            row["registration_status_label"],
                            safe_csv_cell(binding["vehicle"]["name"] if binding else ""),
                            safe_csv_cell(binding["vehicle"]["identifier"] if binding else ""),
                            row["binding_state_label"],
                            local(event["recorded_at"] if event else None),
                            event["position_source_label"] if event else "",
                            event["obd_source_label"] if event else "",
                            row["telemetry_state_label"],
                        ]
                    )
            else:
                yield writer.writerow(
                    [
                        "Device ID",
                        "Vehicle",
                        "Vehicle Identifier",
                        "Bound At",
                        "Unbound At",
                        "Binding State",
                        "Paired By",
                        "Unpaired By",
                    ]
                )
                for item in bindings.iterator(chunk_size=500):
                    yield writer.writerow(
                        [
                            safe_csv_cell(item.device.device_id),
                            safe_csv_cell(item.vehicle.display_name),
                            safe_csv_cell(item.vehicle.device_id),
                            local(item.paired_at),
                            local(item.unpaired_at),
                            "Active" if item.unpaired_at is None else "Historical",
                            safe_csv_cell(safe_actor(item.paired_by) or ""),
                            safe_csv_cell(safe_actor(item.unpaired_by) or ""),
                        ]
                    )

        response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="ftms_device_telemetry_{kind}_{filters["date_from"]}_to_'
            f'{filters["date_to"]}.csv"'
        )
        return response


class FuelReferenceReportFilterSerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    vehicle = serializers.IntegerField(required=False, min_value=1)
    prediction_source = serializers.CharField(required=False, max_length=40)
    fuel_type = serializers.ChoiceField(choices=Vehicle.FuelType.values, required=False)
    fuel_grade = serializers.ChoiceField(choices=Vehicle.FuelGrade.values, required=False)
    price_source = serializers.ChoiceField(
        choices=FuelPriceRecord.SourceMode.values, required=False
    )
    provider = serializers.CharField(required=False, max_length=160)
    prediction_page = serializers.IntegerField(required=False, min_value=1, default=1)
    baseline_page = serializers.IntegerField(required=False, min_value=1, default=1)
    price_page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100, default=15)

    def validate(self, attrs):
        today = timezone.localdate(timezone=REPORT_TIMEZONE)
        attrs.setdefault("date_to", today)
        attrs.setdefault("date_from", attrs["date_to"] - timedelta(days=29))
        if attrs["date_from"] > attrs["date_to"]:
            raise serializers.ValidationError({"date_to": "Must be on or after date_from."})
        return attrs


def fuel_reference_query(request, allow_pagination=True):
    allowed = set(FuelReferenceReportFilterSerializer().fields)
    if not allow_pagination:
        allowed -= {"prediction_page", "baseline_page", "price_page", "page_size"}
    unknown = set(request.query_params) - allowed
    if unknown:
        raise serializers.ValidationError({key: "Unknown filter." for key in unknown})
    serializer = FuelReferenceReportFilterSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    filters = serializer.validated_data
    start, end = report_boundaries(filters)
    predictions = FuelPrediction.objects.select_related("vehicle").filter(
        input_timestamp__gte=start, input_timestamp__lt=end
    )
    baselines = VehicleFuelReferenceBaseline.objects.select_related("vehicle").all()
    prices = FuelPriceRecord.objects.filter(effective_at__gte=start, effective_at__lt=end)
    if filters.get("vehicle"):
        predictions = predictions.filter(vehicle_id=filters["vehicle"])
        baselines = baselines.filter(vehicle_id=filters["vehicle"])
    if filters.get("prediction_source"):
        predictions = predictions.filter(source_mode=filters["prediction_source"])
    if filters.get("fuel_type"):
        predictions = predictions.filter(vehicle__fuel_type=filters["fuel_type"])
        baselines = baselines.filter(vehicle__fuel_type=filters["fuel_type"])
        prices = prices.filter(fuel_type=filters["fuel_type"])
    if filters.get("fuel_grade"):
        predictions = predictions.filter(vehicle__fuel_grade=filters["fuel_grade"])
        baselines = baselines.filter(vehicle__fuel_grade=filters["fuel_grade"])
        prices = prices.filter(fuel_grade=filters["fuel_grade"])
    if filters.get("price_source"):
        prices = prices.filter(source_mode=filters["price_source"])
    if filters.get("provider"):
        prices = prices.filter(provider=filters["provider"])
    return filters, predictions, baselines, prices


def fuel_prediction_row(item):
    operational = item.source_mode == "validated_vehicle_telemetry"
    return {
        "id": item.pk,
        "vehicle": {
            "id": item.vehicle_id,
            "name": item.vehicle.display_name,
            "identifier": item.vehicle.device_id,
        },
        "estimated_fuel_lph": item.estimated_fuel_lph,
        "input_timestamp": item.input_timestamp,
        "predicted_at": item.predicted_at,
        "model_name": item.model_name,
        "model_version": item.model_version,
        "source_mode": item.source_mode,
        "provenance_label": "Predicted · Operational telemetry"
        if operational
        else "Predicted · Non-operational source",
        "operational_source": operational,
    }


def fuel_baseline_row(item):
    return {
        "id": item.pk,
        "vehicle": {
            "id": item.vehicle_id,
            "name": item.vehicle.display_name,
            "identifier": item.vehicle.device_id,
        },
        "fuel_type": item.vehicle.fuel_type,
        "fuel_type_label": item.vehicle.get_fuel_type_display()
        if item.vehicle.fuel_type
        else "Not recorded",
        "fuel_grade": item.vehicle.fuel_grade,
        "fuel_grade_label": item.vehicle.get_fuel_grade_display()
        if item.vehicle.fuel_grade
        else "Not recorded",
        "reference_fuel_rate_lph": item.reference_fuel_rate_lph,
        "provenance": item.provenance,
        "provenance_label": "Fleet Reference Baseline · Capstone Reference",
        "basis_version": item.basis_version,
        "is_active": item.is_active,
    }


def fuel_price_row(item):
    return {
        "id": item.pk,
        "provider": item.provider,
        "fuel_type": item.fuel_type,
        "fuel_type_label": item.get_fuel_type_display(),
        "fuel_grade": item.fuel_grade,
        "fuel_grade_label": item.get_fuel_grade_display()
        if item.fuel_grade
        else "Generic / not grade-specific",
        "price_per_liter": item.price_per_liter,
        "currency": item.currency,
        "source_mode": item.source_mode,
        "source_mode_label": item.get_source_mode_display(),
        "effective_at": item.effective_at,
        "retrieved_at": item.retrieved_at,
        "is_active": item.is_active,
        "provenance_label": "Reference price",
    }


class FuelReferenceReportView(APIView):
    permission_classes = [StaffAccess, ReportsViewAccess]
    http_method_names = ["get", "options"]

    def get(self, request):
        filters, predictions, baselines, prices = fuel_reference_query(request)

        def payload(queryset, parameter, mapper):
            paginator, page = page_payload(queryset, request, parameter, filters["page_size"])
            return {
                "count": paginator.page.paginator.count,
                "page": paginator.page.number,
                "page_size": filters["page_size"],
                "total_pages": paginator.page.paginator.num_pages,
                "results": [mapper(row) for row in page],
            }

        operational = predictions.filter(source_mode="validated_vehicle_telemetry")
        latest = (
            operational.order_by("-input_timestamp")
            .values_list("input_timestamp", flat=True)
            .first()
        )
        current_prices = FuelPriceRecord.objects.filter(
            is_active=True, effective_at__lte=timezone.now()
        )
        return Response(
            {
                "meta": {
                    "title": "Fuel Predictions & Reference Data",
                    "generated_at": timezone.now(),
                    "generated_by": request.user.get_full_name().strip() or request.user.username,
                    "timezone": REPORT_TIMEZONE_NAME,
                    "date_from": filters["date_from"],
                    "date_to": filters["date_to"],
                    "prediction_date_basis": "FuelPrediction.input_timestamp",
                    "price_date_basis": "FuelPriceRecord.effective_at",
                },
                "summary": {
                    "eligible_predictions": operational.count(),
                    "vehicles_with_reference_baselines": (
                        VehicleFuelReferenceBaseline.objects.filter(is_active=True)
                    )
                    .values("vehicle_id")
                    .distinct()
                    .count(),
                    "fuel_grades_with_current_reference_price": current_prices.exclude(
                        fuel_grade=""
                    )
                    .values("fuel_grade")
                    .distinct()
                    .count(),
                    "latest_eligible_prediction_at": latest,
                },
                "choices": {
                    "vehicles": [
                        {"value": row.pk, "label": f"{row.display_name} · {row.device_id}"}
                        for row in Vehicle.objects.order_by("display_name", "pk")
                    ],
                    "prediction_sources": [
                        {"value": value, "label": value}
                        for value in FuelPrediction.objects.values_list("source_mode", flat=True)
                        .distinct()
                        .order_by("source_mode")
                    ],
                    "fuel_types": [
                        {"value": value, "label": label}
                        for value, label in Vehicle.FuelType.choices
                    ],
                    "fuel_grades": [
                        {"value": value, "label": label}
                        for value, label in Vehicle.FuelGrade.choices
                    ],
                    "price_sources": [
                        {"value": value, "label": label}
                        for value, label in FuelPriceRecord.SourceMode.choices
                    ],
                    "providers": [
                        {"value": value, "label": value}
                        for value in FuelPriceRecord.objects.values_list("provider", flat=True)
                        .distinct()
                        .order_by("provider")
                    ],
                },
                "predictions": payload(
                    predictions.order_by("-input_timestamp", "-pk"),
                    "prediction_page",
                    fuel_prediction_row,
                ),
                "baselines": payload(
                    baselines.order_by("vehicle__display_name", "pk"),
                    "baseline_page",
                    fuel_baseline_row,
                ),
                "prices": payload(
                    prices.order_by("-effective_at", "-pk"), "price_page", fuel_price_row
                ),
            }
        )


class FuelReferenceCsvView(APIView):
    permission_classes = [StaffAccess, ReportsViewAccess, ReportsExportAccess]
    http_method_names = ["get", "options"]

    def get(self, request, kind):
        if kind not in {"predictions", "baselines", "prices"}:
            raise serializers.ValidationError({"kind": "Use predictions, baselines, or prices."})
        filters, predictions, baselines, prices = fuel_reference_query(
            request, allow_pagination=False
        )
        writer = csv.writer(Echo())

        def local(value):
            return timezone.localtime(value, REPORT_TIMEZONE).isoformat() if value else ""

        def rows():
            if kind == "predictions":
                yield writer.writerow(
                    [
                        "Vehicle",
                        "Vehicle Identifier",
                        "Predicted L/h",
                        "Input Timestamp",
                        "Predicted At",
                        "Model",
                        "Model Version",
                        "Source Mode",
                        "Provenance",
                    ]
                )
                for item in predictions.order_by("input_timestamp", "pk").iterator(chunk_size=500):
                    row = fuel_prediction_row(item)
                    yield writer.writerow(
                        [
                            safe_csv_cell(item.vehicle.display_name),
                            safe_csv_cell(item.vehicle.device_id),
                            item.estimated_fuel_lph,
                            local(item.input_timestamp),
                            local(item.predicted_at),
                            safe_csv_cell(item.model_name),
                            safe_csv_cell(item.model_version),
                            safe_csv_cell(item.source_mode),
                            row["provenance_label"],
                        ]
                    )
            elif kind == "baselines":
                yield writer.writerow(
                    [
                        "Vehicle",
                        "Vehicle Identifier",
                        "Fuel Type",
                        "Fuel Grade",
                        "Reference L/h",
                        "Provenance",
                        "Basis Version",
                        "Active",
                    ]
                )
                for item in baselines.iterator(chunk_size=500):
                    yield writer.writerow(
                        [
                            safe_csv_cell(item.vehicle.display_name),
                            safe_csv_cell(item.vehicle.device_id),
                            item.vehicle.get_fuel_type_display()
                            if item.vehicle.fuel_type
                            else "Not recorded",
                            item.vehicle.get_fuel_grade_display()
                            if item.vehicle.fuel_grade
                            else "Not recorded",
                            item.reference_fuel_rate_lph,
                            item.provenance,
                            safe_csv_cell(item.basis_version),
                            "Yes" if item.is_active else "No",
                        ]
                    )
            else:
                yield writer.writerow(
                    [
                        "Provider",
                        "Fuel Type",
                        "Fuel Grade",
                        "PHP/L",
                        "Source Mode",
                        "Effective At",
                        "Retrieved At",
                        "Active",
                        "Provenance",
                    ]
                )
                for item in prices.iterator(chunk_size=500):
                    yield writer.writerow(
                        [
                            safe_csv_cell(item.provider),
                            item.get_fuel_type_display(),
                            item.get_fuel_grade_display()
                            if item.fuel_grade
                            else "Generic / not grade-specific",
                            item.price_per_liter,
                            item.get_source_mode_display(),
                            local(item.effective_at),
                            local(item.retrieved_at),
                            "Yes" if item.is_active else "No",
                            "Reference price",
                        ]
                    )

        response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            "attachment; filename="
            f'"ftms_fuel_reference_{kind}_{filters["date_from"]}'
            f'_to_{filters["date_to"]}.csv"'
        )
        return response
