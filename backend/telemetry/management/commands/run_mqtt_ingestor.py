import logging
import os
import signal

import paho.mqtt.client as mqtt
from django.core.management.base import BaseCommand

from telemetry.mqtt import handle_mqtt_message

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the long-lived Sprint 2 MQTT telemetry ingestor."

    def handle(self, *args, **options):
        host = os.getenv("MQTT_HOST", "mosquitto")
        port = int(os.getenv("MQTT_PORT", "1883"))
        topic_prefix = os.getenv("MQTT_TOPIC_PREFIX", "ftms/v1/telemetry").rstrip("/")
        qos = int(os.getenv("MQTT_QOS", "1"))
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.enable_logger(logger)

        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code == 0:
                client.subscribe(f"{topic_prefix}/+", qos=qos)
                logger.info("MQTT ingestor subscribed prefix=%s qos=%s", topic_prefix, qos)
            else:
                logger.warning("MQTT connection rejected reason=%s", reason_code)

        def on_message(client, userdata, message):
            try:
                handle_mqtt_message(message, topic_prefix)
            except Exception:
                logger.exception("Unexpected MQTT handler failure topic=%s", message.topic)

        def shutdown(signum, frame):
            logger.info("MQTT ingestor shutting down")
            client.disconnect()

        client.on_connect = on_connect
        client.on_message = on_message
        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
        client.connect_async(host, port, keepalive=30)
        logger.info("MQTT ingestor starting host=%s port=%s", host, port)
        client.loop_forever(retry_first_connection=True)
