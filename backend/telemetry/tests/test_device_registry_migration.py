from datetime import UTC, datetime
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ExistingDeviceMappingMigrationTests(TransactionTestCase):
    migrate_from = ("telemetry", "0002_geofence_geofenceevent")
    migrate_to = ("telemetry", "0003_device_registry_and_bindings")

    def restore_current_telemetry_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes("telemetry"))

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state(
            [self.migrate_from, ("fleet", "0007_driver_driverdocument")]
        ).apps
        Vehicle = old_apps.get_model("fleet", "Vehicle")
        TelemetryEvent = old_apps.get_model("telemetry", "TelemetryEvent")
        vehicle = Vehicle.objects.create(
            device_id="MIGRATED-001",
            plate_number="MIG-001",
            display_name="Migrated Vehicle",
        )
        event = TelemetryEvent.objects.create(
            schema_version="1.0",
            event_id="pre-registry-event",
            sequence_number=1,
            vehicle_id=vehicle.pk,
            recorded_at=datetime(2026, 8, 1, tzinfo=UTC),
            location=Point(121.0196, 14.5186, srid=4326),
            gnss_speed_kph=Decimal("30.00"),
            driving_event="NORMAL",
        )
        self.vehicle_pk = vehicle.pk
        self.event_pk = event.pk

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        self.apps = executor.loader.project_state([self.migrate_to]).apps

    def tearDown(self):
        try:
            self.restore_current_telemetry_schema()
        finally:
            super().tearDown()

    def test_existing_vehicle_and_event_are_backfilled_without_reassignment(self):
        TelemetryDevice = self.apps.get_model("telemetry", "TelemetryDevice")
        TelemetryDeviceBinding = self.apps.get_model(
            "telemetry", "TelemetryDeviceBinding"
        )
        TelemetryEvent = self.apps.get_model("telemetry", "TelemetryEvent")

        device = TelemetryDevice.objects.get(device_id="MIGRATED-001")
        binding = TelemetryDeviceBinding.objects.get(device_id=device.pk)
        event = TelemetryEvent.objects.get(pk=self.event_pk)

        self.assertEqual(binding.vehicle_id, self.vehicle_pk)
        self.assertIsNone(binding.unpaired_at)
        self.assertEqual(event.vehicle_id, self.vehicle_pk)
        self.assertEqual(event.device_id, device.pk)
