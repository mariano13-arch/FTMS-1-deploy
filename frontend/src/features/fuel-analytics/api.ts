import { api } from "../../services/api";

export type FuelFeatureStatus = "available" | "missing" | "unverified";
export type FuelPredictionStatus = "prediction_available" | "prediction_blocked" | "invalid_input" | "model_unavailable";
export type FuelPredictionResult = {
  status: FuelPredictionStatus;
  model_name: string;
  model_version: string;
  target: "estimated_fuel_lph";
  estimated_fuel_lph: number | null;
  input_timestamp: string | null;
  inputs: Record<string, number>;
  missing_features: string[];
  invalid_features: string[];
  unexpected_features: string[];
  is_estimate: true;
  history_persisted?: boolean;
};
export type FuelModelInfo = {
  model_name: string;
  model_version: string;
  model_type: string;
  model_role: string;
  target: "estimated_fuel_lph";
  features: string[];
  excluded_leakage_features: string[];
  metrics: { mae_lph: number; rmse_lph: number; r2: number };
  hyperparameters: Record<string, number>;
  prediction_semantics: string;
  accuracy_note: string;
  availability: "available" | "unavailable";
  is_estimate: true;
};
export type FuelReadiness = {
  inputs: Array<{ feature: string; status: FuelFeatureStatus; source: string | null; note: string }>;
  latest_telemetry: null | { event_id: string; vehicle_id: number; device_id: string; vehicle_name: string; recorded_at: string };
  latest_operational_result: FuelPredictionResult;
};

export type FuelDashboardRange = "24h" | "7d" | "30d";
export type FuelDashboardVehicleStatus = FuelPredictionStatus | "demo_ready" | "no_telemetry";
export type FuelPredictionInputDetail = {
  feature: string;
  value: number;
  unit: string | null;
  source: "Actual persisted telemetry" | "Demo/Test Input" | "Validated API Input";
};
export type FuelVehicleReadiness = {
  available_count: number;
  required_count: number;
  available_features: string[];
  missing_features: string[];
  unverified_features: string[];
};
export type FuelDashboardVehicle = {
  vehicle_id: number;
  vehicle_name: string;
  plate_number: string;
  device_id: string;
  telemetry_status: "available" | "no_telemetry";
  telemetry_timestamp: string | null;
  latest_estimated_fuel_lph: number | null;
  prediction_status: FuelDashboardVehicleStatus;
  last_prediction_at: string | null;
  prediction_source_mode: string | null;
  prediction_source_label: string | null;
  latest_prediction_input_timestamp: string | null;
  latest_prediction_inputs: FuelPredictionInputDetail[];
  is_demo_prediction: boolean;
  input_readiness: FuelVehicleReadiness;
};
export type FuelDashboard = {
  refreshed_at: string;
  model_availability: "available" | "unavailable";
  demo_data_present: boolean;
  demo_data_note: string | null;
  filters: {
    range: FuelDashboardRange;
    vehicle_id: number | null;
    selected_vehicle: null | { vehicle_id: number; vehicle_name: string; plate_number: string };
    trend_aggregation: string;
  };
  summary: {
    vehicle_count: number;
    prediction_ready_count: number;
    demo_ready_count: number;
    prediction_blocked_count: number;
    average_estimated_fuel_lph: number | null;
    demo_average_estimated_fuel_lph: number | null;
  };
  trend: Array<{ timestamp: string; estimated_fuel_lph: number }>;
  vehicle_comparison: Array<{
    vehicle_id: number;
    vehicle_name: string;
    plate_number: string;
    estimated_fuel_lph: number;
    predicted_at: string;
    source_mode: string;
    source_label: string;
    is_demo_prediction: boolean;
  }>;
  readiness_breakdown: { ready: number; demo_ready: number; blocked: number; no_telemetry: number; model_unavailable: number };
  vehicle_options: Array<{ vehicle_id: number; vehicle_name: string; plate_number: string; device_id: string }>;
  vehicle_pagination: {
    page: number;
    page_size: number;
    total_count: number;
    total_pages: number;
    start: number;
    end: number;
  };
  vehicles: FuelDashboardVehicle[];
};

export const getFuelModelInfo = (signal?: AbortSignal) => api<FuelModelInfo>("/api/v1/analytics/fuel/model-info/", { signal });
export const getFuelReadiness = (signal?: AbortSignal) => api<FuelReadiness>("/api/v1/analytics/fuel/readiness/", { signal });
export const getFuelDashboard = (range: FuelDashboardRange, vehicleId: number | null, search: string, signal?: AbortSignal) => {
  const query = new URLSearchParams({ range, page: "1", page_size: "500" });
  if (vehicleId !== null) query.set("vehicle", String(vehicleId));
  if (search.trim()) query.set("search", search.trim());
  return api<FuelDashboard>(`/api/v1/analytics/fuel/dashboard/?${query}`, { signal });
};
