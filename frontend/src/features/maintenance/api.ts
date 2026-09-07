import { api } from "../../services/api";

export type MaintenanceModelInfo = {
  model_name: string; model_version: string; contract_version: string;
  features: string[]; decision_threshold: number; deployment_state: string;
  production_ready: boolean; score_semantics: string;
};
export type MaintenanceReadiness = {
  deployment_state: string; production_ready: boolean; direct_obd_feed_allowed: boolean;
  unit_scaling_verified: boolean; vehicle_compatibility_verified: boolean;
  blocking_reason: string; required_features: string[]; source_modes: string[];
};
export const getMaintenanceModelInfo = (signal?: AbortSignal) => api<MaintenanceModelInfo>("/api/v1/analytics/maintenance/model-info/", { signal });
export const getMaintenanceReadiness = (signal?: AbortSignal) => api<MaintenanceReadiness>("/api/v1/analytics/maintenance/readiness/", { signal });

export const maintenanceStatuses = ["OPEN", "SCHEDULED", "IN_PROGRESS", "COMPLETED", "CANCELLED"] as const;
export type MaintenanceStatus = typeof maintenanceStatuses[number];
export type MaintenanceRecord = {
  id: number; vehicle: { id: number; device_id: string; display_name: string; plate_number: string };
  inspection: null | { id: number; inspection_date: string; inspection_type: string; result: string };
  source: "MANUAL" | "INSPECTION"; status: MaintenanceStatus; title: string; notes: string;
  scheduled_at: string | null; started_at: string | null; completed_at: string | null;
  created_by: number; created_by_name: string; allowed_transitions: MaintenanceStatus[];
  created_at: string; updated_at: string;
};
export type MaintenancePage = { count: number; next: string | null; previous: string | null; can_manage: boolean; results: MaintenanceRecord[] };
export const getMaintenanceRecords = (vehicle = "", signal?: AbortSignal) => api<MaintenancePage>(`/api/v1/vehicles/maintenance/${vehicle ? `?vehicle=${encodeURIComponent(vehicle)}` : ""}`, { signal });
export const createMaintenanceRecord = (body: { vehicle_device_id: string; title: string; notes: string; inspection_id?: number }) => api<MaintenanceRecord>("/api/v1/vehicles/maintenance/", { method: "POST", body: JSON.stringify(body) });
export const transitionMaintenanceRecord = (id: number, body: { status: MaintenanceStatus; scheduled_at?: string }) => api<MaintenanceRecord>(`/api/v1/vehicles/maintenance/${id}/transition/`, { method: "POST", body: JSON.stringify(body) });
