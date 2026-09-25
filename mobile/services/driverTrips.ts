import { api, ApiError } from '@/services/api';
import type {
  DriverTrip,
  DriverTripExecution,
  DriverTripExecutionAction,
  DriverTripExecutionStatus,
  DriverTripRoute,
  DriverVehiclePosition,
} from '@/types';

type DriverTripExecutionPayload = {
  assignment_id: number;
  trip_id: string;
  status: DriverTripExecutionStatus;
  status_label: string;
  allowed_actions: DriverTripExecutionAction[];
  execution_started_at: string | null;
  pickup_arrived_at: string | null;
  pickup_departed_at: string | null;
  destination_arrived_at: string | null;
  completed_at: string | null;
};

type DriverTripPayload = {
  id: string;
  request_number: string;
  request_type: string;
  request_type_label: string;
  request_category: string | null;
  request_category_label: string | null;
  priority: string;
  priority_label: string;
  status: string;
  status_label: string;
  is_accepted: boolean;
  accepted_at: string | null;
  assignment_confirmed_at: string;
  scheduled_pickup_at: string;
  estimated_duration_minutes: number;
  passenger_count: number;
  luggage_count: number;
  pickup: { name: string; address: string };
  destination: { name: string; address: string };
  vehicle: {
    id: number;
    display_name: string;
    plate_number: string;
    vehicle_type: string;
    vehicle_type_label: string;
    passenger_capacity: number | null;
    payload_capacity_kg: string | null;
  };
  handling_instructions: string;
  load_description: string;
  load_quantity: number | null;
  estimated_weight_kg: string | null;
  temperature_requirement: string;
  flight_context: {
    flight_number: string;
    terminal: string;
    scheduled_arrival_at: string | null;
    estimated_arrival_at: string | null;
    actual_arrival_at: string | null;
    provider_flight_status: string;
    refresh_status: string;
    refresh_message: string;
  } | null;
  capacity_compatibility: { status: string; message: string };
  execution: DriverTripExecutionPayload;
};

type DriverRoadRoutePayload = {
  geometry: {
    type: 'LineString';
    coordinates: [number, number][];
  };
  distance_meters: number;
  duration_seconds: number;
  traffic_delay_seconds: number;
  departure_time: string;
  arrival_time: string;
  traffic_mode: 'live';
};

type DriverVehiclePositionPayload = {
  latitude: number;
  longitude: number;
  recorded_at: string;
  is_stale: boolean;
  source: 'GNSS' | 'CELLULAR_LBS' | 'SIMULATED_TEST';
};

type DriverTripRoutePayload = {
  phase: DriverTripRoute['phase'];
  execution_status: DriverTripExecutionStatus;
  route_status: DriverTripRoute['routeStatus'];
  position_state: DriverTripRoute['positionState'];
  position_recorded_at: string | null;
  position_age_seconds: number | null;
  route_basis: DriverTripRoute['routeBasis'];
  vehicle_position: DriverVehiclePositionPayload | null;
  pickup: { name: string; latitude: number; longitude: number };
  destination: { name: string; latitude: number; longitude: number };
  route: DriverRoadRoutePayload | null;
};

function isRoutePlace(value: unknown): value is DriverTripRoutePayload['pickup'] {
  if (!value || typeof value !== 'object') return false;
  const place = value as Record<string, unknown>;
  return (
    typeof place.name === 'string' &&
    typeof place.latitude === 'number' &&
    Number.isFinite(place.latitude) &&
    typeof place.longitude === 'number' &&
    Number.isFinite(place.longitude)
  );
}

function assertActiveRouteContract(payload: unknown): asserts payload is DriverTripRoutePayload {
  if (!payload || typeof payload !== 'object') {
    throw new ApiError(
      'Active route details are unavailable because the server response is incomplete.',
      502,
    );
  }
  const activeRoute = payload as Partial<DriverTripRoutePayload>;
  if (!isRoutePlace(activeRoute.pickup) || !isRoutePlace(activeRoute.destination)) {
    throw new ApiError(
      'Active route details are unavailable because the server response is incomplete.',
      502,
    );
  }
}

function mapDriverTripExecution(payload: DriverTripExecutionPayload): DriverTripExecution {
  return {
    assignmentId: payload.assignment_id,
    tripId: payload.trip_id,
    status: payload.status,
    statusLabel: payload.status_label,
    allowedActions: payload.allowed_actions,
    executionStartedAt: payload.execution_started_at,
    pickupArrivedAt: payload.pickup_arrived_at,
    pickupDepartedAt: payload.pickup_departed_at,
    destinationArrivedAt: payload.destination_arrived_at,
    completedAt: payload.completed_at,
  };
}

function mapDriverTrip(payload: DriverTripPayload): DriverTrip {
  return {
    id: payload.id,
    requestNumber: payload.request_number,
    requestType: payload.request_type,
    requestTypeLabel: payload.request_type_label,
    requestCategory: payload.request_category,
    requestCategoryLabel: payload.request_category_label,
    priority: payload.priority,
    priorityLabel: payload.priority_label,
    status: payload.status,
    statusLabel: payload.status_label,
    isAccepted: payload.is_accepted,
    acceptedAt: payload.accepted_at,
    assignmentConfirmedAt: payload.assignment_confirmed_at,
    scheduledPickupAt: payload.scheduled_pickup_at,
    estimatedDurationMinutes: payload.estimated_duration_minutes,
    passengerCount: payload.passenger_count,
    luggageCount: payload.luggage_count,
    pickup: payload.pickup,
    destination: payload.destination,
    vehicle: {
      id: payload.vehicle.id,
      displayName: payload.vehicle.display_name,
      plateNumber: payload.vehicle.plate_number,
      vehicleType: payload.vehicle.vehicle_type,
      vehicleTypeLabel: payload.vehicle.vehicle_type_label,
      passengerCapacity: payload.vehicle.passenger_capacity,
      payloadCapacityKg: payload.vehicle.payload_capacity_kg,
    },
    handlingInstructions: payload.handling_instructions,
    loadDescription: payload.load_description,
    loadQuantity: payload.load_quantity,
    estimatedWeightKg: payload.estimated_weight_kg,
    temperatureRequirement: payload.temperature_requirement,
    flightContext: payload.flight_context ? {
      flightNumber: payload.flight_context.flight_number,
      terminal: payload.flight_context.terminal,
      scheduledArrivalAt: payload.flight_context.scheduled_arrival_at,
      estimatedArrivalAt: payload.flight_context.estimated_arrival_at,
      actualArrivalAt: payload.flight_context.actual_arrival_at,
      providerFlightStatus: payload.flight_context.provider_flight_status,
      refreshStatus: payload.flight_context.refresh_status,
      refreshMessage: payload.flight_context.refresh_message,
    } : null,
    capacityCompatibility: payload.capacity_compatibility,
    execution: mapDriverTripExecution(payload.execution),
  };
}

export async function getDriverTrips(signal?: AbortSignal): Promise<DriverTrip[]> {
  const response = await api<{ trips: DriverTripPayload[] }>('/api/v1/driver-trips/', {
    signal,
  });
  return response.trips.map(mapDriverTrip);
}

export async function getDriverTrip(
  tripId: string,
  signal?: AbortSignal,
): Promise<DriverTrip> {
  const response = await api<{ trip: DriverTripPayload }>(
    `/api/v1/driver-trips/${encodeURIComponent(tripId)}/`,
    { signal },
  );
  return mapDriverTrip(response.trip);
}

export async function acceptDriverTrip(
  tripId: string,
  confirmedAt: string,
): Promise<DriverTrip> {
  const response = await api<{ trip: DriverTripPayload }>(
    `/api/v1/driver-trips/${encodeURIComponent(tripId)}/accept/`,
    { method: 'POST', body: JSON.stringify({ confirmed_at: confirmedAt }) },
  );
  return mapDriverTrip(response.trip);
}

export async function transitionDriverTrip(
  tripId: string,
  action: DriverTripExecutionAction,
): Promise<DriverTripExecution> {
  const response = await api<{ execution: DriverTripExecutionPayload }>(
    `/api/v1/driver-trips/${encodeURIComponent(tripId)}/transition/`,
    {
      method: 'POST',
      body: JSON.stringify({ action }),
    },
  );
  return mapDriverTripExecution(response.execution);
}

export async function getDriverTripRoute(
  tripId: string,
  signal?: AbortSignal,
): Promise<DriverTripRoute> {
  const response = await api<{ route: unknown }>(
    `/api/v1/driver-trips/${encodeURIComponent(tripId)}/route/`,
    { signal },
  );
  assertActiveRouteContract(response.route);
  return {
    phase: response.route.phase,
    executionStatus: response.route.execution_status,
    routeStatus: response.route.route_status,
    positionState: response.route.position_state,
    positionRecordedAt: response.route.position_recorded_at,
    positionAgeSeconds: response.route.position_age_seconds,
    routeBasis: response.route.route_basis,
    vehiclePosition: response.route.vehicle_position ? {
      latitude: response.route.vehicle_position.latitude,
      longitude: response.route.vehicle_position.longitude,
      recordedAt: response.route.vehicle_position.recorded_at,
      isStale: response.route.vehicle_position.is_stale,
      source: response.route.vehicle_position.source,
    } : null,
    pickup: response.route.pickup,
    destination: response.route.destination,
    route: response.route.route ? {
      geometry: response.route.route.geometry,
      distanceMeters: response.route.route.distance_meters,
      durationSeconds: response.route.route.duration_seconds,
      trafficDelaySeconds: response.route.route.traffic_delay_seconds,
      departureTime: response.route.route.departure_time,
      arrivalTime: response.route.route.arrival_time,
      trafficMode: response.route.route.traffic_mode,
    } : null,
  };
}

export async function getDriverTripVehiclePosition(
  tripId: string,
  signal?: AbortSignal,
): Promise<DriverVehiclePosition | null> {
  const response = await api<{ vehicle_position: DriverVehiclePositionPayload | null }>(
    `/api/v1/driver-trips/${encodeURIComponent(tripId)}/vehicle-position/`,
    { signal },
  );
  if (!response.vehicle_position) {
    return null;
  }
  return {
    latitude: response.vehicle_position.latitude,
    longitude: response.vehicle_position.longitude,
    recordedAt: response.vehicle_position.recorded_at,
    isStale: response.vehicle_position.is_stale,
    source: response.vehicle_position.source,
  };
}
