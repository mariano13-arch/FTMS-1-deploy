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
