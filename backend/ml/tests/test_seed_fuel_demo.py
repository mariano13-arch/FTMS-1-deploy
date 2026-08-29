from datetime import timedelta
from io import StringIO

from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from fleet.models import Vehicle
from ml.demo_fuel import (
    CONTROLLED_DEMO_INPUTS,
    DEMO_SOURCE_MODE,
    build_demo_inputs,
    run_demo_inference,
)
from ml.fuel import contract
from ml.models import FuelPrediction
from telemetry.models import TelemetryEvent


class FuelDemoSeedCommandTests(TestCase):
    def create_vehicle(
        self,
        device_id="LILYGO-001",
        name="Sprint 1 Demo Vehicle",
        plate_number=None,
    ):
        return Vehicle.objects.create(
            device_id=device_id,
            plate_number=plate_number or (
                "DEMO-001" if device_id == "LILYGO-001" else device_id
            ),
            display_name=name,
        )

    def create_telemetry(self, vehicle, *, suffix, speed, rpm, recorded_at):
        return TelemetryEvent.objects.create(
            schema_version="1.0",
            event_id=f"fuel-demo-{suffix}",
            sequence_number=int(suffix),
            vehicle=vehicle,
            recorded_at=recorded_at,
            location=Point(121.02, 14.56, srid=4326),
            gnss_speed_kph=speed,
            rpm=rpm,
            driving_event=TelemetryEvent.DrivingEvent.NORMAL,
        )

    @override_settings(DEBUG=False)
    def test_command_refuses_non_development_execution(self):
        with self.assertRaisesMessage(CommandError, "requires settings.DEBUG=True"):
            call_command("seed_fuel_demo")

    @override_settings(DEBUG=True)
    def test_command_requires_existing_demo_vehicle(self):
        self.create_vehicle("REAL-001", "Real Vehicle")

        with self.assertRaisesMessage(CommandError, "device_id=LILYGO-001"):
            call_command("seed_fuel_demo")

    @override_settings(DEBUG=True)
    def test_command_falls_back_to_demo_plate_number(self):
        demo = self.create_vehicle(
            "LEGACY-DEMO",
            "Sprint 1 Demo Vehicle",
            plate_number="DEMO-001",
        )
        event = self.create_telemetry(
            demo,
            suffix="1",
            speed="35.5",
            rpm=1700,
            recorded_at=timezone.now(),
        )

        call_command("seed_fuel_demo", stdout=StringIO())

        prediction = FuelPrediction.objects.get()
        self.assertEqual(prediction.vehicle, demo)
        self.assertEqual(prediction.input_timestamp, event.recorded_at)
        self.assertEqual(prediction.source_mode, DEMO_SOURCE_MODE)

    @override_settings(DEBUG=True)
    def test_command_prefers_lilygo_device_id_and_validates_display_name(self):
        preferred = self.create_vehicle(
            "LILYGO-001",
            "Sprint 1 Demo Vehicle",
            plate_number="PREFERRED-001",
        )
        fallback = self.create_vehicle(
            "LEGACY-DEMO",
            "Sprint 1 Demo Vehicle",
            plate_number="DEMO-001",
        )
        now = timezone.now()
        self.create_telemetry(
            preferred, suffix="1", speed="20", rpm=1200, recorded_at=now
        )
        self.create_telemetry(
            fallback, suffix="2", speed="40", rpm=1800, recorded_at=now
        )

        call_command("seed_fuel_demo", stdout=StringIO())

        prediction = FuelPrediction.objects.get()
        self.assertEqual(prediction.vehicle, preferred)
        self.assertFalse(FuelPrediction.objects.filter(vehicle=fallback).exists())

        FuelPrediction.objects.all().delete()
        preferred.display_name = "Unrelated Vehicle"
        preferred.save(update_fields=["display_name"])
        with self.assertRaisesMessage(CommandError, "Refusing to seed it"):
            call_command("seed_fuel_demo", stdout=StringIO())

    @override_settings(DEBUG=True)
    def test_seed_uses_real_timestamps_speed_rpm_and_controlled_inputs_idempotently(self):
        demo = self.create_vehicle()
        other = self.create_vehicle("REAL-001", "Real Vehicle")
        now = timezone.now()
        older = self.create_telemetry(
            demo,
            suffix="1",
            speed="21.50",
            rpm=1300,
            recorded_at=now - timedelta(minutes=10),
        )
        newer = self.create_telemetry(
            demo,
            suffix="2",
            speed="48.25",
            rpm=2100,
            recorded_at=now,
        )
        self.create_telemetry(
            demo,
            suffix="3",
            speed="52.00",
            rpm=None,
            recorded_at=now + timedelta(minutes=1),
        )
        other_event = self.create_telemetry(
            other,
            suffix="4",
            speed="70.00",
            rpm=2500,
            recorded_at=now,
        )
        other_prediction = FuelPrediction.objects.create(
            vehicle=other,
            input_timestamp=other_event.recorded_at,
            estimated_fuel_lph=9.9999,
            model_name=contract()["model_name"],
            model_version=contract()["model_version"],
            source_mode="explicit_validated_api",
            validated_inputs=build_demo_inputs(other_event),
        )
        telemetry_snapshot = list(
            TelemetryEvent.objects.order_by("pk").values_list(
                "pk", "recorded_at", "gnss_speed_kph", "rpm"
            )
        )

        output = StringIO()
        call_command("seed_fuel_demo", stdout=output)
        call_command("seed_fuel_demo", stdout=output)

        predictions = list(
            FuelPrediction.objects.filter(vehicle=demo).order_by("input_timestamp")
        )
        self.assertEqual(len(predictions), 2)
        self.assertEqual(
            [item.input_timestamp for item in predictions],
            [older.recorded_at, newer.recorded_at],
        )
        for prediction, event in zip(predictions, (older, newer), strict=True):
            expected_inputs = build_demo_inputs(event)
            expected_result = run_demo_inference(event)
            self.assertEqual(prediction.source_mode, DEMO_SOURCE_MODE)
            self.assertEqual(prediction.validated_inputs, expected_inputs)
            self.assertEqual(
                prediction.validated_inputs["Vehicle_Speed_km_per_h"],
                float(event.gnss_speed_kph),
            )
            self.assertEqual(
                prediction.validated_inputs["Engine_RPM_RPM"], float(event.rpm)
            )
            for feature, value in CONTROLLED_DEMO_INPUTS.items():
                self.assertEqual(prediction.validated_inputs[feature], value)
            self.assertAlmostEqual(
                float(prediction.estimated_fuel_lph),
                expected_result["estimated_fuel_lph"],
                places=4,
            )
        self.assertEqual(FuelPrediction.objects.get(pk=other_prediction.pk), other_prediction)
        self.assertEqual(
            list(
                TelemetryEvent.objects.order_by("pk").values_list(
                    "pk", "recorded_at", "gnss_speed_kph", "rpm"
                )
            ),
            telemetry_snapshot,
        )
        self.assertIn("DEMO/TEST/RESEARCH", output.getvalue())
        self.assertIn("skipped 2 existing prediction(s)", output.getvalue())

    @override_settings(DEBUG=True)
    def test_clear_removes_only_demo_001_demo_predictions(self):
        demo = self.create_vehicle()
        other = self.create_vehicle("OTHER-001", "Other Vehicle")
        now = timezone.now()
        demo_event = self.create_telemetry(
            demo, suffix="1", speed="30", rpm=1500, recorded_at=now
        )
        other_event = self.create_telemetry(
            other, suffix="2", speed="40", rpm=1800, recorded_at=now
        )
        demo_prediction = FuelPrediction.objects.create(
            vehicle=demo,
            input_timestamp=demo_event.recorded_at,
            estimated_fuel_lph=2.0,
            model_name=contract()["model_name"],
            model_version=contract()["model_version"],
            source_mode=DEMO_SOURCE_MODE,
            validated_inputs=build_demo_inputs(demo_event),
        )
        real_prediction = FuelPrediction.objects.create(
            vehicle=demo,
            input_timestamp=now - timedelta(days=1),
            estimated_fuel_lph=3.0,
            model_name=contract()["model_name"],
            model_version=contract()["model_version"],
            source_mode="explicit_validated_api",
            validated_inputs=build_demo_inputs(demo_event),
        )
        other_demo_prediction = FuelPrediction.objects.create(
            vehicle=other,
            input_timestamp=other_event.recorded_at,
            estimated_fuel_lph=4.0,
            model_name=contract()["model_name"],
            model_version=contract()["model_version"],
            source_mode=DEMO_SOURCE_MODE,
            validated_inputs=build_demo_inputs(other_event),
        )
        telemetry_count = TelemetryEvent.objects.count()
        output = StringIO()

        call_command("seed_fuel_demo", "--clear", stdout=output)

        self.assertFalse(FuelPrediction.objects.filter(pk=demo_prediction.pk).exists())
        self.assertTrue(FuelPrediction.objects.filter(pk=real_prediction.pk).exists())
        self.assertTrue(
            FuelPrediction.objects.filter(pk=other_demo_prediction.pk).exists()
        )
        self.assertEqual(TelemetryEvent.objects.count(), telemetry_count)
        self.assertIn("for DEMO-001 only", output.getvalue())
