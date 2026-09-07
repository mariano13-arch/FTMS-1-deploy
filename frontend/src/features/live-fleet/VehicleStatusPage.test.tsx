import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import VehicleStatusPage from "./VehicleStatusPage";
import type { FleetLiveResponse, FleetLiveVehicle } from "./api";

const mocks = vi.hoisted(() => ({ getFleet: vi.fn() }));
vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  getFleetLiveVehicles: mocks.getFleet,
}));

const vehicle: FleetLiveVehicle = {
  vehicle_id: 1,
  device_id: "LILYGO-002",
  display_name: "Operations Shuttle",
  plate_number: "ABC-123",
  vehicle_type: "VAN",
  is_active: true,
  telemetry_state: "live" as const,
  telemetry: {
    latitude: 14.5,
    longitude: 121,
    speed_kph: null,
    position_source: "CELLULAR_LBS" as const,
    position_accuracy_m: 550,
    recorded_at: "2026-09-07T04:00:00Z",
    age_seconds: 10,
    driving_event: null,
    rpm: 0,
    coolant_c: 91,
    engine_load_pct: 0,
    obd_source: "SIMULATED_TEST" as const,
    telemetry_source: "real" as const,
    is_demo_telemetry: false,
  },
  active_assignment: null,
};

const response = (vehicles: FleetLiveVehicle[]): FleetLiveResponse => ({
  generated_at: "2026-09-07T04:00:10Z",
  capabilities: { telemetry_trail: true, safety_events: true, geofence: true, demo_telemetry: false },
  demo_telemetry: { enabled: false, active: false, simulated_vehicle_count: 0 },
  vehicles,
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/live-map/vehicles/LILYGO-002/status"]}>
      <Route path="/live-map/vehicles/:deviceId/status"><VehicleStatusPage /></Route>
    </MemoryRouter>,
  );
}

beforeEach(() => mocks.getFleet.mockResolvedValue(response([vehicle])));

test("renders populated telemetry, simulated provenance, zeroes, and LBS semantics", async () => {
  renderPage();
  expect(await screen.findByRole("heading", { name: "Operations Shuttle" })).toBeInTheDocument();
  expect(screen.getByRole("dialog", { name: "Operations Shuttle" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Close vehicle status" })).toHaveAttribute("href", "/live-map");
  expect(screen.getByText("ABC-123 · LILYGO-002")).toBeInTheDocument();
  expect(screen.getByText("Approximate cellular location")).toBeInTheDocument();
  expect(screen.getByText("~550 m")).toBeInTheDocument();
  expect(screen.getByText("SIMULATED TEST OBD DATA")).toBeInTheDocument();
  expect(screen.getByText("No event")).toBeInTheDocument();

  const position = screen.getByRole("heading", { name: "Position" }).closest("section")!;
  expect(within(position).getByText("—")).toBeInTheDocument();
  const engine = screen.getByRole("heading", { name: "Engine / OBD" }).closest("section")!;
  expect(within(engine).getByText("0", { selector: "dd" })).toBeInTheDocument();
  expect(within(engine).getByText("0%", { selector: "dd" })).toBeInTheDocument();
  expect(within(engine).getByText("91 °C")).toBeInTheDocument();
  expect(screen.getByText("Simulated test")).toBeInTheDocument();
});

test("renders missing readings as unavailable without fabricating zeroes", async () => {
  mocks.getFleet.mockResolvedValueOnce(response([{ ...vehicle, telemetry: {
    ...vehicle.telemetry!, speed_kph: 0, position_source: "GNSS", position_accuracy_m: null,
    rpm: null, coolant_c: null, engine_load_pct: null, obd_source: null,
  } }]));
  renderPage();
  await screen.findByRole("heading", { name: "Operations Shuttle" });
  expect(screen.getByText("0 km/h")).toBeInTheDocument();
  expect(screen.queryByText("SIMULATED TEST OBD DATA")).not.toBeInTheDocument();
  const engine = screen.getByRole("heading", { name: "Engine / OBD" }).closest("section")!;
  expect(within(engine).getAllByText("—")).toHaveLength(3);
});

test("shows a clear empty state when the vehicle has no telemetry", async () => {
  mocks.getFleet.mockResolvedValueOnce(response([{ ...vehicle, telemetry_state: "no_telemetry", telemetry: null }]));
  renderPage();
  expect(await screen.findByRole("heading", { name: "No telemetry received" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Position" })).not.toBeInTheDocument();
});
