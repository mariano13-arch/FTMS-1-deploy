export type TelemetryEvent = {
  schema_version: "1.0";
  event_id: string;
  sequence_number: number;
  device_id: string;
  recorded_at: string;
  received_at: string;
  latitude: number;
  longitude: number;
  gnss_speed_kph: number;
  rpm: number | null;
  coolant_c: number | null;
  engine_load_pct: number | null;
  driving_event: "NORMAL" | "HARSH_BRAKING" | "HARSH_ACCELERATION" | "SHARP_TURN";
};

export type LatestStatusResponse = {
  vehicle: {
    device_id: string;
    plate_number: string;
    display_name: string;
  };
  latest: TelemetryEvent | null;
};

import { api } from "./api";

export async function getLatestStatus(
  deviceId: string,
  signal?: AbortSignal,
): Promise<LatestStatusResponse> {
  return api<LatestStatusResponse>(
    `/api/v1/vehicles/${encodeURIComponent(deviceId)}/latest-status/`, { signal },
  );
}
