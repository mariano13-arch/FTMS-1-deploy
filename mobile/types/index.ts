/** Shared mobile domain types will be added when the Django mobile API contract is approved. */
export type PlannedMobileFeature =
  | 'AUTH'
  | 'TRIPS'
  | 'INSPECTION'
  | 'INCIDENTS'
  | 'COMPLETION'
  | 'PROFILE';

export type { DriverIdentity } from './driverAuth';
export type {
  DriverTrip,
  DriverTripExecution,
  DriverTripExecutionAction,
  DriverTripExecutionStatus,
  DriverTripPlace,
  DriverTripRoute,
  DriverTripVehicle,
  DriverVehiclePosition,
} from './driverTrips';
