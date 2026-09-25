import { api } from "../../services/api";

export type DashboardValue = {
  value: string;
  label: string;
  count: number;
};

export type DashboardRecent = {
  id: number;
  label: string;
  detail: string;
  occurred_at: string;
  provenance?: string;
  location?: null;
};

export type DashboardWidget = {
  scope: string;
  classification: string;
  provenance: string;
  description: string;
  module_url: string;
  total: number;
  values: DashboardValue[];
  secondary?: DashboardValue[];
  recent?: DashboardRecent[];
};

export type DashboardSummary = {
  generated_at: string;
  request_status: DashboardWidget;
  dispatch_queue: DashboardWidget;
  trip_status: DashboardWidget;
  completed_trips: DashboardWidget;
  fleet_state: DashboardWidget;
  driver_state: DashboardWidget;
  inspection_results: DashboardWidget;
  maintenance_activity: DashboardWidget;
  safety_events: DashboardWidget;
  geofence_activity: DashboardWidget;
  device_telemetry: DashboardWidget;
  fuel_evidence: DashboardWidget;
  sos_activity: DashboardWidget;
};

export const getDashboardSummary = (signal?: AbortSignal) =>
  api<DashboardSummary>("/api/v1/dashboard/summary/", { signal });
