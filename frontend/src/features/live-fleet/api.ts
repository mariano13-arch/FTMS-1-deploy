import { api } from "../../services/api";

export type TelemetryState = "live" | "stale" | "offline" | "no_telemetry";

export type FleetAssignment = {
  assignment_id: number;
  execution_status:
    | "ASSIGNED"
    | "EN_ROUTE_TO_PICKUP"
    | "AT_PICKUP"
    | "IN_TRANSIT"
    | "AT_DESTINATION";
  driver_id: number;
  driver_code: string;
  driver_name: string;
  request_id: string;
  request_number: string;
  request_status: "APPROVED" | "READY_FOR_DISPATCH";
  source_system:
    | "HOTEL_MANAGEMENT_SYSTEM"
    | "RESTAURANT_MANAGEMENT_SYSTEM"
    | "MANUAL_STAFF_ENTRY"
    | "OTHER_SUBSYSTEM";
  scheduled_pickup_at: string;
  pickup_name: string;
  pickup_latitude: string;
  pickup_longitude: string;
  destination_name: string;
  destination_latitude: string;
  destination_longitude: string;
};

export type FleetLiveVehicle = {
  vehicle_id: number;
  device_id: string;
  display_name: string;
  plate_number: string;
  vehicle_type: string;
  is_active: boolean;
  telemetry_state: TelemetryState;
  telemetry: null | {
    latitude: number;
    longitude: number;
    speed_kph: number;
    recorded_at: string;
    age_seconds: number;
    driving_event: string;
    telemetry_source: "real" | "demo";
    is_demo_telemetry: boolean;
  };
  active_assignment: FleetAssignment | null;
};

export type FleetLiveResponse = {
  generated_at: string;
  capabilities: {
    telemetry_trail: boolean;
    safety_events: boolean;
    geofence: boolean;
    demo_telemetry: boolean;
  };
  demo_telemetry: {
    enabled: boolean;
    active: boolean;
    simulated_vehicle_count: number;
    configuration_error?: string;
  };
  vehicles: FleetLiveVehicle[];
};

export type FleetTrailPoint = {
  event_id: string;
  latitude: number;
  longitude: number;
  speed_kph: number;
  recorded_at: string;
};

export type FleetTrailResponse = {
  vehicle_id: number;
  device_id: string;
  points: FleetTrailPoint[];
};

export type FleetSafetyEvent = {
  event_id: string;
  event_type: "HARSH_BRAKING" | "HARSH_ACCELERATION";
  recorded_at: string;
  latitude: number;
  longitude: number;
  speed_kph: number;
  vehicle_id: number;
  device_id: string;
  vehicle_name: string;
  plate_number: string;
};

export type FleetSafetyEventResponse = {
  events: FleetSafetyEvent[];
};

export type GeofenceCoordinate = {
  latitude: number;
  longitude: number;
};

export type GeofenceEvent = {
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
  geofence_category: Geofence["category"];
};

export type Geofence = {
  id: string;
  name: string;
  description: string;
  category: "DEPOT" | "CUSTOMER" | "HOTEL" | "RESTRICTED" | "CUSTOM";
  shape_type: "CIRCLE" | "POLYGON";
  vertices: GeofenceCoordinate[];
  center: GeofenceCoordinate;
  radius_meters: number | null;
  color: string;
  show_on_map: boolean;
  is_active: boolean;
  current_vehicle_count: number;
  event_count: number;
  entries_today: number;
  exits_today: number;
  latest_event: GeofenceEvent | null;
  created_at: string;
  updated_at: string;
  current_vehicles?: Array<{
    vehicle_id: number;
    device_id: string;
    vehicle_name: string;
    plate_number: string;
    recorded_at: string;
  }>;
  events?: GeofenceEvent[];
};

export type GeofenceWrite = Pick<
  Geofence,
  | "name"
  | "description"
  | "category"
  | "shape_type"
  | "vertices"
  | "center"
  | "radius_meters"
  | "color"
  | "show_on_map"
  | "is_active"
>;

export type GeofenceActivityFilters = {
  geofence?: string;
  vehicle?: number;
  event_type?: GeofenceEvent["event_type"];
  date_from?: string;
  date_to?: string;
  page?: number;
  page_size?: number;
};

export type GeofenceActivityResponse = {
  count: number;
  next: string | null;
  previous: string | null;
  results: GeofenceEvent[];
};

export const getFleetLiveVehicles = (signal?: AbortSignal) =>
  api<FleetLiveResponse>("/api/v1/fleet-live/vehicles/", { signal });

export const getFleetVehicleTrail = (
  vehicleId: number,
  signal?: AbortSignal,
) =>
  api<FleetTrailResponse>(
    `/api/v1/fleet-live/vehicles/${vehicleId}/trail/`,
    {
      signal,
    },
  );

export const getFleetSafetyEvents = (signal?: AbortSignal) =>
  api<FleetSafetyEventResponse>("/api/v1/fleet-live/safety-events/", {
    signal,
  });

export const getGeofences = (signal?: AbortSignal) =>
  api<{ results: Geofence[] }>("/api/v1/fleet-live/geofences/", {
    signal,
  });

export const getGeofence = (id: string, signal?: AbortSignal) =>
  api<Geofence>(
    `/api/v1/fleet-live/geofences/${encodeURIComponent(id)}/`,
    {
      signal,
    },
  );

export const getGeofenceActivity = (
  filters: GeofenceActivityFilters,
  signal?: AbortSignal,
) => {
  const query = new URLSearchParams();

  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      query.set(key, String(value));
    }
  });

  return api<GeofenceActivityResponse>(
    `/api/v1/fleet-live/geofence-events/?${query.toString()}`,
    {
      signal,
    },
  );
};

export const createGeofence = (
  body: GeofenceWrite,
  signal?: AbortSignal,
) =>
  api<Geofence>("/api/v1/fleet-live/geofences/", {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });

export const updateGeofence = (
  id: string,
  body: GeofenceWrite,
  signal?: AbortSignal,
) =>
  api<Geofence>(
    `/api/v1/fleet-live/geofences/${encodeURIComponent(id)}/`,
    {
      method: "PATCH",
      body: JSON.stringify(body),
      signal,
    },
  );