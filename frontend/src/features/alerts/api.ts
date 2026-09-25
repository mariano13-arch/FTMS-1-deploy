import { api } from "../../services/api";

export type Page<T> = { count: number; next: string | null; previous: string | null; results: T[] };
export type AlertSummary = {
  active_attention: number;
  safety_events_today: number;
  restricted_entries_today: number;
  vehicle_device_attention: number;
};
export type VehicleIdentity = { id: number; device_id: string; display_name: string; plate_number: string };
export type AttentionItem = {
  id: string;
  condition: string;
  source: "TELEMETRY" | "INSPECTION" | "MAINTENANCE";
  current_state: string;
  last_updated_at: string | null;
  vehicle: VehicleIdentity;
  details: Record<string, unknown>;
};
export type AttentionResponse = Page<AttentionItem> & { summary: AlertSummary };
export type SafetyIncident = {
  event_id: string;
  event_type: "HARSH_BRAKING" | "HARSH_ACCELERATION" | "SHARP_TURN";
  recorded_at: string;
  received_at: string;
  latitude: number;
  longitude: number;
  position_source: "GNSS" | "CELLULAR_LBS" | "SIMULATED_TEST";
  position_accuracy_m: number | null;
  speed_kph: number | null;
  rpm: number | null;
  coolant_c: number | null;
  engine_load_pct: number | null;
  obd_source: "PHYSICAL_OBD" | "SIMULATED_TEST" | null;
  vehicle_id: number;
  device_id: string;
  vehicle_device_id: string;
  vehicle_name: string;
  plate_number: string;
};
export type GeofenceActivity = {
  id: number;
  event_type: "ENTER" | "EXIT";
  occurred_at: string;
  latitude: number;
  longitude: number;
  vehicle_id: number;
  device_id: string;
  vehicle_name: string;
  plate_number: string;
  geofence_id: string;
  geofence_name: string;
  geofence_category: "DEPOT" | "CUSTOMER" | "HOTEL" | "RESTRICTED" | "CUSTOM";
  geofence_shape_type: "CIRCLE" | "POLYGON";
  geofence_radius_meters: number | null;
  telemetry_event_id: string;
  telemetry_position_source: "GNSS" | "CELLULAR_LBS" | "SIMULATED_TEST";
  telemetry_recorded_at: string;
  created_at: string;
  is_restricted_entry: boolean;
};
export type AlertVehicleOption = { vehicle_id: number; device_id: string; display_name: string; plate_number: string };
export type AlertGeofenceOption = { id: string; name: string; category: GeofenceActivity["geofence_category"] };

const query = (values: Record<string, string | number | undefined>) => {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  return params.toString();
};

export const getActiveAttention = (filters: Record<string, string | number | undefined>, signal?: AbortSignal) =>
  api<AttentionResponse>(`/api/v1/alerts/active-attention/?${query({ ...filters, page_size: 15 })}`, { signal });

export const getSafetyIncidents = (filters: Record<string, string | number | undefined>, signal?: AbortSignal) =>
  api<Page<SafetyIncident> & { events?: SafetyIncident[] }>(`/api/v1/fleet-live/safety-events/?${query({ ...filters, page_size: 15 })}`, { signal }).then(payload => ({
    count: payload.count ?? payload.events?.length ?? 0,
    next: payload.next ?? null,
    previous: payload.previous ?? null,
    results: payload.results ?? payload.events ?? [],
  }));

export const getGeofenceActivity = (filters: Record<string, string | number | undefined>, signal?: AbortSignal) =>
  api<Page<GeofenceActivity>>(`/api/v1/fleet-live/geofence-events/?${query({ ...filters, page_size: 15 })}`, { signal });

export const getAlertVehicleOptions = (signal?: AbortSignal) =>
  api<{ vehicles: AlertVehicleOption[] }>("/api/v1/fleet-live/vehicles/", { signal });

export const getAlertGeofenceOptions = (signal?: AbortSignal) =>
  api<{ results: AlertGeofenceOption[] }>("/api/v1/fleet-live/geofences/", { signal });
