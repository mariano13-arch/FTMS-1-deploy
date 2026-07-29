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

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function getLatestStatus(
  deviceId: string,
  signal?: AbortSignal,
): Promise<LatestStatusResponse> {
  const response = await fetch(
    `${apiBaseUrl}/api/v1/vehicles/${encodeURIComponent(deviceId)}/latest-status/`,
    { signal },
  );
  if (!response.ok) {
    throw new Error("Latest vehicle status request failed");
  }
  return response.json() as Promise<LatestStatusResponse>;
}
