#!/usr/bin/env python3
"""Publish simulated FTMS telemetry through MQTT with acknowledged QoS delivery."""

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from uuid import uuid4

import paho.mqtt.client as mqtt


def build_event(sequence_number, device_id):
    sample_index = sequence_number % 5
    nullable_sample = sample_index == 2
    return {
        "schema_version": "1.0",
        "event_id": f"mqtt-{sequence_number}-{uuid4()}",
        "sequence_number": sequence_number,
        "device_id": device_id,
        "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "latitude": round(14.5186 + sample_index * 0.0002, 6),
        "longitude": round(121.0196 + sample_index * 0.0002, 6),
        "gnss_speed_kph": round(30 + sample_index * 2.1, 2),
        "rpm": None if nullable_sample else 1500 + sample_index * 100,
        "coolant_c": None if nullable_sample else 85 + sample_index,
        "engine_load_pct": None if nullable_sample else 30 + sample_index * 3,
        "driving_event": "NORMAL",
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broker-host", default="localhost")
    parser.add_argument("--broker-port", type=int, default=1883)
    parser.add_argument("--topic-prefix", default="ftms/v1/telemetry")
    parser.add_argument("--device-id", default="LILYGO-001")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--qos", type=int, default=1, choices=(0, 1, 2))
    return parser.parse_args()


def main():
    args = parse_args()
    if args.count < 1 or args.interval < 0:
        print("count must be positive and interval cannot be negative", file=sys.stderr)
        return 2

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    try:
        client.connect(args.broker_host, args.broker_port, keepalive=30)
        client.loop_start()
        topic = f"{args.topic_prefix.rstrip('/')}/{args.device_id}"
        sequence_start = int(time.time() * 1000)
        for offset in range(args.count):
            event = build_event(sequence_start + offset, args.device_id)
            publication = client.publish(
                topic,
                json.dumps(event),
                qos=args.qos,
                retain=False,
            )
            publication.wait_for_publish(timeout=10)
            if not publication.is_published():
                raise RuntimeError("broker acknowledgement timed out")
            print(
                f"published event_id={event['event_id']} "
                f"device_id={args.device_id} qos={args.qos}"
            )
            if offset + 1 < args.count:
                time.sleep(args.interval)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"MQTT publication failed: {exc}", file=sys.stderr)
        return 1
    finally:
        client.disconnect()
        client.loop_stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
