import type { LatestStatusResponse, TelemetryEvent } from "./telemetry";
import { apiBaseUrl } from "./api";

export type VehicleStatusMessage = {
  type: "vehicle.status.snapshot" | "vehicle.status.updated";
  data: LatestStatusResponse;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value));
}

function isNumberInRange(value: unknown, minimum: number, maximum: number) {
  return (
    typeof value === "number" &&
    Number.isFinite(value) &&
    value >= minimum &&
    value <= maximum
  );
}

function isValidTimestamp(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

function isTelemetryEvent(
  value: unknown,
  vehicleDeviceId: string,
): value is TelemetryEvent {
  if (!isRecord(value)) return false;
  return (
    value.schema_version === "1.0" &&
    typeof value.event_id === "string" &&
    Number.isSafeInteger(value.sequence_number) &&
    Number(value.sequence_number) >= 0 &&
    value.device_id === vehicleDeviceId &&
    isValidTimestamp(value.recorded_at) &&
    isValidTimestamp(value.received_at) &&
    isNumberInRange(value.latitude, -90, 90) &&
    isNumberInRange(value.longitude, -180, 180) &&
    isNumberInRange(value.gnss_speed_kph, 0, 300) &&
    (value.rpm === null ||
      (Number.isSafeInteger(value.rpm) &&
        Number(value.rpm) >= 0 &&
        Number(value.rpm) <= 12_000)) &&
    isNullableNumber(value.coolant_c) &&
    (value.engine_load_pct === null ||
      isNumberInRange(value.engine_load_pct, 0, 100)) &&
    ["NORMAL", "HARSH_BRAKING", "HARSH_ACCELERATION", "SHARP_TURN"].includes(
      String(value.driving_event),
    )
  );
}

export function parseVehicleStatusMessage(
  raw: string,
  requestedDeviceId: string,
): VehicleStatusMessage | null {
  try {
    const message: unknown = JSON.parse(raw);
    if (!isRecord(message) || !isRecord(message.data)) return null;
    if (
      message.type !== "vehicle.status.snapshot" &&
      message.type !== "vehicle.status.updated"
    ) {
      return null;
    }
    const vehicle = message.data.vehicle;
    const latest = message.data.latest;
    if (
      !isRecord(vehicle) ||
      typeof vehicle.device_id !== "string" ||
      vehicle.device_id.length === 0 ||
      vehicle.device_id !== requestedDeviceId ||
      typeof vehicle.plate_number !== "string" ||
      typeof vehicle.display_name !== "string" ||
      (latest !== null && !isTelemetryEvent(latest, vehicle.device_id))
    ) {
      return null;
    }
    return message as VehicleStatusMessage;
  } catch {
    return null;
  }
}

export function isNewerEvent(
  candidate: TelemetryEvent,
  current: TelemetryEvent | null,
): boolean {
  if (current === null) return true;
  const candidateRecordedAt = Date.parse(candidate.recorded_at);
  const currentRecordedAt = Date.parse(current.recorded_at);
  if (candidateRecordedAt !== currentRecordedAt) {
    return candidateRecordedAt > currentRecordedAt;
  }
  if (candidate.sequence_number !== current.sequence_number) {
    return candidate.sequence_number > current.sequence_number;
  }
  const candidateReceivedAt = Date.parse(candidate.received_at);
  const currentReceivedAt = Date.parse(current.received_at);
  if (candidateReceivedAt !== currentReceivedAt) {
    return candidateReceivedAt > currentReceivedAt;
  }
  return candidate.event_id > current.event_id;
}

export function vehicleStatusWebSocketUrl(deviceId: string): string {
  const configured = import.meta.env.VITE_WS_BASE_URL as string | undefined;
  const baseUrl =
    configured ??
    apiBaseUrl.replace(/^http:/, "ws:").replace(/^https:/, "wss:");
  return `${baseUrl.replace(/\/$/, "")}/ws/v1/vehicles/${encodeURIComponent(deviceId)}/status/`;
}
