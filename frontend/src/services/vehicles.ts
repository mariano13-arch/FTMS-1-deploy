import { api } from "./api";

export const vehicleTypes = ["SEDAN","SUV","VAN","SHUTTLE_BUS","SERVICE_TRUCK","MOTORCYCLE","OTHER"] as const;
export const fuelTypes = ["GASOLINE", "DIESEL"] as const;
export const fuelGrades = ["UNLEADED_91", "PREMIUM_95", "PREMIUM_97", "REGULAR_DIESEL", "PREMIUM_DIESEL"] as const;
export type FuelType = typeof fuelTypes[number] | "";
export type FuelGrade = typeof fuelGrades[number] | "";
export const fuelGradesByType: Record<Exclude<FuelType, "">, readonly FuelGrade[]> = {
  GASOLINE: ["UNLEADED_91", "PREMIUM_95", "PREMIUM_97"],
  DIESEL: ["REGULAR_DIESEL", "PREMIUM_DIESEL"],
};
export const transmissionTypes = ["MANUAL", "AUTOMATIC", "CVT", "OTHER"] as const;
export const ownershipTypes = ["COMPANY_OWNED", "LEASED", "RENTED", "OTHER"] as const;
export const documentTypes = ["OFFICIAL_RECEIPT", "CERTIFICATE_OF_REGISTRATION", "INSURANCE", "PURCHASE_ORDER", "SALES_INVOICE", "WARRANTY", "LEASE_AGREEMENT", "EMISSION_CERTIFICATE", "PMVIC_CERTIFICATE", "VEHICLE_PHOTO", "OTHER"] as const;
export type VehicleType = typeof vehicleTypes[number];
export type Vehicle = {
  id?: number; device_id: string; plate_number: string; display_name: string;
  vehicle_type: VehicleType; manufacturer: string; model: string;
  model_year: number | null; passenger_capacity: number | null;
  payload_capacity_kg: string | null; gvwr_kg: string | null;
  vin: string; engine_number: string; chassis_number: string; color: string;
  fuel_type: FuelType; fuel_grade: FuelGrade;
  transmission_type: typeof transmissionTypes[number] | "";
  ownership_type: typeof ownershipTypes[number] | ""; supplier_name: string;
  purchase_order_number: string; acquisition_date: string | null; purchase_price: string | null;
  purchase_currency: string; warranty_expiry_date: string | null;
  registration_expiry_date: string | null; insurance_expiry_date: string | null;
  is_active: boolean; created_at: string; updated_at: string;
  photo_url: string | null;
  latest_inspection: VehicleInspectionSummary | null; document_count: number;
  document_health: "CURRENT" | "EXPIRING_SOON" | "EXPIRED" | "INCOMPLETE";
};
export const inspectionTypes = ["PRE_TRIP", "POST_TRIP", "PERIODIC"] as const;
export const inspectionResults = ["PASSED", "NEEDS_ATTENTION", "FAILED"] as const;
export const inspectionConditions = ["OK", "NEEDS_ATTENTION", "NOT_CHECKED"] as const;
export type VehicleInspectionSummary = { id: number; inspection_date: string; inspection_type: typeof inspectionTypes[number]; result: typeof inspectionResults[number] };
export type VehicleInspection = VehicleInspectionSummary & {
  vehicle: number; odometer_km: number | null; fuel_level_percent: number | null;
  exterior_condition: typeof inspectionConditions[number]; interior_condition: typeof inspectionConditions[number];
  tires_condition: typeof inspectionConditions[number]; lights_condition: typeof inspectionConditions[number];
  brakes_condition: typeof inspectionConditions[number]; fluids_condition: typeof inspectionConditions[number];
  safety_equipment_condition: typeof inspectionConditions[number]; notes: string; issues_found: string;
  inspected_by: number; inspector_name: string; created_at: string; updated_at: string;
};
export type InspectionPage = { count: number; next: string | null; previous: string | null; results: VehicleInspection[] };
export type VehicleDocument = {
  id: number; vehicle: number; document_type: typeof documentTypes[number]; title: string;
  reference_number: string; issuer_name: string; issued_date: string | null;
  effective_date: string | null; expiry_date: string | null;
  file_name: string; download_url: string; uploaded_by: number; uploaded_by_name: string;
  created_at: string; updated_at: string;
};
export type DocumentPage = { count: number; next: string | null; previous: string | null; results: VehicleDocument[] };
export type VehiclePage = {
  count: number; next: string | null; previous: string | null; results: Vehicle[];
};
export const getVehicles = (query: string, signal?: AbortSignal) =>
  api<VehiclePage>(`/api/v1/vehicles/${query ? `?${query}` : ""}`, { signal });
export const getVehicle = (id: string, signal?: AbortSignal) =>
  api<Vehicle>(`/api/v1/vehicles/${encodeURIComponent(id)}/`, { signal });
export const createVehicle = (body: FormData, signal?: AbortSignal) =>
  api<Vehicle>("/api/v1/vehicles/", { method: "POST", body, signal });
export const editVehicle = (id: string, body: FormData, signal?: AbortSignal) =>
  api<Vehicle>(`/api/v1/vehicles/${encodeURIComponent(id)}/`, { method: "PATCH", body, signal });
export const changeVehicleStatus = (id: string, active: boolean, signal?: AbortSignal) =>
  api<Vehicle>(`/api/v1/vehicles/${encodeURIComponent(id)}/${active ? "reactivate" : "deactivate"}/`, { method: "POST", body: "{}", signal });
export const getVehicleInspections = (id: string, query = "", signal?: AbortSignal) =>
  api<InspectionPage>(`/api/v1/vehicles/${encodeURIComponent(id)}/inspections/${query ? `?${query}` : ""}`, { signal });
export const createVehicleInspection = (id: string, body: unknown, signal?: AbortSignal) =>
  api<VehicleInspection>(`/api/v1/vehicles/${encodeURIComponent(id)}/inspections/`, { method: "POST", body: JSON.stringify(body), signal });
export const getVehicleDocuments = (id: string, query = "", signal?: AbortSignal) =>
  api<DocumentPage>(`/api/v1/vehicles/${encodeURIComponent(id)}/documents/${query ? `?${query}` : ""}`, { signal });
export const createVehicleDocument = (id: string, body: FormData, signal?: AbortSignal) =>
  api<VehicleDocument>(`/api/v1/vehicles/${encodeURIComponent(id)}/documents/`, { method: "POST", body, signal });
