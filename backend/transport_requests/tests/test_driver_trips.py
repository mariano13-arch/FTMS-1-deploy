from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from fleet.models import Driver, Vehicle
from transport_requests.models import DispatchAssignment, TransportRequest


class DriverTripApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.operator = get_user_model().objects.create_user(
            username="trip-operator", is_staff=True
        )
        self.driver_user = get_user_model().objects.create_user(
            username="assigned-driver", password="Strong-test-password-42!"
        )
        self.driver = Driver.objects.create(
            driver_code="DRV-TRIP-001",
            first_name="Maria",
            last_name="Reyes",
            linked_user=self.driver_user,
        )
        self.other_user = get_user_model().objects.create_user(
            username="other-driver", password="Strong-test-password-42!"
        )
        self.other_driver = Driver.objects.create(
            driver_code="DRV-TRIP-002",
            first_name="Jose",
            last_name="Santos",
            linked_user=self.other_user,
        )
        self.vehicle = Vehicle.objects.create(
            device_id="DRV-TRIP-VEH-001",
            plate_number="ABC-123",
            display_name="Guest Van",
            vehicle_type=Vehicle.VehicleType.VAN,
            passenger_capacity=8,
        )

    def make_request(self, reference, *, status=TransportRequest.Status.APPROVED, hours=2):
        return TransportRequest.objects.create(
            source_system=TransportRequest.SourceSystem.HOTEL_MANAGEMENT_SYSTEM,
            external_reference=reference,
            request_type=TransportRequest.RequestType.GUEST_TRANSFER,
            request_category=TransportRequest.RequestCategory.PASSENGER_TRANSPORT,
            requester_name="Front Desk",
            requester_contact="internal-contact",
            pickup_name="FTMS Hotel",
            pickup_address="Makati City",
            pickup_latitude="14.565200",
            pickup_longitude="121.028600",
            destination_name="Ninoy Aquino International Airport",
            destination_address="Pasay City",
            destination_latitude="14.508600",
            destination_longitude="121.019800",
            scheduled_pickup_at=timezone.now() + timedelta(hours=hours),
            estimated_duration_minutes=60,
            required_vehicle_type=Vehicle.VehicleType.VAN,
            passenger_count=4,
            luggage_count=2,
            handling_instructions="Meet at the main entrance.",
            notes="Staff-only test note",
            status=status,
            assigned_vehicle=self.vehicle if status != TransportRequest.Status.CANCELLED else None,
            created_by=self.operator,
        )

    def assign(self, item, driver=None):
        item.assigned_vehicle = self.vehicle
        item.save(update_fields=["assigned_vehicle", "updated_at"])
        return DispatchAssignment.objects.create(
            transport_request=item,
            vehicle=self.vehicle,
            driver=driver or self.driver,
            selection_mode=DispatchAssignment.SelectionMode.MANUAL,
            override_reason="Controlled test assignment",
            confirmed_by=self.operator,
        )

    def test_unauthenticated_access_is_denied(self):
        item = self.make_request("UNAUTH")
        self.assign(item)

        self.assertEqual(self.client.get("/api/v1/driver-trips/").status_code, 401)
        self.assertEqual(
            self.client.get(f"/api/v1/driver-trips/{item.pk}/").status_code, 401
        )

    def test_list_contains_only_own_active_assignments(self):
        later = self.make_request(
            "OWN-READY", status=TransportRequest.Status.READY_FOR_DISPATCH, hours=4
        )
        earlier = self.make_request("OWN-APPROVED", hours=2)
        other = self.make_request("OTHER", hours=1)
        cancelled = self.make_request(
            "CANCELLED", status=TransportRequest.Status.CANCELLED, hours=3
        )
        self.make_request("UNASSIGNED", hours=5)
        for item, driver in (
            (later, self.driver),
            (earlier, self.driver),
            (other, self.other_driver),
            (cancelled, self.driver),
        ):
            self.assign(item, driver)
        self.client.force_login(self.driver_user)

        response = self.client.get("/api/v1/driver-trips/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [trip["id"] for trip in response.json()["trips"]],
            [str(earlier.pk), str(later.pk)],
        )

    def test_driver_can_read_own_trip_with_minimal_operational_fields(self):
        item = self.make_request("OWN-DETAIL")
        self.assign(item)
        self.client.force_login(self.driver_user)

        response = self.client.get(f"/api/v1/driver-trips/{item.pk}/")

        self.assertEqual(response.status_code, 200)
        trip = response.json()["trip"]
        self.assertEqual(
            set(trip),
            {
                "id",
                "request_number",
                "request_type",
                "request_type_label",
                "request_category",
                "request_category_label",
                "priority",
                "priority_label",
                "status",
                "status_label",
                "scheduled_pickup_at",
                "estimated_duration_minutes",
                "passenger_count",
                "luggage_count",
                "pickup",
                "destination",
                "vehicle",
                "handling_instructions",
                "load_description",
                "load_quantity",
                "estimated_weight_kg",
                "temperature_requirement",
                "execution",
            },
        )
        self.assertEqual(trip["id"], str(item.pk))
        self.assertEqual(trip["pickup"], {"name": "FTMS Hotel", "address": "Makati City"})
        self.assertEqual(trip["destination"]["address"], "Pasay City")
        self.assertEqual(trip["vehicle"]["plate_number"], "ABC-123")
        self.assertEqual(trip["passenger_count"], 4)
        self.assertEqual(trip["handling_instructions"], "Meet at the main entrance.")
        self.assertEqual(
            trip["execution"],
            {
                "assignment_id": DispatchAssignment.objects.get(
                    transport_request=item
                ).pk,
                "trip_id": str(item.pk),
                "status": "ASSIGNED",
                "status_label": "Assigned",
                "allowed_actions": ["START_TOWARD_PICKUP"],
                "execution_started_at": None,
                "pickup_arrived_at": None,
                "pickup_departed_at": None,
                "destination_arrived_at": None,
                "completed_at": None,
            },
        )
        for private_field in (
            "requester_name",
            "requester_contact",
            "notes",
            "created_by",
            "approved_by",
            "events",
            "execution_events",
        ):
            self.assertNotIn(private_field, trip)
        self.assertNotIn("device_id", trip["vehicle"])

    def test_driver_cannot_read_another_drivers_trip(self):
        item = self.make_request("OTHER-DETAIL")
        self.assign(item, self.other_driver)
        self.client.force_login(self.driver_user)

        self.assertEqual(
            self.client.get(f"/api/v1/driver-trips/{item.pk}/").status_code, 404
        )

    def test_empty_assignment_list_is_clean(self):
        self.client.force_login(self.driver_user)

        response = self.client.get("/api/v1/driver-trips/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"trips": []})
