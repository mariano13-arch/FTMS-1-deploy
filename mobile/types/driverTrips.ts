export type DriverTripPlace = {
  name: string;
  address: string;
};

export type DriverTripVehicle = {
  id: number;
  displayName: string;
  plateNumber: string;
  vehicleType: string;
  vehicleTypeLabel: string;
  passengerCapacity?: number | null;
  payloadCapacityKg?: string | null;
};

export type DriverTripFlightContext = {
  flightNumber: string;
  terminal: string;
  scheduledArrivalAt: string | null;
  estimatedArrivalAt: string | null;
  actualArrivalAt: string | null;
  providerFlightStatus: string;
  refreshStatus: string;
  refreshMessage: string;
};

export type DriverTripExecutionStatus =
  | 'ASSIGNED'
  | 'EN_ROUTE_TO_PICKUP'
  | 'AT_PICKUP'
  | 'IN_TRANSIT'
  | 'AT_DESTINATION'
  | 'COMPLETED';

export type DriverTripExecutionAction =
  | 'START_TOWARD_PICKUP'
  | 'ARRIVE_AT_PICKUP'
  | 'DEPART_PICKUP'
  | 'ARRIVE_AT_DESTINATION'
  | 'COMPLETE';

export type DriverTripExecution = {
  assignmentId: number;
  tripId: string;
  status: DriverTripExecutionStatus;
  statusLabel: string;
  allowedActions: DriverTripExecutionAction[];
  executionStartedAt: string | null;
  pickupArrivedAt: string | null;
  pickupDepartedAt: string | null;
  destinationArrivedAt: string | null;
  completedAt: string | null;
};

export type DriverRoadRoute = {
  geometry: {
    type: 'LineString';
    coordinates: [longitude: number, latitude: number][];
  };
  distanceMeters: number;
  durationSeconds: number;
  trafficDelaySeconds: number;
  departureTime: string;
  arrivalTime: string;
  trafficMode: 'live';
};

export type DriverVehiclePosition = {
  latitude: number;
  longitude: number;
  recordedAt: string;
  isStale: boolean;
  source: 'GNSS' | 'CELLULAR_LBS' | 'SIMULATED_TEST';
};

export type DriverRoutePlace = {
  name: string;
  latitude: number;
  longitude: number;
};

export type DriverTripRoute = {
  phase: 'TO_PICKUP' | 'TO_DESTINATION' | 'ARRIVED' | 'COMPLETED';
  executionStatus: DriverTripExecutionStatus;
  routeStatus: 'AVAILABLE' | 'POSITION_UNAVAILABLE' | 'TEMPORARILY_UNAVAILABLE' | 'NOT_ACTIVE';
  positionState: 'CURRENT' | 'STALE' | 'UNAVAILABLE';
  positionRecordedAt: string | null;
  positionAgeSeconds: number | null;
  routeBasis: 'CURRENT_VEHICLE_POSITION' | 'LAST_KNOWN_VEHICLE_POSITION' | 'PICKUP' | null;
  vehiclePosition: DriverVehiclePosition | null;
  pickup: DriverRoutePlace;
  destination: DriverRoutePlace;
  route: DriverRoadRoute | null;
};

export type DriverTrip = {
  id: string;
  requestNumber: string;
  requestType: string;
  requestTypeLabel: string;
  requestCategory: string | null;
  requestCategoryLabel: string | null;
  priority: string;
  priorityLabel: string;
  status: string;
  statusLabel: string;
  isAccepted: boolean;
  acceptedAt: string | null;
  assignmentConfirmedAt: string;
  scheduledPickupAt: string;
  estimatedDurationMinutes: number;
  passengerCount: number;
  luggageCount: number;
  pickup: DriverTripPlace;
  destination: DriverTripPlace;
  vehicle: DriverTripVehicle;
  handlingInstructions: string;
  loadDescription: string;
  loadQuantity: number | null;
  estimatedWeightKg: string | null;
  temperatureRequirement: string;
  flightContext?: DriverTripFlightContext | null;
  capacityCompatibility?: { status: string; message: string };
  execution: DriverTripExecution;
};
