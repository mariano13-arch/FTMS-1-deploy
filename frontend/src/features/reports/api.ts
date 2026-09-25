import { api, apiBaseUrl, ApiError } from "../../services/api";

export type ReportFilterValues = {
  date_from: string;
  date_to: string;
  source?: string;
  request_type?: string;
  status?: string;
  priority?: string;
  page?: number;
  page_size?: number;
};

export type ReportChoice = { value: string | number; label: string };
export type ReportBreakdown = ReportChoice & { count: number };
export type TransportReport = {
  meta: {
    title: string;
    generated_at: string;
    generated_by: string;
    timezone: string;
    date_basis: string;
    date_from: string;
    date_to: string;
  };
  summary: {
    requests_created: number;
    approved: number;
    rejected: number;
    cancelled: number;
    currently_dispatch_ready: number;
  };
  trend: { date: string; count: number }[];
  breakdowns: { by_source: ReportBreakdown[]; by_status: ReportBreakdown[] };
  choices: {
    sources: ReportChoice[];
    request_types: ReportChoice[];
    statuses: ReportChoice[];
    priorities: ReportChoice[];
  };
  details: {
    count: number;
    page: number;
    page_size: number;
    total_pages: number;
    results: Array<{
      id: string;
      request_number: string;
      source_label: string;
      request_type_label: string;
      request_category_label: string | null;
      priority_label: string;
      status_label: string;
      scheduled_pickup_at: string;
      created_at: string;
    }>;
  };
};

function queryString(filters: ReportFilterValues, includePagination = true) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== "" && (includePagination || !(key === "page_size" || key.endsWith("_page") || key === "page"))) {
      params.set(key, String(value));
    }
  });
  return params.toString();
}

export function fetchTransportReport(filters: ReportFilterValues) {
  return api<TransportReport>(`/api/v1/reports/transport-requests/?${queryString(filters)}`);
}

async function downloadTransportReportExport(
  filters: ReportFilterValues,
  format: "csv" | "xlsx" | "pdf",
  fallbackFilename: string,
) {
  const response = await fetch(
    `${apiBaseUrl}/api/v1/reports/transport-requests/${format}/?${queryString(filters, false)}`,
    { credentials: "include" },
  );
  if (!response.ok) throw new ApiError(response.status, await response.json().catch(() => null));
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] ?? fallbackFilename;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export const downloadTransportReportCsv = (filters: ReportFilterValues) =>
  downloadTransportReportExport(filters, "csv", "transport-requests.csv");
export const downloadTransportReportXlsx = (filters: ReportFilterValues) =>
  downloadTransportReportExport(filters, "xlsx", "transport-requests.xlsx");
export const downloadTransportReportPdf = (filters: ReportFilterValues) =>
  downloadTransportReportExport(filters, "pdf", "transport-requests.pdf");

export type DispatchReportFilters = ReportFilterValues & { vehicle?: string; driver?: string; execution_status?: string; selection_mode?: string; search?: string };
export type DispatchReportRow = {
  id: number; request_id: string; request_number: string; request_type_label: string;
  driver: { id: number; code: string; name: string }; vehicle: { id: number; name: string; identifier: string; plate_number: string };
  selection_mode: string; selection_mode_label: string; manual_override_reason: string;
  execution_status: string; execution_status_label: string; confirmed_at: string; confirmed_by: string;
  accepted_at: string | null; execution_started_at: string | null; pickup_arrived_at: string | null;
  pickup_departed_at: string | null; destination_arrived_at: string | null; completed_at: string | null;
  durations: Record<string, number | null>;
};
export type DispatchTripReport = {
  meta: TransportReport["meta"];
  summary: { assignments_confirmed: number; driver_acceptances: number; trips_in_progress: number; completed_trips: number; average_execution_duration_seconds: number | null };
  trend: TransportReport["trend"];
  breakdowns: { by_execution_status: ReportBreakdown[]; by_selection_mode: ReportBreakdown[] };
  choices: { vehicles: ReportChoice[]; drivers: ReportChoice[]; execution_statuses: ReportChoice[]; selection_modes: ReportChoice[] };
  details: { count: number; page: number; page_size: number; total_pages: number; results: DispatchReportRow[] };
};

export function fetchDispatchTripReport(filters: DispatchReportFilters) {
  return api<DispatchTripReport>(`/api/v1/reports/dispatch-trips/?${queryString(filters)}`);
}

export async function downloadDispatchTripCsv(filters: DispatchReportFilters) {
  const response = await fetch(`${apiBaseUrl}/api/v1/reports/dispatch-trips/csv/?${queryString(filters, false)}`, { credentials: "include" });
  if (!response.ok) throw new ApiError(response.status, await response.json().catch(() => null));
  const blob = await response.blob();
  const url = URL.createObjectURL(blob); const anchor = document.createElement("a");
  anchor.href = url; anchor.download = "dispatch-trips.csv"; anchor.click(); URL.revokeObjectURL(url);
}

export type FleetAssignmentFilters = ReportFilterValues & {
  vehicle?: string; vehicle_type?: string; vehicle_active?: string; vehicle_search?: string;
  driver?: string; employment_status?: string; driver_search?: string;
  vehicle_page?: number; driver_page?: number;
};
export type CompactAssignment = { id: number; request_id: string; request_number: string; vehicle: { id: number; name: string; identifier: string }; driver: { id: number; code: string; name: string }; selection_mode_label: string; execution_status: string; execution_status_label: string; confirmed_at: string };
export type VehicleAssignmentRow = { id: number; name: string; identifier: string; plate_number: string; vehicle_type: string; vehicle_type_label: string; fuel_type: string; fuel_type_label: string; fuel_grade: string; fuel_grade_label: string; is_active: boolean; passenger_capacity: number | null; payload_capacity_kg: string | null; assignments: number; completed_trips: number; current_assignment: CompactAssignment | null; latest_assignment: CompactAssignment | null };
export type DriverAssignmentRow = { id: number; name: string; driver_code: string; employment_status: string; employment_status_label: string; assignments: number; completed_trips: number; current_assignment: CompactAssignment | null; latest_assignment: CompactAssignment | null };
type SummaryPage<T> = { count: number; page: number; page_size: number; total_pages: number; results: T[] };
export type FleetAssignmentReport = {
  meta: TransportReport["meta"];
  summary: { active_vehicles: number; active_drivers: number; assignments_confirmed: number; completed_trips: number; currently_assigned_vehicles: number };
  trend: TransportReport["trend"];
  breakdowns: { by_vehicle: ReportBreakdown[]; by_driver: ReportBreakdown[]; by_vehicle_type: ReportBreakdown[] };
  choices: { vehicles: ReportChoice[]; vehicle_types: ReportChoice[]; drivers: ReportChoice[]; employment_statuses: ReportChoice[] };
  vehicles: SummaryPage<VehicleAssignmentRow>;
  drivers: SummaryPage<DriverAssignmentRow>;
};
export function fetchFleetAssignmentReport(filters: FleetAssignmentFilters) { return api<FleetAssignmentReport>(`/api/v1/reports/fleet-assignments/?${queryString(filters)}`); }
export async function downloadFleetAssignmentCsv(kind: "vehicles" | "drivers", filters: FleetAssignmentFilters) { const response = await fetch(`${apiBaseUrl}/api/v1/reports/fleet-assignments/${kind}/csv/?${queryString(filters, false)}`, { credentials: "include" }); if (!response.ok) throw new ApiError(response.status, await response.json().catch(() => null)); const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `fleet-assignments-${kind}.csv`; link.click(); URL.revokeObjectURL(url); }

export type SafetyGeofenceFilters = ReportFilterValues & { safety_event_type?: string; safety_vehicle?: string; safety_driver?: string; position_source?: string; obd_source?: string; safety_search?: string; geofence_event_type?: string; category?: string; geofence?: string; geofence_vehicle?: string; geofence_position_source?: string; geofence_search?: string; sos_status?: string; sos_vehicle?: string; safety_page?: number; geofence_page?: number; sos_page?: number };
export type SafetyEventRow = { id: number; event_id: string; occurred_at: string; event_type: string; event_type_label: string; driver: { id: number; code: string; name: string }; assignment: { id: number; request_number: string }; vehicle: { id: number; name: string; identifier: string }; device_id: string; position_source: string; position_source_label: string; obd_source: string | null; obd_source_label: string | null; provenance: "OPERATIONAL" };
export type GeofenceEventRow = { id: number; occurred_at: string; created_at: string; event_type: string; event_type_label: string; display_classification: string; geofence: { id: string; name: string; category: string; category_label: string; shape_type: string; shape_type_label: string; radius_meters: number | null }; vehicle: { id: number; name: string; identifier: string }; latitude: number; longitude: number; telemetry: { id: number; event_id: string; recorded_at: string; position_source: string; position_source_label: string; obd_source: string | null; obd_source_label: string | null } };
export type SosEventRow = { id: number; status: string; status_label: string; source: string; source_label: string; activated_at: string; cleared_at: string | null; device: { id: number; device_id: string }; vehicle: { id: number; name: string; identifier: string } | null; driver: { id: number; code: string; name: string } | null; location: null; location_label: string };
export type SafetyGeofenceReport = { meta: TransportReport["meta"] & { safety_date_basis: string; geofence_date_basis: string; sos_date_basis: string }; summary: { safety_events: number; harsh_braking: number; harsh_acceleration: number; sharp_turns: number; restricted_entries: number; geofence_activity: number; sos_activations: number; active_sos: number }; safety_trend: TransportReport["trend"]; geofence_trend: { date: string; enter: number; exit: number; count: number }[]; breakdowns: { safety_types: ReportBreakdown[]; position_sources: ReportBreakdown[]; geofence_events: ReportBreakdown[]; restricted_by_geofence: ReportBreakdown[] }; choices: { safety_event_types: ReportChoice[]; vehicles: ReportChoice[]; drivers: ReportChoice[]; position_sources: ReportChoice[]; obd_sources: ReportChoice[]; geofence_event_types: ReportChoice[]; categories: ReportChoice[]; geofences: ReportChoice[]; sos_statuses: ReportChoice[] }; safety_events: SummaryPage<SafetyEventRow>; geofence_activity: SummaryPage<GeofenceEventRow>; sos_activity: SummaryPage<SosEventRow> };
export function fetchSafetyGeofenceReport(filters: SafetyGeofenceFilters) { return api<SafetyGeofenceReport>(`/api/v1/reports/safety-geofence/?${queryString(filters)}`); }
export async function downloadSafetyGeofenceCsv(kind: "safety" | "geofence" | "sos", filters: SafetyGeofenceFilters) { const response = await fetch(`${apiBaseUrl}/api/v1/reports/safety-geofence/${kind}/csv/?${queryString(filters, false)}`, { credentials: "include" }); if (!response.ok) throw new ApiError(response.status, await response.json().catch(() => null)); const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `${kind}-activity.csv`; link.click(); URL.revokeObjectURL(url); }

export type DeviceTelemetryFilters = ReportFilterValues & { registry_status?: string; binding_state?: string; telemetry_state?: string; position_source?: string; obd_source?: string; vehicle?: string; device_search?: string; binding_device?: string; binding_vehicle?: string; binding_history_state?: string; binding_search?: string; device_page?: number; binding_page?: number };
export type DeviceSummaryRow = { id: number; device_id: string; registration_status: string; registration_status_label: string; registered_at: string; binding_state: string; binding_state_label: string; current_binding: { id: number; paired_at: string; paired_by: string | null; vehicle: { id: number; name: string; identifier: string } } | null; latest_telemetry: { id: number; recorded_at: string; received_at: string; position_source: string; position_source_label: string; position_accuracy_m: string | null; obd_source: string | null; obd_source_label: string | null; latitude: number; longitude: number } | null; telemetry_state: string; telemetry_state_label: string; binding_count: number };
export type BindingHistoryRow = { id: number; device: { id: number; device_id: string; registration_status: string; registration_status_label: string }; vehicle: { id: number; name: string; identifier: string }; paired_at: string; unpaired_at: string | null; binding_state: string; binding_state_label: string; paired_by: string | null; unpaired_by: string | null };
export type DeviceTelemetryReport = { meta: TransportReport["meta"] & { telemetry_date_basis: string; binding_date_basis: string; freshness_rule: null }; summary: { registered_devices: number; paired_devices: number; unpaired_devices: number; retired_devices: number; no_telemetry: number }; trend: TransportReport["trend"]; breakdowns: { availability: ReportBreakdown[]; binding_state: ReportBreakdown[]; position_sources: ReportBreakdown[]; obd_sources: ReportBreakdown[] }; choices: { registry_statuses: ReportChoice[]; vehicles: ReportChoice[]; devices: ReportChoice[]; position_sources: ReportChoice[]; obd_sources: ReportChoice[] }; devices: { count: number; page: number; page_size: number; total_pages: number; results: DeviceSummaryRow[] }; bindings: { count: number; page: number; page_size: number; total_pages: number; results: BindingHistoryRow[] } };
export function fetchDeviceTelemetryReport(filters: DeviceTelemetryFilters) { return api<DeviceTelemetryReport>(`/api/v1/reports/device-telemetry/?${queryString(filters)}`); }
export async function downloadDeviceTelemetryCsv(kind: "devices" | "bindings", filters: DeviceTelemetryFilters) { const response = await fetch(`${apiBaseUrl}/api/v1/reports/device-telemetry/${kind}/csv/?${queryString(filters, false)}`, { credentials: "include" }); if (!response.ok) throw new ApiError(response.status, await response.json().catch(() => null)); const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `device-telemetry-${kind}.csv`; link.click(); URL.revokeObjectURL(url); }

export type InspectionMaintenanceFilters = ReportFilterValues & { inspection_vehicle?: string; inspection_type?: string; inspection_result?: string; inspection_search?: string; maintenance_vehicle?: string; maintenance_status?: string; maintenance_source?: string; inspection_page?: number; maintenance_page?: number };
export type InspectionRow = { id: number; inspection_date: string; inspection_type_label: string; result_label: string; vehicle: { name: string; identifier: string }; inspector: string; odometer_km: number | null; fuel_level_percent: number | null; checklist: Record<string, { value: string; label: string }>; exception_count: number; issues_found: string; notes: string; related_maintenance: { id: number; title: string; status_label: string }[] };
export type MaintenanceRow = { id: number; created_at: string; vehicle: { name: string; identifier: string }; title: string; source_label: string; status_label: string; scheduled_at: string | null; started_at: string | null; completed_at: string | null; notes: string; creator: string; linked_inspection: { inspection_date: string; type_label: string; result_label: string } | null };
export type InspectionMaintenanceReport = { meta: TransportReport["meta"]; summary: { inspections: number; passed: number; needs_attention: number; failed: number; active_maintenance: number; completed_maintenance: number }; trend: TransportReport["trend"]; breakdowns: { inspection_results: ReportBreakdown[]; checklist_attention: ReportBreakdown[]; maintenance_status: ReportBreakdown[]; maintenance_source: ReportBreakdown[] }; choices: { vehicles: ReportChoice[]; inspection_types: ReportChoice[]; inspection_results: ReportChoice[]; maintenance_statuses: ReportChoice[]; maintenance_sources: ReportChoice[] }; inspections: { count: number; page: number; page_size: number; total_pages: number; results: InspectionRow[] }; maintenance: { count: number; page: number; page_size: number; total_pages: number; results: MaintenanceRow[] } };
export function fetchInspectionMaintenanceReport(filters: InspectionMaintenanceFilters) { return api<InspectionMaintenanceReport>(`/api/v1/reports/inspection-maintenance/?${queryString(filters)}`); }
export async function downloadInspectionMaintenanceCsv(kind: "inspections" | "maintenance", filters: InspectionMaintenanceFilters) { const response = await fetch(`${apiBaseUrl}/api/v1/reports/inspection-maintenance/${kind}/csv/?${queryString(filters, false)}`, { credentials: "include" }); if (!response.ok) throw new ApiError(response.status, await response.json().catch(() => null)); const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `${kind}.csv`; link.click(); URL.revokeObjectURL(url); }

export type FuelReferenceFilters = ReportFilterValues & { vehicle?: string; prediction_source?: string; fuel_type?: string; fuel_grade?: string; price_source?: string; provider?: string; prediction_page?: number; baseline_page?: number; price_page?: number };
export type FuelReferenceReport = {
  meta: TransportReport["meta"] & { prediction_date_basis: string; price_date_basis: string };
  summary: { eligible_predictions: number; vehicles_with_reference_baselines: number; fuel_grades_with_current_reference_price: number; latest_eligible_prediction_at: string | null };
  choices: { vehicles: ReportChoice[]; prediction_sources: ReportChoice[]; fuel_types: ReportChoice[]; fuel_grades: ReportChoice[]; price_sources: ReportChoice[]; providers: ReportChoice[] };
  predictions: SummaryPage<{ id: number; vehicle: { id: number; name: string; identifier: string }; estimated_fuel_lph: string; input_timestamp: string; predicted_at: string; model_name: string; model_version: string; source_mode: string; provenance_label: string; operational_source: boolean }>;
  baselines: SummaryPage<{ id: number; vehicle: { id: number; name: string; identifier: string }; fuel_type_label: string; fuel_grade_label: string; reference_fuel_rate_lph: string; provenance: string; provenance_label: string; basis_version: string; is_active: boolean }>;
  prices: SummaryPage<{ id: number; provider: string; fuel_type_label: string; fuel_grade_label: string; price_per_liter: string; currency: string; source_mode: string; source_mode_label: string; effective_at: string; retrieved_at: string; is_active: boolean; provenance_label: string }>;
};
export function fetchFuelReferenceReport(filters: FuelReferenceFilters) { return api<FuelReferenceReport>(`/api/v1/reports/fuel-reference/?${queryString(filters)}`); }
export async function downloadFuelReferenceCsv(kind: "predictions" | "baselines" | "prices", filters: FuelReferenceFilters) { const response = await fetch(`${apiBaseUrl}/api/v1/reports/fuel-reference/${kind}/csv/?${queryString(filters, false)}`, { credentials: "include" }); if (!response.ok) throw new ApiError(response.status, await response.json().catch(() => null)); const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `fuel-reference-${kind}.csv`; link.click(); URL.revokeObjectURL(url); }
