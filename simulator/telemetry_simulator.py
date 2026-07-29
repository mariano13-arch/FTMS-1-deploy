#!/usr/bin/env python3
"""Send deterministic simulated telemetry to the FTMS REST ingestion endpoint."""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from uuid import uuid4


def build_event(sequence_number, device_id):
    sample_index = sequence_number % 5
    nullable_sample = sample_index == 2
    return {
        "schema_version": "1.0",
        "event_id": f"sim-{sequence_number}-{uuid4()}",
        "sequence_number": sequence_number,
        "device_id": device_id,
        "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "latitude": round(14.5186 + sample_index * 0.0001, 6),
        "longitude": round(121.0196 + sample_index * 0.0001, 6),
        "gnss_speed_kph": round(34.0 + sample_index * 1.7, 2),
        "rpm": None if nullable_sample else 1600 + sample_index * 75,
        "coolant_c": None if nullable_sample else 86 + sample_index,
        "engine_load_pct": None if nullable_sample else 31 + sample_index * 2,
        "driving_event": "NORMAL",
    }


def send_event(url, event):
    request = urllib.request.Request(
        url,
        data=json.dumps(event).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, json.load(response)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-base-url",
        default="http://localhost:8000",
        help="FTMS API base URL.",
    )
    parser.add_argument("--device-id", default="LILYGO-001", help="Vehicle device ID.")
    parser.add_argument("--count", type=int, default=1, help="Number of events to send.")
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Delay between events.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.count < 1 or args.interval < 0:
        print("count must be positive and interval cannot be negative", file=sys.stderr)
        return 2

    url = f"{args.api_base_url.rstrip('/')}/api/v1/telemetry/"
    sequence_start = int(time.time() * 1000)
    for offset in range(args.count):
        event = build_event(sequence_start + offset, args.device_id)
        try:
            status, response = send_event(url, event)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"failed to send {event['event_id']}: {exc}", file=sys.stderr)
            return 1
        print(
            f"{status} {event['event_id']} "
            f"status={response.get('status')} duplicate={response.get('duplicate')}"
        )
        if offset + 1 < args.count:
            time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
