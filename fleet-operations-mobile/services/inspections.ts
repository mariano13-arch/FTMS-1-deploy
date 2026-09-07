import { api } from '@/services/api';
import type {
  InspectionDefinition,
  InspectionSubmission,
  VehicleInspection,
} from '@/types';

type ChoicePayload = { value: string; label: string };
type DefinitionPayload = {
  inspection_types: ChoicePayload[];
  results: ChoicePayload[];
  checklist: Array<{
    field: string;
    label: string;
    required: boolean;
    choices: ChoicePayload[];
  }>;
};

type InspectionPayload = {
  id: number;
  vehicle: number;
  inspection_date: string;
  inspection_type: string;
  result: string;
  odometer_km: number | null;
  fuel_level_percent: number | null;
  exterior_condition: string;
  interior_condition: string;
  tires_condition: string;
  lights_condition: string;
  brakes_condition: string;
  fluids_condition: string;
  safety_equipment_condition: string;
  notes: string;
  issues_found: string;
  inspected_by: number;
  inspector_name: string;
  created_at: string;
  updated_at: string;
};

type InspectionPagePayload = {
  count: number;
  next: string | null;
  previous: string | null;
  results: InspectionPayload[];
};

const conditionFields = [
  'exterior_condition',
  'interior_condition',
  'tires_condition',
  'lights_condition',
  'brakes_condition',
  'fluids_condition',
  'safety_equipment_condition',
] as const;

function mapInspection(payload: InspectionPayload): VehicleInspection {
  return {
    id: payload.id,
    vehicleId: payload.vehicle,
    inspectionDate: payload.inspection_date,
    inspectionType: payload.inspection_type,
    result: payload.result,
    odometerKm: payload.odometer_km,
    fuelLevelPercent: payload.fuel_level_percent,
    conditions: Object.fromEntries(conditionFields.map((field) => [field, payload[field]])),
    notes: payload.notes,
    issuesFound: payload.issues_found,
    inspectorId: payload.inspected_by,
    inspectorName: payload.inspector_name,
    createdAt: payload.created_at,
    updatedAt: payload.updated_at,
  };
}

export async function getInspectionDefinition(signal?: AbortSignal): Promise<InspectionDefinition> {
  const payload = await api<DefinitionPayload>('/api/v1/vehicles/inspection-definition/', { signal });
  return {
    inspectionTypes: payload.inspection_types,
    results: payload.results,
    checklist: payload.checklist,
  };
}

export async function getInspectionHistory(
  vehicleDeviceId: string,
  signal?: AbortSignal,
): Promise<VehicleInspection[]> {
  let path: string | null =
    `/api/v1/vehicles/${encodeURIComponent(vehicleDeviceId)}/inspections/?page_size=50`;
  const inspections: VehicleInspection[] = [];
  while (path) {
    const payload: InspectionPagePayload = await api<InspectionPagePayload>(path, { signal });
    inspections.push(...payload.results.map(mapInspection));
    path = payload.next;
  }
  return inspections;
}

export async function getInspection(
  vehicleDeviceId: string,
  inspectionId: number,
  signal?: AbortSignal,
): Promise<VehicleInspection> {
  const payload = await api<InspectionPayload>(
    `/api/v1/vehicles/${encodeURIComponent(vehicleDeviceId)}/inspections/${inspectionId}/`,
    { signal },
  );
  return mapInspection(payload);
}

export async function submitInspection(
  vehicleDeviceId: string,
  submission: InspectionSubmission,
  idempotencyKey: string,
): Promise<VehicleInspection> {
  const payload = await api<InspectionPayload>(
    `/api/v1/vehicles/${encodeURIComponent(vehicleDeviceId)}/inspections/`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify(submission),
    },
  );
  return mapInspection(payload);
}
