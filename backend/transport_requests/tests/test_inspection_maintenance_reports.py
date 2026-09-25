from datetime import datetime
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Vehicle, VehicleInspection, VehicleMaintenanceRecord


class InspectionMaintenanceReportTests(TestCase):
    endpoint = "/api/v1/reports/inspection-maintenance/"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="inspection-reporter",
            is_staff=True,
            first_name="=Fleet",
            last_name="Manager",
        )
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.FLEET_MANAGER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.vehicle = Vehicle.objects.create(
            device_id="INSPECT-1", plate_number="INS-1", display_name="=Inspection Van"
        )
        self.other_vehicle = Vehicle.objects.create(
            device_id="INSPECT-2", plate_number="INS-2", display_name="Other Van"
        )

    def inspection(self, suffix, **values):
        defaults = {
            "vehicle": self.vehicle,
            "inspection_date": "2026-09-20",
            "inspection_type": VehicleInspection.InspectionType.PRE_TRIP,
            "result": VehicleInspection.Result.PASSED,
            "inspected_by": self.user,
            **{
                field: VehicleInspection.Condition.OK
                for field in VehicleInspection.CHECKLIST_FIELDS
            },
            "issues_found": f"issue {suffix}",
            "notes": f"note {suffix}",
        }
        defaults.update(values)
        return VehicleInspection.objects.create(**defaults)

    def maintenance(self, suffix, *, created_at="2026-09-20T04:00:00+00:00", **values):
        defaults = {
            "vehicle": self.vehicle,
            "source": VehicleMaintenanceRecord.Source.MANUAL,
            "status": VehicleMaintenanceRecord.Status.OPEN,
            "title": f"Maintenance {suffix}",
            "created_by": self.user,
        }
        defaults.update(values)
        record = VehicleMaintenanceRecord.objects.create(**defaults)
        VehicleMaintenanceRecord.objects.filter(pk=record.pk).update(created_at=created_at)
        record.refresh_from_db()
        return record

    def get(self, **params):
        return self.client.get(
            self.endpoint,
            {"date_from": "2026-09-20", "date_to": "2026-09-20", **params},
        )

    def test_kpis_checklist_breakdowns_and_detail_semantics(self):
        passed = self.inspection("passed")
        attention = self.inspection(
            "attention",
            result=VehicleInspection.Result.NEEDS_ATTENTION,
            brakes_condition=VehicleInspection.Condition.NEEDS_ATTENTION,
            lights_condition=VehicleInspection.Condition.NOT_CHECKED,
        )
        self.inspection("failed", result=VehicleInspection.Result.FAILED)
        linked = self.maintenance(
            "linked",
            source=VehicleMaintenanceRecord.Source.INSPECTION,
            inspection=attention,
            title="=Formula title",
        )
        self.maintenance("progress", status=VehicleMaintenanceRecord.Status.IN_PROGRESS)
        self.maintenance(
            "completed",
            status=VehicleMaintenanceRecord.Status.COMPLETED,
            completed_at=datetime(2026, 9, 20, 8, tzinfo=dt_timezone.utc),
        )
        self.maintenance("outside", created_at="2026-09-18T04:00:00+00:00")

        data = self.get().json()
        self.assertEqual(
            data["summary"],
            {
                "inspections": 3,
                "passed": 1,
                "needs_attention": 1,
                "failed": 1,
                "active_maintenance": 3,
                "completed_maintenance": 1,
            },
        )
        attention_counts = {
            row["value"]: row["count"] for row in data["breakdowns"]["checklist_attention"]
        }
        self.assertEqual(attention_counts["brakes_condition"], 1)
        self.assertEqual(attention_counts["lights_condition"], 0)
        row = next(row for row in data["inspections"]["results"] if row["id"] == attention.pk)
        self.assertEqual(row["exception_count"], 2)
        self.assertEqual(row["related_maintenance"][0]["id"], linked.pk)
        self.assertEqual(row["vehicle"]["name"], "=Inspection Van")
        self.assertTrue(any(row["id"] == passed.pk for row in data["inspections"]["results"]))

    def test_filters_and_independent_pagination(self):
        for index in range(16):
            self.inspection(str(index))
            self.maintenance(str(index))
        self.inspection(
            "other",
            vehicle=self.other_vehicle,
            inspection_type=VehicleInspection.InspectionType.PERIODIC,
            result=VehicleInspection.Result.FAILED,
        )
        self.maintenance(
            "other",
            vehicle=self.other_vehicle,
            status=VehicleMaintenanceRecord.Status.CANCELLED,
        )

        data = self.get(inspection_page=2, maintenance_page=1).json()
        self.assertEqual(data["inspections"]["page"], 2)
        self.assertEqual(len(data["inspections"]["results"]), 2)
        self.assertEqual(data["maintenance"]["page"], 1)
        self.assertEqual(len(data["maintenance"]["results"]), 15)

        filtered = self.get(
            inspection_vehicle=self.other_vehicle.pk,
            inspection_type="PERIODIC",
            inspection_result="FAILED",
            inspection_search="INSPECT-2",
            maintenance_vehicle=self.other_vehicle.pk,
            maintenance_status="CANCELLED",
            maintenance_source="MANUAL",
        ).json()
        self.assertEqual(filtered["inspections"]["count"], 1)
        self.assertEqual(filtered["maintenance"]["count"], 1)

    def test_csv_is_complete_filtered_and_formula_safe(self):
        inspection = self.inspection(
            "csv", issues_found="=unsafe issue", notes="+unsafe note"
        )
        self.maintenance("csv", title="@unsafe title", notes="-unsafe note")
        for index in range(16):
            self.inspection(f"extra-{index}")

        params = {
            "date_from": "2026-09-20",
            "date_to": "2026-09-20",
            "inspection_vehicle": self.vehicle.pk,
            "inspection_result": "PASSED",
            "inspection_page": 2,
        }
        response = self.client.get(
            "/api/v1/reports/inspection-maintenance/inspections/csv/", params
        )
        body = b"".join(response.streaming_content).decode()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(body.splitlines()), 18)
        self.assertIn("'=Inspection Van", body)
        self.assertIn("'=Fleet Manager", body)
        self.assertIn("'=unsafe issue", body)
        self.assertIn("'+unsafe note", body)
        self.assertIn(str(inspection.inspection_date), body)

        response = self.client.get(
            "/api/v1/reports/inspection-maintenance/maintenance/csv/",
            {"date_from": "2026-09-20", "date_to": "2026-09-20", "maintenance_status": "OPEN"},
        )
        body = b"".join(response.streaming_content).decode()
        self.assertIn("'=Inspection Van", body)
        self.assertIn("'@unsafe title", body)
        self.assertIn("'-unsafe note", body)

    def test_invalid_ranges_unknown_filters_and_non_staff_are_rejected(self):
        self.assertEqual(self.get(date_from="2026-09-21", date_to="2026-09-20").status_code, 400)
        self.assertEqual(self.get(page_size=101).status_code, 400)
        self.assertEqual(self.get(unknown="value").status_code, 400)
        ordinary = get_user_model().objects.create_user(username="ordinary")
        self.client.force_authenticate(ordinary)
        self.assertEqual(self.get().status_code, 403)
