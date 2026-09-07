import { api } from '@/services/api';
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
  };
  handling_instructions: string;
  load_description: string;
  load_quantity: number | null;
  estimated_weight_kg: string | null;
  temperature_requirement: string;
  execution: DriverTripExecutionPayload;
};

type DriverTripRoutePayload = {
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
};

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
    },
    handlingInstructions: payload.handling_instructions,
    loadDescription: payload.load_description,
    loadQuantity: payload.load_quantity,
    estimatedWeightKg: payload.estimated_weight_kg,
    temperatureRequirement: payload.temperature_requirement,
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
  const response = await api<{ route: DriverTripRoutePayload }>(
    `/api/v1/driver-trips/${encodeURIComponent(tripId)}/route/`,
    { signal },
  );
  return {
    geometry: response.route.geometry,
    distanceMeters: response.route.distance_meters,
    durationSeconds: response.route.duration_seconds,
    trafficDelaySeconds: response.route.traffic_delay_seconds,
    departureTime: response.route.departure_time,
    arrivalTime: response.route.arrival_time,
    trafficMode: response.route.traffic_mode,
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
  };
}
