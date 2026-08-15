from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Driver, Vehicle
from transport_requests import consolidation
from transport_requests.models import (
    DispatchAssignment,
    DispatchPlan,
    DispatchPlanEvent,
    DispatchPlanStop,
    TransportRequest,
)


def road_matrix(size):
    durations = [
        [0 if row == column else abs(row - column) * 10 for column in range(size)]
        for row in range(size)
    ]
    distances = [[value * 100 for value in row] for row in durations]
    return {
        "durations_seconds": durations,
        "distances_meters": distances,
        "traffic_delays_seconds": [[0] * size for _ in range(size)],
        "cell_statuses": [["OK"] * size for _ in range(size)],
        "cell_count": size * size,
    }


class ConsolidationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="dispatcher", is_staff=True)
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.DISPATCHER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        today = timezone.localdate()
        self.driver = Driver.objects.create(
            driver_code="DEV-CONS-DRV",
            first_name="Consolidation",
            last_name="Driver",
            license_number="CONS-001",
            license_expiry_date=today + timedelta(days=90),
            medical_certificate_expiry_date=today + timedelta(days=90),
        )
        self.vehicle = Vehicle.objects.create(
            device_id="DEV-CONS-VEH",
            plate_number="CNS-001",
            display_name="Consolidation Truck",
            vehicle_type=Vehicle.VehicleType.SERVICE_TRUCK,
            passenger_capacity=3,
            payload_capacity_kg=Decimal("1000.00"),
        )
        self.first = self.make_request("CONS-001", Decimal("400.00"), 2)
        self.second = self.make_request("CONS-002", Decimal("300.00"), 3)

    def make_request(self, reference, weight, hours):
        return TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.MANUAL_STAFF_ENTRY,
            external_reference=reference,
            request_type=TransportRequest.RequestType.SUPPLIER_PICKUP,
            request_category=TransportRequest.RequestCategory.DELIVERY_LOGISTICS,
            requester_name="Development Operations",
            pickup_name=f"Pickup {reference}",
            pickup_address="Makati",
            pickup_latitude="14.565200",
            pickup_longitude="121.028600",
            destination_name=f"Delivery {reference}",
            destination_address="Pasay",
            destination_latitude="14.508600",
            destination_longitude="121.019800",
            scheduled_pickup_at=timezone.now() + timedelta(hours=hours),
            estimated_duration_minutes=60,
            required_vehicle_type=Vehicle.VehicleType.SERVICE_TRUCK,
            passenger_count=0,
            load_description="Development supplies",
            estimated_weight_kg=weight,
            status=TransportRequest.Status.APPROVED,
            created_by=self.user,
        )

    def matrix(self, *_args, **_kwargs):
        return road_matrix(6)

    @patch("transport_requests.consolidation.matrix.build_point_matrix")
    @patch("transport_requests.consolidation.matrix.eligible_vehicle_origins")
    def test_routing_model_uses_tomtom_costs_precedence_and_capacity(self, origins, matrix_mock):
        origins.return_value = [
            {"vehicle_id": self.vehicle.device_id, "latitude": 14.5, "longitude": 121.0}
        ]
        matrix_mock.side_effect = self.matrix
        result = consolidation.recommendations(self.first.pk)["recommendation"]
        self.assertIsNotNone(result)
        stops = result["route"]["stops"]
        for request_id in (str(self.first.pk), str(self.second.pk)):
            pickup = next(
                item["sequence"]
                for item in stops
                if item["request_id"] == request_id and item["stop_type"] == "PICKUP"
            )
            delivery = next(
                item["sequence"]
                for item in stops
                if item["request_id"] == request_id and item["stop_type"] == "DELIVERY"
            )
            self.assertLess(pickup, delivery)
        self.assertLessEqual(
            Decimal(result["route"]["peak_load_kg"]), self.vehicle.payload_capacity_kg
        )
        self.assertGreater(result["route"]["difference"]["travel_time_seconds"], 0)
        self.assertNotIn("safety_score", result)
        self.assertFalse(DispatchPlan.objects.exists())

    @patch("transport_requests.consolidation.matrix.build_point_matrix")
    @patch("transport_requests.consolidation.matrix.eligible_vehicle_origins")
    def test_explicit_confirmation_persists_one_plan_assignments_stops_and_audit(
        self, origins, matrix_mock
    ):
        origins.return_value = [
            {"vehicle_id": self.vehicle.device_id, "latitude": 14.5, "longitude": 121.0}
        ]
        matrix_mock.side_effect = self.matrix
        suggestion = consolidation.recommendations(self.first.pk)["recommendation"]
        response = self.client.post(
            "/api/v1/transport-requests/dispatch-board/consolidations/confirm/",
            {"recommendation_token": suggestion["recommendation_token"]},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        plan = DispatchPlan.objects.get()
        self.assertEqual(plan.assignments.count(), 2)
        self.assertEqual(DispatchPlanStop.objects.filter(plan=plan).count(), 4)
        self.assertEqual(
            DispatchPlanEvent.objects.get(plan=plan).event_type, "CONSOLIDATION_CONFIRMED"
        )
        self.assertEqual(
            set(plan.assignments.values_list("vehicle_id", flat=True)), {self.vehicle.pk}
        )
        self.assertEqual(
            set(plan.assignments.values_list("driver_id", flat=True)), {self.driver.pk}
        )
        self.assertEqual(
            set(
                TransportRequest.objects.filter(pk__in=[self.first.pk, self.second.pk]).values_list(
                    "assigned_vehicle_id", flat=True
                )
            ),
            {self.vehicle.pk},
        )

    @patch("transport_requests.consolidation.matrix.build_point_matrix")
    @patch("transport_requests.consolidation.matrix.eligible_vehicle_origins")
    def test_prepare_is_atomic_for_all_members_and_creates_no_trip(self, origins, matrix_mock):
        origins.return_value = [
            {"vehicle_id": self.vehicle.device_id, "latitude": 14.5, "longitude": 121.0}
        ]
        matrix_mock.side_effect = self.matrix
        plan = consolidation.confirm(
            consolidation.recommendations(self.first.pk)["recommendation"]["recommendation_token"],
            self.user,
        )
        response = self.client.post(
            f"/api/v1/transport-requests/dispatch-board/consolidations/{plan.pk}/prepare/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            TransportRequest.objects.filter(
                pk__in=[self.first.pk, self.second.pk],
                status=TransportRequest.Status.READY_FOR_DISPATCH,
            ).count(),
            2,
        )
        self.assertFalse(hasattr(plan, "trip"))

    def test_truthful_eligibility_exclusions(self):
        passenger = self.make_request("CONS-PAX", Decimal("20.00"), 4)
        passenger.request_category = TransportRequest.RequestCategory.PASSENGER_TRANSPORT
        passenger.passenger_count = 1
        passenger.estimated_weight_kg = None
        passenger.save(
            update_fields=[
                "request_category",
                "passenger_count",
                "estimated_weight_kg",
                "updated_at",
            ]
        )
        self.assertIn(
            "Passenger transport", consolidation.recommendations(passenger.pk)["exclusions"][0]
        )
        self.second.estimated_weight_kg = None
        self.second.save(update_fields=["estimated_weight_kg", "updated_at"])
        result = consolidation.recommendations(self.first.pk)
        self.assertIsNone(result["recommendation"])

    def test_forged_token_is_rejected_and_existing_assignment_blocks_grouping(self):
        response = self.client.post(
            "/api/v1/transport-requests/dispatch-board/consolidations/confirm/",
            {"recommendation_token": "forged"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        DispatchAssignment.objects.create(
            transport_request=self.second,
            vehicle=self.vehicle,
            driver=self.driver,
            selection_mode=DispatchAssignment.SelectionMode.MANUAL,
            override_reason="Existing confirmed dispatch",
            confirmed_by=self.user,
        )
        self.assertIsNone(consolidation.recommendations(self.first.pk)["recommendation"])
