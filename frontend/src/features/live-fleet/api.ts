import { api } from "../../services/api";

export type TelemetryState = "live" | "stale" | "offline" | "no_telemetry";
export type PositionSource = "GNSS" | "CELLULAR_LBS" | "SIMULATED_TEST";
export type ObdSource = "SIMULATED_TEST" | "PHYSICAL_OBD";

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
  photo_url: string | null;
  is_active: boolean;
  telemetry_state: TelemetryState;
  telemetry: null | {
    latitude: number;
    longitude: number;
    speed_kph: number | null;
    position_source?: PositionSource;
    position_accuracy_m?: number | null;
    recorded_at: string;
    age_seconds: number;
    driving_event: string | null;
    rpm?: number | null;
    coolant_c?: number | null;
    engine_load_pct?: number | null;
    obd_source?: ObdSource | null;
    telemetry_source: "real" | "demo";
    is_demo_telemetry: boolean;
  };
  active_assignment: FleetAssignment | null;
  emergency_sos?: null | {
    id: number;
    device_id: string;
    vehicle_id: number | null;
    driver_id: number | null;
    status: "ACTIVE";
    source: "PHYSICAL_BUTTON";
    activated_at: string;
    cleared_at: null;
  };
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

export type FleetActiveRoute = {
  phase: "TO_PICKUP" | "TO_DESTINATION" | "ARRIVED" | "COMPLETED";
  execution_status: FleetAssignment["execution_status"] | "COMPLETED" | "RECOMMENDATION";
  route_status: "AVAILABLE" | "POSITION_UNAVAILABLE" | "TEMPORARILY_UNAVAILABLE" | "NOT_ACTIVE";
  position_state: "CURRENT" | "STALE" | "UNAVAILABLE";
  position_recorded_at: string | null;
  position_age_seconds: number | null;
  route_basis: "CURRENT_VEHICLE_POSITION" | "LAST_KNOWN_VEHICLE_POSITION" | "PICKUP" | null;
  vehicle_position: null | {
    latitude: number;
    longitude: number;
    recorded_at: string;
    is_stale: boolean;
    source: PositionSource;
  };
  pickup: { name: string; latitude: number; longitude: number };
  destination: { name: string; latitude: number; longitude: number };
  route: null | {
    geometry: { type: "LineString"; coordinates: [number, number][] };
    distance_meters: number;
    duration_seconds: number;
    traffic_delay_seconds: number;
    departure_time: string;
    arrival_time: string;
    traffic_mode: "live";
  };
  planned_route_status: "AVAILABLE" | "TEMPORARILY_UNAVAILABLE" | "NOT_APPLICABLE";
  planned_route: FleetActiveRoute["route"];
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
  event_type: "HARSH_BRAKING" | "HARSH_ACCELERATION" | "SHARP_TURN";
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

export const getFleetActiveAssignmentRoute = (
  assignmentId: number,
  signal?: AbortSignal,
) =>
  api<{ route: FleetActiveRoute }>(
    `/api/v1/fleet-live/assignments/${assignmentId}/route/`,
    { signal },
  );

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
