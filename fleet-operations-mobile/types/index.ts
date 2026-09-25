export type StaffRole = 'FLEET_ADMIN' | 'FLEET_MANAGER' | 'FLEET_STAFF';

export type StaffIdentity = {
  id: number;
  username: string;
  displayName: string;
  role: StaffRole;
};

export type TelemetryDeviceSummary = {
  deviceId: string;
  registrationStatus: string;
};

export type Vehicle = {
  id: number;
  compatibilityDeviceId: string;
  displayName: string;
  plateNumber: string;
  vehicleType: string;
  manufacturer: string;
  model: string;
  isActive: boolean;
  currentTelemetryDevice: TelemetryDeviceSummary | null;
  latestInspection: VehicleInspectionSummary | null;
};

export type InspectionChoice = {
  value: string;
  label: string;
};

export type InspectionChecklistItem = {
  field: string;
  label: string;
  required: boolean;
  choices: InspectionChoice[];
};

export type InspectionDefinition = {
  inspectionTypes: InspectionChoice[];
  results: InspectionChoice[];
  checklist: InspectionChecklistItem[];
};

export type VehicleInspectionSummary = {
  id: number;
  inspectionDate: string;
  inspectionType: string;
  result: string;
};

export type VehicleInspection = VehicleInspectionSummary & {
  vehicleId: number;
  odometerKm: number | null;
  fuelLevelPercent: number | null;
  conditions: Record<string, string>;
  notes: string;
  issuesFound: string;
  inspectorId: number;
  inspectorName: string;
  createdAt: string;
  updatedAt: string;
};

export type InspectionSubmission = {
  inspection_type: string;
  result: string;
  odometer_km?: number;
  fuel_level_percent?: number;
  notes: string;
  issues_found: string;
} & Record<string, string | number | undefined>;

export type TelemetryDevice = TelemetryDeviceSummary & {
  isPaired: boolean;
  currentVehicle: null | {
    vehicleId: number;
    plateNumber: string;
    displayName: string;
    compatibilityDeviceId: string;
  };
};
