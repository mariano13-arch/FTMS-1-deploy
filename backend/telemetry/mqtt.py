import json
import logging

from telemetry.services import (
    IngestionStatus,
    TelemetryValidationError,
    ingest_telemetry,
)

logger = logging.getLogger(__name__)
MAX_MQTT_PAYLOAD_BYTES = 65_536


def handle_mqtt_message(message, topic_prefix):
    topic = message.topic
    if message.retain:
        logger.warning("Rejected retained telemetry topic=%s", topic)
        return None
    if len(message.payload) > MAX_MQTT_PAYLOAD_BYTES:
        logger.warning("Rejected oversized telemetry topic=%s", topic)
        return None
    try:
        payload = json.loads(message.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Rejected malformed telemetry topic=%s", topic)
        return None
    if not isinstance(payload, dict):
        logger.warning("Rejected non-object telemetry topic=%s", topic)
        return None

    expected_prefix = f"{topic_prefix.rstrip('/')}/"
    topic_device_id = topic.removeprefix(expected_prefix)
    if (
        not topic.startswith(expected_prefix)
        or "/" in topic_device_id
        or payload.get("device_id") != topic_device_id
    ):
        logger.warning("Rejected topic/device mismatch topic=%s", topic)
        return None

    try:
        result = ingest_telemetry(payload)
    except TelemetryValidationError:
        logger.warning(
            "Rejected invalid telemetry device_id=%s event_id=%s topic=%s",
            payload.get("device_id"),
            payload.get("event_id"),
            topic,
        )
        return None

    if result.status == IngestionStatus.CONFLICT:
        logger.warning(
            "Rejected conflicting telemetry device_id=%s event_id=%s topic=%s",
            payload.get("device_id"),
            payload.get("event_id"),
            topic,
        )
        return result
    logger.info(
        "Accepted telemetry result=%s device_id=%s event_id=%s topic=%s",
        result.status,
        payload.get("device_id"),
        payload.get("event_id"),
        topic,
    )
    return result
