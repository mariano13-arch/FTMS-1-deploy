from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.exceptions import ValidationError as SerializerValidationError

from fleet.models import Vehicle
from fleet.serializers import VehicleSerializer


class VehicleFuelDomainTests(TestCase):
    def vehicle(self, code, *, fuel_type="", fuel_grade=""):
        return Vehicle(
            device_id=code,
            plate_number=code,
            display_name=code,
            fuel_type=fuel_type,
            fuel_grade=fuel_grade,
        )

    def test_existing_liquid_fuel_types_remain_without_fabricated_grade(self):
        for fuel_type in (Vehicle.FuelType.GASOLINE, Vehicle.FuelType.DIESEL):
            with self.subTest(fuel_type=fuel_type):
                vehicle = self.vehicle(f"PRESERVE-{fuel_type}", fuel_type=fuel_type)
                vehicle.full_clean()
                vehicle.save()
                vehicle.refresh_from_db()
                self.assertEqual(vehicle.fuel_type, fuel_type)
                self.assertEqual(vehicle.fuel_grade, "")

    def test_valid_gasoline_grades(self):
        for grade in (
            Vehicle.FuelGrade.UNLEADED_91,
            Vehicle.FuelGrade.PREMIUM_95,
            Vehicle.FuelGrade.PREMIUM_97,
        ):
            with self.subTest(grade=grade):
                self.vehicle("VALID-GAS", fuel_type="GASOLINE", fuel_grade=grade).full_clean()

    def test_valid_diesel_grades(self):
        for grade in (
            Vehicle.FuelGrade.REGULAR_DIESEL,
            Vehicle.FuelGrade.PREMIUM_DIESEL,
        ):
            with self.subTest(grade=grade):
                self.vehicle("VALID-DIESEL", fuel_type="DIESEL", fuel_grade=grade).full_clean()

    def test_mismatched_or_grade_without_type_is_rejected(self):
        invalid = (
            ("GASOLINE", "REGULAR_DIESEL"),
            ("DIESEL", "PREMIUM_95"),
            ("", "UNLEADED_91"),
        )
        for fuel_type, fuel_grade in invalid:
            with self.subTest(fuel_type=fuel_type, fuel_grade=fuel_grade):
                with self.assertRaises(ValidationError):
                    self.vehicle(
                        f"BAD-{fuel_type or 'BLANK'}-{fuel_grade}",
                        fuel_type=fuel_type,
                        fuel_grade=fuel_grade,
                    ).full_clean()

    def test_blank_type_and_grade_are_valid(self):
        self.vehicle("BLANK-FUEL").full_clean()

    def test_removed_fuel_types_are_not_model_or_serializer_choices(self):
        choices = {choice for choice, _label in Vehicle.FuelType.choices}
        self.assertEqual(choices, {"GASOLINE", "DIESEL"})
        for removed in ("HYBRID", "ELECTRIC", "OTHER"):
            with self.subTest(removed=removed):
                with self.assertRaises(ValidationError):
                    self.vehicle(f"REMOVED-{removed}", fuel_type=removed).full_clean()
                serializer = VehicleSerializer(
                    data={
                        "device_id": f"REMOVED-{removed}",
                        "plate_number": f"REMOVED-{removed}",
                        "display_name": removed,
                        "fuel_type": removed,
                    }
                )
                self.assertFalse(serializer.is_valid())
                self.assertIn("fuel_type", serializer.errors)

    def test_serializer_exposes_and_accepts_fuel_grade(self):
        serializer = VehicleSerializer(
            data={
                "device_id": "SERIAL-FUEL",
                "plate_number": "SERIAL-FUEL",
                "display_name": "Serializer fuel",
                "fuel_type": "GASOLINE",
                "fuel_grade": "UNLEADED_91",
            }
        )
        serializer.is_valid(raise_exception=True)
        vehicle = serializer.save()
        self.assertEqual(VehicleSerializer(vehicle).data["fuel_grade"], "UNLEADED_91")

    def test_update_must_explicitly_clear_or_replace_incompatible_grade(self):
        vehicle = self.vehicle(
            "UPDATE-FUEL", fuel_type="GASOLINE", fuel_grade="PREMIUM_95"
        )
        vehicle.save()
        serializer = VehicleSerializer(
            vehicle, data={"fuel_type": "DIESEL"}, partial=True
        )
        with self.assertRaises(SerializerValidationError):
            serializer.is_valid(raise_exception=True)

        serializer = VehicleSerializer(
            vehicle,
            data={"fuel_type": "DIESEL", "fuel_grade": ""},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        self.assertEqual(serializer.save().fuel_grade, "")
