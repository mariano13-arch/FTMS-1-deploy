import { api } from "./api";

export const vehicleTypes = ["SEDAN","SUV","VAN","SHUTTLE_BUS","SERVICE_TRUCK","MOTORCYCLE","OTHER"] as const;
export type VehicleType = typeof vehicleTypes[number];
export type Vehicle = {
  device_id: string; plate_number: string; display_name: string;
  vehicle_type: VehicleType; manufacturer: string; model: string;
  model_year: number | null; passenger_capacity: number | null;
  is_active: boolean; created_at: string; updated_at: string;
};
export type VehiclePage = {
  count: number; next: string | null; previous: string | null; results: Vehicle[];
};
export const getVehicles = (query: string, signal?: AbortSignal) =>
  api<VehiclePage>(`/api/v1/vehicles/${query ? `?${query}` : ""}`, { signal });
export const getVehicle = (id: string, signal?: AbortSignal) =>
  api<Vehicle>(`/api/v1/vehicles/${encodeURIComponent(id)}/`, { signal });
export const createVehicle = (body: unknown, signal?: AbortSignal) =>
  api<Vehicle>("/api/v1/vehicles/", { method: "POST", body: JSON.stringify(body), signal });
export const editVehicle = (id: string, body: unknown, signal?: AbortSignal) =>
  api<Vehicle>(`/api/v1/vehicles/${encodeURIComponent(id)}/`, { method: "PATCH", body: JSON.stringify(body), signal });
export const changeVehicleStatus = (id: string, active: boolean, signal?: AbortSignal) =>
  api<Vehicle>(`/api/v1/vehicles/${encodeURIComponent(id)}/${active ? "reactivate" : "deactivate"}/`, { method: "POST", body: "{}", signal });
