from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from fleet.models import Vehicle, VehicleInspection


class VehicleInspectionTests(TestCase):
    password = "A-strong-test-password-42!"

    def setUp(self):
        self.vehicle = Vehicle.objects.create(
            device_id="TEST-001", plate_number="TEST-001", display_name="Test Van"
        )
        self.other_vehicle = Vehicle.objects.create(
            device_id="TEST-002", plate_number="TEST-002", display_name="Other Van"
        )

    def user(self, role=None, superuser=False):
        user = get_user_model().objects.create_user(
            username=f"user-{get_user_model().objects.count()}",
            password=self.password,
            is_staff=True,
            is_superuser=superuser,
        )
        if role:
            StaffProfile.objects.create(user=user, role=role)
        return user

    def client_for(self, user):
        client = APIClient()
        self.assertTrue(client.login(username=user.username, password=self.password))
        return client

    def payload(self, **overrides):
        return {
            "inspection_date": "2026-08-12",
            "inspection_type": "PRE_TRIP",
            "result": "PASSED",
            "odometer_km": 12500,
            "fuel_level_percent": 75,
            "exterior_condition": "OK",
            "interior_condition": "OK",
            "tires_condition": "OK",
            "lights_condition": "OK",
            "brakes_condition": "OK",
            "fluids_condition": "OK",
            "safety_equipment_condition": "OK",
            "notes": " Checked before service. ",
            "issues_found": "",
            **overrides,
        }

    def create_inspection(self, user=None, vehicle=None, **overrides):
        return VehicleInspection.objects.create(
            vehicle=vehicle or self.vehicle,
            inspected_by=user or self.user(StaffProfile.Role.FLEET_MANAGER),
            inspection_date=overrides.pop("inspection_date", date(2026, 8, 12)),
            inspection_type=overrides.pop("inspection_type", "PRE_TRIP"),
            result=overrides.pop("result", "PASSED"),
            exterior_condition=overrides.pop("exterior_condition", "OK"),
            interior_condition=overrides.pop("interior_condition", "OK"),
            tires_condition=overrides.pop("tires_condition", "OK"),
            lights_condition=overrides.pop("lights_condition", "OK"),
            brakes_condition=overrides.pop("brakes_condition", "OK"),
            fluids_condition=overrides.pop("fluids_condition", "OK"),
            safety_equipment_condition=overrides.pop(
                "safety_equipment_condition", "OK"
            ),
            **overrides,
        )

    def test_model_relationship_enums_and_numeric_validation(self):
        manager = self.user(StaffProfile.Role.FLEET_MANAGER)
        inspection = self.create_inspection(manager, odometer_km=0, fuel_level_percent=0)
        self.assertEqual(self.vehicle.inspections.get(), inspection)
        for field, value in (
            ("result", "UNKNOWN"),
            ("inspection_type", "UNKNOWN"),
            ("exterior_condition", "UNKNOWN"),
            ("odometer_km", -1),
            ("fuel_level_percent", 101),
        ):
            candidate = self.create_inspection(manager)
            setattr(candidate, field, value)
            with self.subTest(field=field), self.assertRaises(ValidationError):
                candidate.full_clean()

    def test_anonymous_and_dispatcher_permissions(self):
        url = "/api/v1/vehicles/TEST-001/inspections/"
        self.assertEqual(APIClient().get(url).status_code, 401)
        dispatcher = self.client_for(self.user(StaffProfile.Role.DISPATCHER))
        self.assertEqual(dispatcher.get(url).status_code, 200)
        self.assertEqual(dispatcher.post(url, self.payload(), format="json").status_code, 403)

    def test_manager_and_superadmin_create_with_server_owned_inspector(self):
        url = "/api/v1/vehicles/TEST-001/inspections/"
        for user in (
            self.user(StaffProfile.Role.FLEET_MANAGER),
            self.user(superuser=True),
        ):
            client = self.client_for(user)
            response = client.post(url, self.payload(), format="json")
            self.assertEqual(response.status_code, 201)
            inspection = VehicleInspection.objects.get(pk=response.json()["id"])
            self.assertEqual(inspection.inspected_by, user)
            self.assertEqual(inspection.notes, "Checked before service.")
        rejected = self.client_for(self.user(superuser=True)).post(
            url, self.payload(inspected_by=999), format="json"
        )
        self.assertEqual(rejected.status_code, 400)

    def test_validation_unknown_fields_and_invalid_vehicle(self):
        client = self.client_for(self.user(StaffProfile.Role.FLEET_MANAGER))
        url = "/api/v1/vehicles/TEST-001/inspections/"
        for payload in (
            self.payload(odometer_km=-1),
            self.payload(fuel_level_percent=-1),
            self.payload(fuel_level_percent=101),
            self.payload(result="UNKNOWN"),
            self.payload(unknown=True),
            self.payload(vehicle=self.other_vehicle.pk),
        ):
            self.assertEqual(client.post(url, payload, format="json").status_code, 400)
        self.assertEqual(
            client.post(
                "/api/v1/vehicles/UNKNOWN/inspections/",
                self.payload(),
                format="json",
            ).status_code,
            404,
        )

    def test_list_is_newest_first_paginated_and_vehicle_isolated(self):
        manager = self.user(StaffProfile.Role.FLEET_MANAGER)
        for offset in range(11):
            self.create_inspection(
                manager, inspection_date=date(2026, 8, 1) + timedelta(days=offset)
            )
        self.create_inspection(manager, vehicle=self.other_vehicle)
        client = self.client_for(self.user(StaffProfile.Role.DISPATCHER))
        response = client.get("/api/v1/vehicles/TEST-001/inspections/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 11)
        self.assertEqual(len(response.json()["results"]), 10)
        self.assertEqual(response.json()["results"][0]["inspection_date"], "2026-08-11")
        self.assertIsNotNone(response.json()["next"])

    def test_detail_vehicle_isolation_update_and_delete_policy(self):
        manager = self.user(StaffProfile.Role.FLEET_MANAGER)
        inspection = self.create_inspection(manager, issues_found="Wiper blade worn")
        client = self.client_for(manager)
        url = f"/api/v1/vehicles/TEST-001/inspections/{inspection.pk}/"
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["issues_found"], "Wiper blade worn")
        self.assertEqual(
            client.patch(
                url, {"result": "NEEDS_ATTENTION"}, format="json"
            ).status_code,
            200,
        )
        self.assertEqual(VehicleInspection.objects.get().result, "NEEDS_ATTENTION")
        self.assertEqual(client.delete(url).status_code, 405)
        self.assertEqual(
            client.get(
                f"/api/v1/vehicles/TEST-002/inspections/{inspection.pk}/"
            ).status_code,
            404,
        )

    def test_dispatcher_cannot_update_inspection(self):
        inspection = self.create_inspection()
        client = self.client_for(self.user(StaffProfile.Role.DISPATCHER))
        self.assertEqual(
            client.patch(
                f"/api/v1/vehicles/TEST-001/inspections/{inspection.pk}/",
                {"result": "FAILED"},
                format="json",
            ).status_code,
            403,
        )
