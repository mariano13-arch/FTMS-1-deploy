import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import AlertsPage from "./AlertsPage";

const mocks = vi.hoisted(() => ({
  attention: vi.fn(), safety: vi.fn(), geofence: vi.fn(), vehicles: vi.fn(), geofences: vi.fn(),
}));
vi.mock("./api", () => ({
  getActiveAttention: mocks.attention,
  getSafetyIncidents: mocks.safety,
  getGeofenceActivity: mocks.geofence,
  getAlertVehicleOptions: mocks.vehicles,
  getAlertGeofenceOptions: mocks.geofences,
}));

const summary = { active_attention: 4, safety_events_today: 3, restricted_entries_today: 1, vehicle_device_attention: 2 };
const attention = {
  id: "telemetry:1:stale", condition: "STALE_TELEMETRY", source: "TELEMETRY", current_state: "STALE",
  last_updated_at: "2026-09-21T01:00:00Z",
  vehicle: { id: 1, device_id: "DEV-001", display_name: "Hotel Shuttle", plate_number: "ABC-123" },
  details: { latest_telemetry_at: "2026-09-21T01:00:00Z", telemetry_age_seconds: 600, position_source: "GNSS" },
};
const safety = {
  event_id: "turn-1", event_type: "SHARP_TURN", recorded_at: "2026-09-21T02:00:00Z", received_at: "2026-09-21T02:00:01Z",
  latitude: 14.56, longitude: 121.02, position_source: "SIMULATED_TEST", position_accuracy_m: null,
  speed_kph: null, rpm: null, coolant_c: null, engine_load_pct: null, obd_source: "SIMULATED_TEST",
  vehicle_id: 1, device_id: "SENSOR-001", vehicle_device_id: "DEV-001", vehicle_name: "Hotel Shuttle", plate_number: "ABC-123",
};
const geofence = {
  id: 9, event_type: "ENTER", occurred_at: "2026-09-21T03:00:00Z", latitude: 14.55, longitude: 121.01,
  vehicle_id: 1, device_id: "DEV-001", vehicle_name: "Hotel Shuttle", plate_number: "ABC-123",
  geofence_id: "zone-1", geofence_name: "Restricted Yard", geofence_category: "RESTRICTED", geofence_shape_type: "POLYGON", geofence_radius_meters: null,
  telemetry_event_id: "geo-event-1", telemetry_position_source: "GNSS", telemetry_recorded_at: "2026-09-21T02:59:59Z", created_at: "2026-09-21T03:00:01Z", is_restricted_entry: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.attention.mockResolvedValue({ count: 16, next: "/next", previous: null, results: [attention], summary });
  mocks.safety.mockResolvedValue({ count: 1, next: null, previous: null, results: [safety] });
  mocks.geofence.mockResolvedValue({ count: 1, next: null, previous: null, results: [geofence] });
  mocks.vehicles.mockResolvedValue({ vehicles: [{ vehicle_id: 1, device_id: "DEV-001", display_name: "Hotel Shuttle", plate_number: "ABC-123" }] });
  mocks.geofences.mockResolvedValue({ results: [{ id: "zone-1", name: "Restricted Yard", category: "RESTRICTED" }] });
});

describe("Alerts and Incidents", () => {
  test("renders truthful KPIs, tabs, attention pagination, and no lifecycle UI", async () => {
    render(<AlertsPage />);
    expect(await screen.findByRole("heading", { name: "Alerts & Incidents" })).toBeInTheDocument();
    const kpis = screen.getByLabelText("Alerts and incidents summary");
    expect(within(kpis).getByText("4")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Active Attention" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Safety Incidents" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Geofence Activity" })).toBeInTheDocument();
    expect(await screen.findByText("Showing 1–1 of 16")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(mocks.attention).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }), expect.any(AbortSignal)));
    expect(screen.queryByText(/Severity|Acknowledge|Resolve|Dismiss/i)).not.toBeInTheDocument();
  });

  test("resets the active page on filters and preserves tab-specific state", async () => {
    render(<AlertsPage />); await screen.findByText("Hotel Shuttle");
    expect(screen.queryByLabelText("Attention source")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    expect(screen.getByLabelText("Attention source").closest(".advanced-filter-panel")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.change(screen.getByLabelText("Search attention"), { target: { value: "Hotel" } });
    await waitFor(() => expect(mocks.attention).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, search: "Hotel" }), expect.any(AbortSignal)));
    fireEvent.click(screen.getByRole("tab", { name: "Safety Incidents" }));
    fireEvent.click(screen.getByRole("tab", { name: "Active Attention" }));
    expect(screen.getByLabelText("Search attention")).toHaveValue("Hotel");
  });

  test("shows Sharp Turn and honest simulated provenance in the shared drawer", async () => {
    mocks.safety.mockResolvedValue({ count: 16, next: "/next", previous: null, results: [safety] });
    render(<AlertsPage />); await screen.findByText("Hotel Shuttle");
    fireEvent.click(screen.getByRole("tab", { name: "Safety Incidents" }));
    expect(await screen.findByText("Sharp Turn")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(mocks.safety).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }), expect.any(AbortSignal)));
    expect(await screen.findByText("Sharp Turn")).toBeInTheDocument();
    expect(screen.getByText("Simulated test data")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View" }));
    const drawer = screen.getByRole("dialog", { name: "Alert and incident details" });
    expect(within(drawer).getByText("SIMULATED TEST POSITION DATA")).toBeInTheDocument();
    expect(within(drawer).getAllByText("Unavailable", { selector: "dd" }).length).toBeGreaterThan(0);
  });

  test("identifies restricted entries and opens geofence source details", async () => {
    render(<AlertsPage />); await screen.findByText("Hotel Shuttle");
    fireEvent.click(screen.getByRole("tab", { name: "Geofence Activity" }));
    expect(await screen.findByText("Restricted Zone Entry")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View" }));
    const drawer = within(screen.getByRole("dialog"));
    expect(drawer.getByText("geo-event-1")).toBeInTheDocument();
    expect(drawer.getByText("GNSS")).toBeInTheDocument();
  });

  test("opens source-specific active-attention details", async () => {
    render(<AlertsPage />); await screen.findByText("Hotel Shuttle");
    fireEvent.click(screen.getByRole("button", { name: "View" }));
    const drawer = screen.getByRole("dialog");
    expect(within(drawer).getByRole("heading", { name: "Telemetry" })).toBeInTheDocument();
    expect(within(drawer).getByText("600 seconds")).toBeInTheDocument();
  });

  test("shows backend errors instead of an empty result", async () => {
    mocks.attention.mockRejectedValueOnce(new Error("backend unavailable"));
    render(<AlertsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load active attention.");
    expect(screen.queryByText("No active attention conditions.")).not.toBeInTheDocument();
  });

  test("applies source-specific filters and clears only the current tab", async () => {
    render(<AlertsPage />); await screen.findByText("Hotel Shuttle");
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    fireEvent.change(screen.getByLabelText("Attention source"), { target: { value: "INSPECTION" } });
    await waitFor(() => expect(mocks.attention).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, source: "INSPECTION" }), expect.any(AbortSignal)));
    fireEvent.click(screen.getByRole("button", { name: "Clear Filters" }));
    await waitFor(() => expect(mocks.attention).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, source: undefined }), expect.any(AbortSignal)));
    expect(screen.getByLabelText("Attention source")).toHaveValue("");
  });

  test("opens real inspection, maintenance, and no-telemetry source details from rows", async () => {
    const noTelemetry = { ...attention, id: "telemetry:2:no_telemetry", condition: "NO_TELEMETRY", current_state: "NO_TELEMETRY", vehicle: { ...attention.vehicle, id: 2, display_name: "No Signal Van" }, details: {} };
    const inspection = { ...attention, id: "inspection:3", condition: "FAILED_INSPECTION", source: "INSPECTION", current_state: "FAILED", vehicle: { ...attention.vehicle, id: 3, display_name: "Inspection Van" }, details: { inspection_type: "PRE_TRIP", inspection_date: "2026-09-21", result: "FAILED", inspector: "Alex Cruz", checklist: { brakes_condition: "NEEDS_ATTENTION" }, issues_found: "Brake wear", notes: "Inspect pads" } };
    const maintenance = { ...attention, id: "maintenance:4", condition: "MAINTENANCE_OPEN", source: "MAINTENANCE", current_state: "OPEN", vehicle: { ...attention.vehicle, id: 4, display_name: "Maintenance Van" }, details: { title: "Brake service", status: "OPEN", maintenance_source: "INSPECTION", notes: "Awaiting service" } };
    mocks.attention.mockResolvedValue({ count: 3, next: null, previous: null, results: [noTelemetry, inspection, maintenance], summary });
    render(<AlertsPage />);
    fireEvent.click(await screen.findByText("No Signal Van"));
    expect(within(screen.getByRole("dialog")).getByText("No telemetry received.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close details" }));
    fireEvent.click(screen.getByText("Inspection Van"));
    expect(within(screen.getByRole("dialog")).getByText("Brake wear")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close details" }));
    fireEvent.click(screen.getByText("Maintenance Van"));
    expect(within(screen.getByRole("dialog")).getByText("Brake service")).toBeInTheDocument();
  });

  test("shows an empty state without pagination controls", async () => {
    mocks.attention.mockResolvedValue({ count: 0, next: null, previous: null, results: [], summary: { ...summary, active_attention: 0 } });
    render(<AlertsPage />);
    expect(await screen.findByText("No active attention conditions.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Previous" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Next" })).not.toBeInTheDocument();
  });
});
