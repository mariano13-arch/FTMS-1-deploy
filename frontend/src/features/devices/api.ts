import { api } from "../../services/api";

export type DeviceTelemetry = {
  recorded_at: string;
  position_source: "GNSS" | "CELLULAR_LBS" | "SIMULATED_TEST";
  obd_source: "PHYSICAL_OBD" | "SIMULATED_TEST" | null;
  latitude: number;
  longitude: number;
};

export type DeviceBinding = {
  id: number;
  paired_at: string;
  paired_by: string | null;
};

export type Device = {
  device_id: string;
  registration_status: "REGISTERED" | "RETIRED";
  created_at: string;
  is_paired: boolean;
  current_vehicle: null | {
    vehicle_id: number;
    plate_number: string;
    display_name: string;
    compatibility_device_id: string;
  };
  current_binding: DeviceBinding | null;
  latest_telemetry: DeviceTelemetry | null;
};

export type DeviceDetail = Device & {
  can_manage: boolean;
  binding_history: Array<{
    id: number;
    vehicle_id: number;
    vehicle_name: string;
    plate_number: string;
    paired_at: string;
    unpaired_at: string | null;
    paired_by: string | null;
    unpaired_by: string | null;
  }>;
};

export type DevicePage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: Device[];
  summary: {
    total_registered: number;
    paired: number;
    unpaired: number;
    recently_seen: number;
  };
  can_manage: boolean;
};

export const getDevices = (query: string, signal?: AbortSignal) =>
  api<DevicePage>(`/api/v1/telemetry-devices/${query ? `?${query}` : ""}`, { signal });

export const getDevice = (deviceId: string, signal?: AbortSignal) =>
  api<DeviceDetail>(`/api/v1/telemetry-devices/${encodeURIComponent(deviceId)}/`, { signal });

export const pairDevice = (deviceId: string, vehicleId: number, replaceCurrent: boolean) =>
  api<Device>(`/api/v1/telemetry-devices/${encodeURIComponent(deviceId)}/pair/`, {
    method: "POST",
    body: JSON.stringify({ vehicle_id: vehicleId, replace_current: replaceCurrent }),
  });

export const unpairDevice = (deviceId: string) =>
  api<Device>(`/api/v1/telemetry-devices/${encodeURIComponent(deviceId)}/unpair/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
