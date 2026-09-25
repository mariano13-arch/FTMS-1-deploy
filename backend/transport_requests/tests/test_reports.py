import io
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from transport_requests.models import TransportRequest, TransportRequestEvent


@override_settings(TIME_ZONE="Asia/Manila")
class TransportRequestReportTests(TestCase):
    endpoint = "/api/v1/reports/transport-requests/"
    csv_endpoint = "/api/v1/reports/transport-requests/csv/"
    xlsx_endpoint = "/api/v1/reports/transport-requests/xlsx/"
    pdf_endpoint = "/api/v1/reports/transport-requests/pdf/"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="report-manager", password="test", is_staff=True
        )
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.FLEET_ADMIN)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def create_request(self, suffix, *, created_at, **overrides):
        values = {
            "source_system": TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            "external_reference": f"HMS-{suffix}",
            "request_type": TransportRequest.RequestType.GUEST_TRANSFER,
            "request_category": TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            "requester_name": "Private Guest",
            "requester_contact": "+63 SECRET",
            "pickup_name": "Hotel",
            "pickup_address": "Private pickup address",
            "pickup_latitude": "14.565200",
            "pickup_longitude": "121.028600",
            "destination_name": "Airport",
            "destination_address": "Private destination address",
            "destination_latitude": "14.508600",
            "destination_longitude": "121.019800",
            "scheduled_pickup_at": created_at + timedelta(days=1),
            "passenger_count": 2,
            "priority": TransportRequest.Priority.NORMAL,
            "status": TransportRequest.Status.FOR_APPROVAL,
            "created_by": self.user,
        }
        values.update(overrides)
        item = TransportRequest.objects.create(**values)
        TransportRequest.objects.filter(pk=item.pk).update(created_at=created_at)
        item.refresh_from_db()
        return item

    def event(self, item, event_type, created_at):
        event = TransportRequestEvent.objects.create(
            request=item,
            event_type=event_type,
            previous_status=TransportRequest.Status.FOR_APPROVAL,
            new_status=getattr(TransportRequest.Status, event_type),
            performed_by=self.user,
        )
        TransportRequestEvent.objects.filter(pk=event.pk).update(created_at=created_at)
        return event

    def test_requires_authorized_staff(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.endpoint).status_code, 401)
        ordinary = get_user_model().objects.create_user(username="ordinary")
        self.client.force_authenticate(ordinary)
        self.assertEqual(self.client.get(self.endpoint).status_code, 403)
        self.assertEqual(self.client.get(self.csv_endpoint).status_code, 403)
        self.assertEqual(self.client.get(self.xlsx_endpoint).status_code, 403)
        self.assertEqual(self.client.get(self.pdf_endpoint).status_code, 403)

    def test_kpis_use_created_at_events_and_current_dispatch_state(self):
        inside = datetime(2026, 9, 20, 4, tzinfo=datetime_timezone.utc)
        outside = datetime(2026, 9, 18, 4, tzinfo=datetime_timezone.utc)
        first = self.create_request("IN", created_at=inside)
        self.create_request("OUT", created_at=outside)
        ready = self.create_request(
            "READY", created_at=outside, status=TransportRequest.Status.READY_FOR_DISPATCH
        )
        self.event(first, "APPROVED", inside + timedelta(hours=1))
        self.event(first, "REJECTED", inside + timedelta(hours=2))
        self.event(first, "CANCELLED", inside + timedelta(hours=3))
        self.event(ready, "APPROVED", outside)

        response = self.client.get(
            self.endpoint, {"date_from": "2026-09-20", "date_to": "2026-09-20"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["summary"],
            {
                "requests_created": 1,
                "approved": 1,
                "rejected": 1,
                "cancelled": 1,
                "currently_dispatch_ready": 1,
            },
        )
        self.assertEqual(response.json()["meta"]["date_basis"], "TransportRequest.created_at")
        self.assertNotIn("completed_trips", response.json()["summary"])

    def test_manila_boundaries_are_inclusive_by_local_date_and_trend(self):
        self.create_request(
            "FIRST", created_at=datetime(2026, 9, 19, 16, tzinfo=datetime_timezone.utc)
        )  # Sep 20 00:00 Manila
        self.create_request(
            "LAST", created_at=datetime(2026, 9, 20, 15, 59, 59, tzinfo=datetime_timezone.utc)
        )  # Sep 20 23:59:59 Manila
        self.create_request(
            "NEXT", created_at=datetime(2026, 9, 20, 16, tzinfo=datetime_timezone.utc)
        )  # Sep 21 00:00 Manila

        data = self.client.get(
            self.endpoint, {"date_from": "2026-09-20", "date_to": "2026-09-20"}
        ).json()

        self.assertEqual(data["summary"]["requests_created"], 2)
        self.assertEqual(data["trend"], [{"date": "2026-09-20", "count": 2}])
        self.assertEqual(data["meta"]["timezone"], "Asia/Manila")

    def test_dimension_filters_and_breakdowns(self):
        moment = datetime(2026, 9, 20, 4, tzinfo=datetime_timezone.utc)
        self.create_request("HMS", created_at=moment)
        self.create_request(
            "SCM",
            created_at=moment,
            source_system=TransportRequest.SourceSystem.SUPPLY_CHAIN_MANAGEMENT_SYSTEM,
            request_type=TransportRequest.RequestType.SUPPLIER_PICKUP,
            request_category=TransportRequest.RequestCategory.DELIVERY_LOGISTICS,
            status=TransportRequest.Status.APPROVED,
            priority=TransportRequest.Priority.HIGH,
        )
        base = {"date_from": "2026-09-20", "date_to": "2026-09-20"}
        filters = {
            "source": TransportRequest.SourceSystem.SUPPLY_CHAIN_MANAGEMENT_SYSTEM,
            "request_type": TransportRequest.RequestType.SUPPLIER_PICKUP,
            "status": TransportRequest.Status.APPROVED,
            "priority": TransportRequest.Priority.HIGH,
        }
        for key, value in filters.items():
            with self.subTest(key=key):
                data = self.client.get(self.endpoint, {**base, key: value}).json()
                self.assertEqual(data["summary"]["requests_created"], 1)
        data = self.client.get(self.endpoint, {**base, **filters}).json()
        source = {row["value"]: row["count"] for row in data["breakdowns"]["by_source"]}
        statuses = {row["value"]: row["count"] for row in data["breakdowns"]["by_status"]}
        self.assertEqual(source[TransportRequest.SourceSystem.SUPPLY_CHAIN_MANAGEMENT_SYSTEM], 1)
        self.assertEqual(source[TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM], 0)
        self.assertEqual(statuses[TransportRequest.Status.APPROVED], 1)

    def test_detail_pagination_defaults_to_fifteen_and_is_private(self):
        moment = datetime(2026, 9, 20, 4, tzinfo=datetime_timezone.utc)
        for index in range(16):
            self.create_request(str(index), created_at=moment + timedelta(seconds=index))
        params = {"date_from": "2026-09-20", "date_to": "2026-09-20"}
        first = self.client.get(self.endpoint, params).json()
        second = self.client.get(self.endpoint, {**params, "page": 2}).json()
        self.assertEqual(first["details"]["page_size"], 15)
        self.assertEqual(first["details"]["count"], 16)
        self.assertEqual(first["details"]["total_pages"], 2)
        self.assertEqual(len(first["details"]["results"]), 15)
        self.assertEqual(len(second["details"]["results"]), 1)
        row = first["details"]["results"][0]
        self.assertTrue(
            {
                "requester_name",
                "requester_contact",
                "pickup_address",
                "destination_address",
            }.isdisjoint(row)
        )
        self.assertEqual(
            self.client.get(self.endpoint, {**params, "page_size": 101}).status_code, 400
        )
        self.assertEqual(self.client.get(self.endpoint, {**params, "page": 9}).status_code, 404)

    def test_csv_is_authorized_filtered_complete_and_formula_safe(self):
        moment = datetime(2026, 9, 20, 4, tzinfo=datetime_timezone.utc)
        for index in range(16):
            self.create_request(str(index), created_at=moment + timedelta(seconds=index))
        malicious = self.create_request("FORMULA", created_at=moment)
        TransportRequest.objects.filter(pk=malicious.pk).update(request_number="=DANGEROUS")
        special = self.create_request("SPECIAL", created_at=moment)
        TransportRequest.objects.filter(pk=special.pk).update(request_number='TR,"SPECIAL"')
        response = self.client.get(
            self.csv_endpoint,
            {
                "date_from": "2026-09-20",
                "date_to": "2026-09-20",
                "source": TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            },
        )
        body = b"".join(response.streaming_content).decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertEqual(len(body.strip().splitlines()), 19)
        self.assertEqual(
            body.splitlines()[0],
            "Request Number,Source System,Request Type,Category,Priority,"
            "Current Status,Scheduled Pickup,Created At",
        )
        self.assertIn("'=DANGEROUS", body)
        self.assertIn('"TR,""SPECIAL"""', body)
        self.assertNotIn("Private Guest", body)
        self.assertNotIn("+63 SECRET", body)

    def test_xlsx_is_real_workbook_filtered_and_formula_safe(self):
        moment = datetime(2026, 9, 20, 4, tzinfo=datetime_timezone.utc)
        self.create_request("INCLUDED", created_at=moment)
        excluded = self.create_request(
            "EXCLUDED",
            created_at=moment,
            source_system=TransportRequest.SourceSystem.SUPPLY_CHAIN_MANAGEMENT_SYSTEM,
        )
        TransportRequest.objects.filter(pk=excluded.pk).update(request_number="=EXCLUDED")
        malicious = self.create_request("FORMULA", created_at=moment)
        TransportRequest.objects.filter(pk=malicious.pk).update(request_number="=DANGEROUS")
        special = self.create_request("SPECIAL", created_at=moment)
        TransportRequest.objects.filter(pk=special.pk).update(request_number="TR & SPECIAL")

        response = self.client.get(
            self.xlsx_endpoint,
            {
                "date_from": "2026-09-20",
                "date_to": "2026-09-20",
                "source": TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        with ZipFile(io.BytesIO(response.content)) as workbook:
            names = set(workbook.namelist())
            sheet = workbook.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("[Content_Types].xml", names)
        self.assertIn("Request Number", sheet)
        self.assertIn("'=DANGEROUS", sheet)
        self.assertIn("TR &amp; SPECIAL", sheet)
        self.assertNotIn("=EXCLUDED", sheet)
        self.assertNotIn("Private Guest", sheet)

    def test_pdf_is_real_filtered_file_and_empty_result_is_safe(self):
        moment = datetime(2026, 9, 20, 4, tzinfo=datetime_timezone.utc)
        self.create_request("PDF", created_at=moment)
        filtered = self.client.get(
            self.pdf_endpoint,
            {"date_from": "2026-09-20", "date_to": "2026-09-20"},
        )
        empty = self.client.get(
            self.pdf_endpoint,
            {"date_from": "2026-09-21", "date_to": "2026-09-21"},
        )

        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered["Content-Type"], "application/pdf")
        self.assertTrue(filtered.content.startswith(b"%PDF-1.4"))
        self.assertIn(b"Request Number", filtered.content)
        self.assertIn(b"Hotel management system", filtered.content)
        self.assertNotIn(b"Private Guest", filtered.content)
        self.assertEqual(empty.status_code, 200)
        self.assertTrue(empty.content.startswith(b"%PDF-1.4"))
        self.assertIn(b"Request Number", empty.content)
