import io
from datetime import timedelta
from decimal import Decimal
from zipfile import ZIP_DEFLATED, ZipFile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from accounts.models import RolePermission, StaffProfile
from fleet.models import FuelPriceRecord

HEADERS = (
    "fuel_type",
    "fuel_grade",
    "price_per_liter",
    "provider",
    "source_mode",
    "effective_at",
)


def csv_upload(name, rows, headers=HEADERS):
    content = ",".join(headers) + "\n"
    content += "\n".join(",".join(str(value) for value in row) for row in rows)
    return SimpleUploadedFile(name, content.encode(), content_type="text/csv")


def xlsx_upload(name, rows, headers=HEADERS):
    sheet_rows = [headers, *rows]
    xml_rows = []
    for row_index, row in enumerate(sheet_rows, start=1):
        cells = []
        for col_index, value in enumerate(row):
            col = chr(ord("A") + col_index)
            cells.append(
                f'<c r="{col}{row_index}" t="inlineStr"><is><t>{value}</t></is></c>'
            )
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", content_types)
        workbook.writestr("xl/worksheets/sheet1.xml", sheet)
    return SimpleUploadedFile(
        name,
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


class FuelPriceImportApiTests(APITestCase):
    url = "/api/v1/vehicles/partner-fuel-prices/import/"

    def user(self, username, role, *, staff=True):
        user = get_user_model().objects.create_user(username=username, is_staff=staff)
        if staff:
            StaffProfile.objects.create(user=user, role=role)
            RolePermission.objects.get_or_create(
                role=role, module="SYSTEM_SETTINGS", action="VIEW"
            )
            if role == StaffProfile.Role.FLEET_MANAGER:
                RolePermission.objects.get_or_create(
                    role=role, module="SYSTEM_SETTINGS", action="MANAGE_PRICES"
                )
        return user

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def row(self, suffix="001", *, fuel_type="GASOLINE", fuel_grade="UNLEADED_91", price="71.25"):
        return (
            fuel_type,
            fuel_grade,
            price,
            f"ShellPH-{suffix}",
            "MANUAL",
            (timezone.now() - timedelta(hours=1)).isoformat(),
        )

    def test_csv_import_accepts_trimmed_valid_rows_and_reports_summary(self):
        client = self.client_for(self.user("manager", StaffProfile.Role.FLEET_MANAGER))
        upload = csv_upload(
            "fuel-prices.csv",
            [
                (
                    " GASOLINE ",
                    " UNLEADED_91 ",
                    " 71.25 ",
                    " ShellPH-CSV ",
                    " MANUAL ",
                    self.row()[5],
                ),
                self.row("002", fuel_type="DIESEL", fuel_grade="REGULAR_DIESEL", price="62.10"),
            ],
        )

        response = client.post(self.url, {"file": upload}, format="multipart")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_rows"], 2)
        self.assertEqual(response.data["accepted_rows"], 2)
        self.assertEqual(response.data["rejected_rows"], 0)
        self.assertIsInstance(response.data["duration_ms"], int)
        self.assertEqual(FuelPriceRecord.objects.count(), 2)
        self.assertEqual(
            FuelPriceRecord.objects.get(provider="ShellPH-CSV").price_per_liter,
            Decimal("71.2500"),
        )

    def test_permissions_require_manage_prices(self):
        dispatcher = self.client_for(self.user("dispatcher", StaffProfile.Role.DISPATCHER))
        response = dispatcher.post(
            self.url,
            {"file": csv_upload("fuel-prices.csv", [self.row()])},
            format="multipart",
        )
        self.assertEqual(response.status_code, 403)

    def test_csv_missing_unknown_headers_empty_and_utf8_errors_are_rejected(self):
        client = self.client_for(self.user("manager", StaffProfile.Role.FLEET_MANAGER))
        cases = (
            csv_upload("missing.csv", [self.row()], headers=HEADERS[:-1]),
            csv_upload("unknown.csv", [(*self.row(), "extra")], headers=(*HEADERS, "extra")),
            SimpleUploadedFile("empty.csv", b"", content_type="text/csv"),
            SimpleUploadedFile("bad.csv", b"\xff\xfe\x00", content_type="text/csv"),
        )
        for upload in cases:
            with self.subTest(name=upload.name):
                response = client.post(self.url, {"file": upload}, format="multipart")
                self.assertEqual(response.status_code, 400)
        self.assertEqual(FuelPriceRecord.objects.count(), 0)

    def test_csv_row_validation_duplicate_and_formula_values_are_reported(self):
        client = self.client_for(self.user("manager", StaffProfile.Role.FLEET_MANAGER))
        duplicate = self.row("DUP")
        upload = csv_upload(
            "fuel-prices.csv",
            [
                duplicate,
                duplicate,
                self.row("BAD", fuel_type="JET", fuel_grade="PREMIUM_95"),
                self.row("FORMULA", price="=1+1"),
            ],
        )

        response = client.post(self.url, {"file": upload}, format="multipart")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_rows"], 4)
        self.assertEqual(response.data["accepted_rows"], 1)
        self.assertEqual(response.data["rejected_rows"], 3)
        fields = {(error["row"], error["field"]) for error in response.data["errors"]}
        self.assertIn((3, "duplicate"), fields)
        self.assertIn((4, "fuel_type"), fields)
        self.assertIn((5, "price_per_liter"), fields)
        self.assertEqual(FuelPriceRecord.objects.count(), 1)

    def test_existing_duplicate_is_rejected_without_new_insert(self):
        existing = self.row("EXISTING")
        FuelPriceRecord.objects.create(
            fuel_type=existing[0],
            fuel_grade=existing[1],
            price_per_liter=existing[2],
            provider=existing[3],
            source_mode=existing[4],
            effective_at=existing[5],
        )
        client = self.client_for(self.user("manager", StaffProfile.Role.FLEET_MANAGER))
        response = client.post(
            self.url,
            {"file": csv_upload("fuel-prices.csv", [existing])},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["accepted_rows"], 0)
        self.assertEqual(response.data["rejected_rows"], 1)
        self.assertEqual(FuelPriceRecord.objects.count(), 1)

    def test_xlsx_import_uses_first_sheet_ignores_blank_rows_and_rejects_corruption(self):
        client = self.client_for(self.user("manager", StaffProfile.Role.FLEET_MANAGER))
        valid = xlsx_upload("fuel-prices.xlsx", [self.row("XLSX"), ("", "", "", "", "", "")])
        response = client.post(self.url, {"file": valid}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["accepted_rows"], 1)

        corrupt = SimpleUploadedFile(
            "fuel-prices.xlsx",
            b"not a workbook",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response = client.post(self.url, {"file": corrupt}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_unsupported_unsafe_and_oversized_files_are_rejected(self):
        client = self.client_for(self.user("manager", StaffProfile.Role.FLEET_MANAGER))
        cases = (
            SimpleUploadedFile("fuel-prices.txt", b"hello", content_type="text/plain"),
            SimpleUploadedFile("../fuel-prices.csv", b"hello", content_type="text/csv"),
            SimpleUploadedFile(
                "huge.csv",
                b"x" * 1_000_001,
                content_type="text/csv",
            ),
        )
        for upload in cases:
            with self.subTest(name=upload.name):
                response = client.post(self.url, {"file": upload}, format="multipart")
                self.assertEqual(response.status_code, 400)

    def test_bulk_csv_import_accepts_one_thousand_rows_and_records_time(self):
        client = self.client_for(self.user("manager", StaffProfile.Role.FLEET_MANAGER))
        rows = [
            self.row(str(index), fuel_type="DIESEL", fuel_grade="REGULAR_DIESEL")
            for index in range(1000)
        ]

        response = client.post(
            self.url,
            {"file": csv_upload("bulk-fuel-prices.csv", rows)},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_rows"], 1000)
        self.assertEqual(response.data["accepted_rows"], 1000)
        self.assertEqual(response.data["rejected_rows"], 0)
        self.assertIsInstance(response.data["duration_ms"], int)
        self.assertEqual(FuelPriceRecord.objects.count(), 1000)
