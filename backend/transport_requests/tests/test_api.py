# ruff: noqa: E501
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Vehicle
from transport_requests.models import (
    TransportRequest,
    TransportRequestEvent,
    generate_request_number,
)
from transport_requests.services import lock_relevant_vehicles


class TransportRequestApiTests(TestCase):
    password = "A-strong-test-password-42!"

    def setUp(self):
        self.client = APIClient()
        self.manager = self.make_user("manager", StaffProfile.Role.FLEET_MANAGER)
        self.dispatcher = self.make_user("dispatcher", StaffProfile.Role.DISPATCHER)
        self.vehicle = Vehicle.objects.create(
            device_id="VAN-01", plate_number="VAN-01", display_name="Guest Van",
            passenger_capacity=6,
        )

    def make_user(self, username, role=None, superuser=False):
        user = get_user_model().objects.create_user(
            username=username, password=self.password, is_staff=True, is_superuser=superuser
        )
        if role:
            StaffProfile.objects.create(user=user, role=role)
        return user

    def login(self, user):
        self.client.force_authenticate(user)

    def payload(self, external="HMS-100"):
        return {
            "source_system": "HOTEL_MANAGEMENT_SYSTEM", "external_reference": external,
            "request_type": "AIRPORT_PICKUP", "requester_name": " Front Desk ",
            "requester_contact": "+63 900 000 0000", "pickup_name": "NAIA Terminal 3",
            "pickup_address": "Pasay City", "pickup_latitude": "14.508600",
            "pickup_longitude": "121.019800", "destination_name": "Oxford Suites Makati",
            "destination_address": "Makati City", "destination_latitude": "14.565200",
            "destination_longitude": "121.028600",
            "scheduled_pickup_at": (timezone.now() + timedelta(hours=2)).isoformat(),
            "passenger_count": 4, "luggage_count": 2, "priority": "HIGH", "notes": " Guest ",
        }

    def create_request(self, user=None, external="HMS-100"):
        self.login(user or self.manager)
        response = self.client.post("/api/v1/transport-requests/", self.payload(external), format="json")
        self.assertEqual(response.status_code, 201)
        return response

    def test_create_normalizes_and_audits_and_duplicate_is_conflict(self):
        response = self.create_request()
        self.assertRegex(response.json()["request_number"], r"^TR-\d{8}-[A-F0-9]{6}$")
        self.assertEqual(response.json()["requester_name"], "Front Desk")
        self.assertEqual(response.json()["status"], "FOR_APPROVAL")
        self.assertEqual(TransportRequestEvent.objects.get().event_type, "CREATED")
        duplicate = self.client.post("/api/v1/transport-requests/", self.payload(), format="json")
        self.assertEqual(duplicate.status_code, 409)

    @override_settings(TIME_ZONE="Asia/Manila")
    def test_request_number_uses_manila_local_date_after_midnight(self):
        shortly_after_midnight = datetime(
            2026, 8, 6, 16, 15, tzinfo=datetime_timezone.utc
        )
        with timezone.override("Asia/Manila"), patch(
            "django.utils.timezone.now", return_value=shortly_after_midnight
        ):
            request_number = generate_request_number()
        self.assertRegex(request_number, r"^TR-20260807-[A-F0-9]{6}$")

    def test_manager_transitions_and_dispatcher_permissions(self):
        request_id = self.create_request().json()["id"]
        self.login(self.dispatcher)
        self.assertEqual(self.client.post(f"/api/v1/transport-requests/{request_id}/approve/", {}, format="json").status_code, 403)
        self.login(self.manager)
        self.assertEqual(self.client.post(f"/api/v1/transport-requests/{request_id}/approve/", {}, format="json").status_code, 200)
        invalid = self.client.post(f"/api/v1/transport-requests/{request_id}/reject/", {}, format="json")
        self.assertEqual(invalid.status_code, 400)
        self.login(self.dispatcher)
        assigned = self.client.post(f"/api/v1/transport-requests/{request_id}/assign-vehicle/", {"vehicle_device_id": self.vehicle.device_id}, format="json")
        self.assertEqual(assigned.status_code, 200)
        ready = self.client.post(f"/api/v1/transport-requests/{request_id}/prepare-dispatch/", {}, format="json")
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()["status"], "READY_FOR_DISPATCH")
        self.assertEqual(TransportRequestEvent.objects.filter(request_id=request_id).count(), 4)

    def test_assignment_rejects_inactive_and_undersized_vehicles(self):
        request_id = self.create_request().json()["id"]
        self.client.post(f"/api/v1/transport-requests/{request_id}/approve/", {}, format="json")
        small = Vehicle.objects.create(
            device_id="CAR-01", plate_number="CAR-01", display_name="Small Car",
            passenger_capacity=2,
        )
        response = self.client.post(f"/api/v1/transport-requests/{request_id}/assign-vehicle/", {"vehicle_device_id": small.device_id}, format="json")
        self.assertEqual(response.status_code, 400)
        self.vehicle.is_active = False
        self.vehicle.save(update_fields=["is_active", "updated_at"])
        response = self.client.post(f"/api/v1/transport-requests/{request_id}/assign-vehicle/", {"vehicle_device_id": self.vehicle.device_id}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_filters_summary_and_edit_audit(self):
        request_id = self.create_request().json()["id"]
        self.assertEqual(self.client.patch(f"/api/v1/transport-requests/{request_id}/", {"notes": "Updated"}, format="json").status_code, 200)
        summary = self.client.get("/api/v1/transport-requests/summary/").json()
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["for_approval"], 1)
        self.assertEqual(summary["high_priority"], 1)
        filtered = self.client.get("/api/v1/transport-requests/?status=FOR_APPROVAL&search=NAIA")
        self.assertEqual(filtered.json()["count"], 1)
        self.assertEqual(TransportRequestEvent.objects.filter(request_id=request_id).count(), 2)

    def test_more_details_requires_manager_and_note_then_dispatcher_edits_and_resubmits(self):
        request_id = self.create_request().json()["id"]
        url = f"/api/v1/transport-requests/{request_id}/request-more-details/"
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 400)
        self.login(self.dispatcher)
        self.assertEqual(
            self.client.post(url, {"note": "Missing room number"}, format="json").status_code,
            403,
        )
        self.login(self.manager)
        response = self.client.post(
            url, {"note": " Please confirm the guest room number. "}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "NEEDS_MORE_DETAILS")
        event = TransportRequestEvent.objects.get(event_type="REQUESTED_MORE_DETAILS")
        self.assertEqual(event.note, "Please confirm the guest room number.")
        self.login(self.dispatcher)
        edited = self.client.patch(
            f"/api/v1/transport-requests/{request_id}/",
            {"notes": "Room 712 confirmed"}, format="json",
        )
        self.assertEqual(edited.status_code, 200)
        resubmitted = self.client.post(
            f"/api/v1/transport-requests/{request_id}/resubmit/", {}, format="json"
        )
        self.assertEqual(resubmitted.status_code, 200)
        self.assertEqual(resubmitted.json()["status"], "FOR_APPROVAL")
        self.assertTrue(
            TransportRequestEvent.objects.filter(event_type="RESUBMITTED").exists()
        )

    def test_reject_cancel_require_notes_and_approved_records_cannot_be_edited(self):
        reject_id = self.create_request(external="REJECT-1").json()["id"]
        reject_url = f"/api/v1/transport-requests/{reject_id}/reject/"
        self.assertEqual(self.client.post(reject_url, {}, format="json").status_code, 400)
        self.assertEqual(
            self.client.post(reject_url, {"note": "Duplicate guest request"}, format="json").status_code,
            200,
        )
        cancel_id = self.create_request(external="CANCEL-1").json()["id"]
        cancel_url = f"/api/v1/transport-requests/{cancel_id}/cancel/"
        self.assertEqual(self.client.post(cancel_url, {}, format="json").status_code, 400)
        self.assertEqual(
            self.client.post(cancel_url, {"note": "Guest cancelled"}, format="json").status_code,
            200,
        )
        approved_id = self.create_request(external="APPROVED-EDIT").json()["id"]
        self.client.post(
            f"/api/v1/transport-requests/{approved_id}/approve/", {}, format="json"
        )
        edited_events = TransportRequestEvent.objects.filter(
            request_id=approved_id, event_type="EDITED"
        ).count()
        stale = self.client.patch(
            f"/api/v1/transport-requests/{approved_id}/",
            {"notes": "Silent operational edit"}, format="json",
        )
        self.assertEqual(stale.status_code, 409)
        self.assertIn("changed workflow status", stale.json()["status"])
        self.assertEqual(TransportRequest.objects.get(pk=approved_id).notes, "Guest")
        self.assertEqual(
            TransportRequestEvent.objects.filter(
                request_id=approved_id, event_type="EDITED"
            ).count(),
            edited_events,
        )

    def test_super_admin_cannot_bypass_stale_edit_after_transition(self):
        request_id = self.create_request(external="STALE-SUPER").json()["id"]
        self.client.post(
            f"/api/v1/transport-requests/{request_id}/approve/", {}, format="json"
        )
        super_admin = self.make_user("super-admin", superuser=True)
        self.login(super_admin)
        response = self.client.patch(
            f"/api/v1/transport-requests/{request_id}/",
            {"requester_name": "Stale overwrite"}, format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            TransportRequest.objects.get(pk=request_id).requester_name,
            "Front Desk",
        )
        self.assertFalse(
            TransportRequestEvent.objects.filter(
                request_id=request_id, event_type="EDITED"
            ).exists()
        )

    @override_settings(TIME_ZONE="Asia/Manila")
    def test_summary_and_calendar_use_manila_operational_boundaries(self):
        manila_today = datetime(2026, 8, 7, 0, 30, tzinfo=datetime_timezone(timedelta(hours=8)))
        payload = self.payload("MANILA-TODAY")
        payload["scheduled_pickup_at"] = manila_today.isoformat()
        self.login(self.manager)
        self.assertEqual(
            self.client.post(
                "/api/v1/transport-requests/", payload, format="json"
            ).status_code,
            201,
        )
        previous_day = self.payload("MANILA-PREVIOUS")
        previous_day["scheduled_pickup_at"] = "2026-08-06T15:59:00Z"
        self.assertEqual(
            self.client.post(
                "/api/v1/transport-requests/", previous_day, format="json"
            ).status_code,
            201,
        )
        with timezone.override("Asia/Manila"), patch(
            "django.utils.timezone.now",
            return_value=datetime(2026, 8, 6, 16, 30, tzinfo=datetime_timezone.utc),
        ):
            summary = self.client.get("/api/v1/transport-requests/summary/").json()
            calendar = self.client.get(
                "/api/v1/transport-requests/calendar/?start=2026-08-07&end=2026-08-07"
            )
        self.assertEqual(summary["scheduled_today"], 1)
        self.assertEqual(calendar.status_code, 200)
        self.assertEqual(calendar.json()["timezone"], "Asia/Manila")
        self.assertEqual(
            [item["calendar_date"] for item in calendar.json()["results"]],
            ["2026-08-07"],
        )
        planning_end = datetime.fromisoformat(
            calendar.json()["results"][0]["planning_end_at"].replace("Z", "+00:00")
        )
        self.assertIsNotNone(planning_end.tzinfo)

    def test_relevant_vehicle_lock_order_is_deterministic(self):
        later = Vehicle.objects.create(
            device_id="VAN-02", plate_number="VAN-02", display_name="Second Van"
        )
        locked = lock_relevant_vehicles(later.pk, self.vehicle.pk, later.pk, None)
        self.assertEqual(list(locked), sorted([self.vehicle.pk, later.pk]))

    def test_dispatch_queue_summary_assignment_filter_and_serializer_shapes(self):
        request_id = self.create_request().json()["id"]
        self.client.post(
            f"/api/v1/transport-requests/{request_id}/approve/", {}, format="json"
        )
        dispatch = self.client.get("/api/v1/transport-requests/?status=APPROVED")
        self.assertEqual(dispatch.json()["count"], 1)
        self.assertNotIn("events", dispatch.json()["results"][0])
        self.assertIn("latest_event_type", dispatch.json()["results"][0])
        combined = self.client.get(
            "/api/v1/transport-requests/?status=FOR_APPROVAL,NEEDS_MORE_DETAILS"
        )
        self.assertEqual(combined.status_code, 200)
        self.assertEqual(
            self.client.get(
                "/api/v1/transport-requests/?assignment=unassigned"
            ).json()["count"],
            1,
        )
        summary = self.client.get("/api/v1/transport-requests/summary/").json()
        self.assertEqual(summary["dispatch_queue"], 1)
        self.assertEqual(summary["approved_unassigned"], 1)
        detail = self.client.get(f"/api/v1/transport-requests/{request_id}/")
        self.assertIn("events", detail.json())
        self.client.post(
            f"/api/v1/transport-requests/{request_id}/assign-vehicle/",
            {"vehicle_device_id": self.vehicle.device_id}, format="json",
        )
        unassigned_id = self.create_request(external="QUEUE-UNASSIGNED").json()["id"]
        self.client.post(
            f"/api/v1/transport-requests/{unassigned_id}/approve/", {}, format="json"
        )
        ordered_dispatch = self.client.get(
            "/api/v1/transport-requests/?status=APPROVED"
        ).json()["results"]
        self.assertEqual(ordered_dispatch[0]["id"], unassigned_id)
        self.assertEqual(
            self.client.get(
                "/api/v1/transport-requests/?status=APPROVED&assignment=assigned"
            ).json()["count"],
            1,
        )
        for query in ("status=APPROVED,NOPE", "assignment=maybe"):
            self.assertEqual(
                self.client.get(f"/api/v1/transport-requests/?{query}").status_code,
                400,
            )

    def test_vehicle_type_overlap_and_prepare_revalidation(self):
        first_id = self.create_request(external="ALLOC-1").json()["id"]
        self.client.patch(
            f"/api/v1/transport-requests/{first_id}/",
            {"required_vehicle_type": "VAN", "estimated_duration_minutes": 120},
            format="json",
        )
        self.client.post(
            f"/api/v1/transport-requests/{first_id}/approve/", {}, format="json"
        )
        wrong_type = Vehicle.objects.create(
            device_id="SUV-01", plate_number="SUV-01", display_name="SUV",
            vehicle_type="SUV", passenger_capacity=6,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/transport-requests/{first_id}/assign-vehicle/",
                {"vehicle_device_id": wrong_type.device_id}, format="json",
            ).status_code,
            400,
        )
        self.vehicle.vehicle_type = "VAN"
        self.vehicle.save(update_fields=["vehicle_type", "updated_at"])
        self.assertEqual(
            self.client.post(
                f"/api/v1/transport-requests/{first_id}/assign-vehicle/",
                {"vehicle_device_id": self.vehicle.device_id}, format="json",
            ).status_code,
            200,
        )
        second_id = self.create_request(external="ALLOC-2").json()["id"]
        self.client.patch(
            f"/api/v1/transport-requests/{second_id}/",
            {"required_vehicle_type": "VAN", "estimated_duration_minutes": 120},
            format="json",
        )
        self.client.post(
            f"/api/v1/transport-requests/{second_id}/approve/", {}, format="json"
        )
        conflict = self.client.post(
            f"/api/v1/transport-requests/{second_id}/assign-vehicle/",
            {"vehicle_device_id": self.vehicle.device_id}, format="json",
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertIn("already allocated", conflict.json()["vehicle"])
        self.vehicle.is_active = False
        self.vehicle.save(update_fields=["is_active", "updated_at"])
        prepare = self.client.post(
            f"/api/v1/transport-requests/{first_id}/prepare-dispatch/", {}, format="json"
        )
        self.assertEqual(prepare.status_code, 400)

    def test_calendar_validation_conflicts_and_ready_constraint(self):
        first_id = self.create_request(external="CAL-1").json()["id"]
        self.client.post(
            f"/api/v1/transport-requests/{first_id}/approve/", {}, format="json"
        )
        self.client.post(
            f"/api/v1/transport-requests/{first_id}/assign-vehicle/",
            {"vehicle_device_id": self.vehicle.device_id}, format="json",
        )
        second_id = self.create_request(external="CAL-2").json()["id"]
        self.client.post(
            f"/api/v1/transport-requests/{second_id}/approve/", {}, format="json"
        )
        TransportRequest.objects.filter(pk=second_id).update(
            assigned_vehicle=self.vehicle
        )
        day = timezone.localdate(
            TransportRequest.objects.get(pk=first_id).scheduled_pickup_at
        ).isoformat()
        calendar = self.client.get(
            f"/api/v1/transport-requests/calendar/?start={day}&end={day}"
        )
        self.assertEqual(calendar.status_code, 200)
        self.assertEqual(calendar.json()["timezone"], str(timezone.get_current_timezone()))
        self.assertEqual(calendar.json()["results"][0]["calendar_date"], day)
        self.assertTrue(all(item["vehicle_conflict"] for item in calendar.json()["results"]))
        self.assertTrue(calendar.json()["results"][0]["conflicting_requests"])
        for query in (
            "start=nope&end=nope", "start=2026-08-02&end=2026-08-01",
            "start=2026-01-01&end=2026-03-01",
        ):
            self.assertEqual(
                self.client.get(
                    f"/api/v1/transport-requests/calendar/?{query}"
                ).status_code,
                400,
            )
        third_id = self.create_request(external="INVALID-READY").json()["id"]
        with self.assertRaises(IntegrityError), transaction.atomic():
            TransportRequest.objects.filter(pk=third_id).update(
                status=TransportRequest.Status.READY_FOR_DISPATCH
            )

    def test_seed_is_idempotent_and_never_leaves_invalid_ready_request(self):
        output = StringIO()
        errors = StringIO()
        call_command("seed_transport_requests", stdout=output, stderr=errors)
        count = TransportRequest.objects.filter(
            external_reference__startswith="SEED-"
        ).count()
        event_count = TransportRequestEvent.objects.filter(
            request__external_reference__startswith="SEED-"
        ).count()
        call_command("seed_transport_requests", stdout=StringIO(), stderr=StringIO())
        self.assertEqual(
            TransportRequest.objects.filter(
                external_reference__startswith="SEED-"
            ).count(),
            count,
        )
        self.assertEqual(
            TransportRequestEvent.objects.filter(
                request__external_reference__startswith="SEED-"
            ).count(),
            event_count,
        )
        self.assertFalse(
            TransportRequest.objects.filter(
                status=TransportRequest.Status.READY_FOR_DISPATCH,
                assigned_vehicle__isnull=True,
            ).exists()
        )
