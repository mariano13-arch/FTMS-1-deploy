from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from telemetry.management.commands.run_mqtt_ingestor import Command


class FakeClient:
    instance = None

    def __init__(self, *args, **kwargs):
        type(self).instance = self
        self.on_connect = None
        self.on_message = None
        self.connected = None
        self.retry_first_connection = None

    def enable_logger(self, logger):
        self.logger = logger

    def subscribe(self, topic, qos):
        self.subscription = (topic, qos)

    def connect_async(self, host, port, keepalive):
        self.connected = (host, port, keepalive)

    def loop_forever(self, retry_first_connection):
        self.retry_first_connection = retry_first_connection
        self.on_message(
            self,
            None,
            SimpleNamespace(topic="ftms/v1/telemetry/LILYGO-001", payload=b"{", retain=False),
        )

    def disconnect(self):
        self.disconnected = True


class MqttCommandTests(SimpleTestCase):
    @patch("telemetry.management.commands.run_mqtt_ingestor.signal.signal")
    @patch("telemetry.management.commands.run_mqtt_ingestor.handle_mqtt_message")
    @patch(
        "telemetry.management.commands.run_mqtt_ingestor.mqtt.Client",
        side_effect=FakeClient,
    )
    def test_command_retries_initial_connection_and_survives_bad_message(
        self, client_factory, handler, signal_mock
    ):
        handler.side_effect = ValueError("bad message")

        Command().handle()

        client = FakeClient.instance
        self.assertEqual(client.connected, ("mosquitto", 1883, 30))
        self.assertTrue(client.retry_first_connection)
        handler.assert_called_once()
        self.assertEqual(signal_mock.call_count, 2)
