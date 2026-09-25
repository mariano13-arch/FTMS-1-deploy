import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import LiveFleetOperationsPage from "./LiveFleetOperationsPage";

const mocks = vi.hoisted(() => ({
  getFleet: vi.fn(),
  getRoute: vi.fn(),
  getTrail: vi.fn(),
  getSafetyEvents: vi.fn(),
  getDrivers: vi.fn(),
  getGeofences: vi.fn(),
  getGeofence: vi.fn(),
  getGeofenceActivity: vi.fn(),
  createGeofence: vi.fn(),
  updateGeofence: vi.fn(),
}));
vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  getFleetLiveVehicles: mocks.getFleet,
  getFleetActiveAssignmentRoute: mocks.getRoute,
  getFleetVehicleTrail: mocks.getTrail,
  getFleetSafetyEvents: mocks.getSafetyEvents,
  getGeofences: mocks.getGeofences,
  getGeofence: mocks.getGeofence,
  getGeofenceActivity: mocks.getGeofenceActivity,
  createGeofence: mocks.createGeofence,
  updateGeofence: mocks.updateGeofence,
}));
vi.mock("../../services/drivers", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../services/drivers")>()),
  getDrivers: mocks.getDrivers,
}));
vi.mock("../transport-requests/components/RequestMap", () => ({
  default: ({
    fleetLocations,
    fleetTrail = [],
    fleetPopup,
    safetyEvents = [],
    geofenceActivityEvent,
    onVehicleSelect,
    onVehicleStatus,
    onVehiclePopupClose,
    onSafetyEventSelect,
    onGeofenceCreateAt,
    routeState,
    route,
    plannedRoute,
    routeCameraKey,
    focusedVehicleId,
  }: {
    fleetLocations: Array<{ deviceId: string; label: string; emergencySOS?: { activatedAt: string } | null }>;
    fleetTrail?: Array<unknown>;
    fleetPopup: null | {
      deviceId: string;
      label: string;
      plateNumber: string;
      telemetryState: string;
      speedKph: number | null;
      positionSource: "GNSS" | "CELLULAR_LBS";
      positionAccuracyM: number | null;
      rpm?: number | null;
      coolantC?: number | null;
      engineLoadPct?: number | null;
      obdSource?: "SIMULATED_TEST" | "PHYSICAL_OBD" | null;
      driverName?: string;
      assignmentStatus?: string;
      activeRouteSummary?: string;
      telemetrySource: string;
    };
    safetyEvents: Array<{ event_id: string; vehicle_name: string }>;
    geofenceActivityEvent?: null | {
      vehicleName: string;
      eventType: string;
    };
    onVehicleSelect: (id: string) => void;
    onVehicleStatus: (id: string) => void;
    onVehiclePopupClose: () => void;
    onSafetyEventSelect: (id: string) => void;
    onGeofenceCreateAt: (point: {
      latitude: number;
      longitude: number;
    }) => void;
    routeState: string;
    route?: { distance_meters: number } | null;
    plannedRoute?: { distance_meters: number } | null;
    routeCameraKey?: string;
    focusedVehicleId?: string;
  }) => (
    <div
      data-testid="fleet-map"
      data-route-state={routeState}
      data-active-route={route ? "primary" : "none"}
      data-planned-route={plannedRoute ? "secondary" : "none"}
      data-route-camera-key={routeCameraKey}
      data-trail-points={fleetTrail.length}
      data-focused-vehicle={focusedVehicleId ?? ""}
    >
      <button
        onClick={() =>
          onGeofenceCreateAt({ latitude: 14.56, longitude: 121.02 })
        }
      >
        Place geofence on map
      </button>
      {fleetLocations.map((item) => (
        <button
          key={item.deviceId}
          data-emergency={item.emergencySOS ? "active" : "normal"}
          onClick={() => onVehicleSelect(item.deviceId)}
        >
          Marker {item.label}
        </button>
      ))}
      {safetyEvents.map((item) => (
        <button
          key={item.event_id}
          onClick={() => onSafetyEventSelect(item.event_id)}
        >
          Safety marker {item.vehicle_name}
        </button>
      ))}
      {geofenceActivityEvent && (
        <span data-testid="historical-geofence-marker">
          Historical {geofenceActivityEvent.eventType}:{" "}
          {geofenceActivityEvent.vehicleName}
        </span>
      )}
      {fleetPopup && (
        <article aria-label={`${fleetPopup.label} map details`}>
          <strong>{fleetPopup.plateNumber}</strong>
          <span>{fleetPopup.label}</span>
          <span>{fleetPopup.telemetryState}</span>
          <span>Speed: {fleetPopup.speedKph} km/h</span>
          {fleetPopup.positionSource === "CELLULAR_LBS" && (
            <>
              <span>Approximate cellular location</span>
              <span>Accuracy ~{Math.round(fleetPopup.positionAccuracyM!)} m</span>
            </>
          )}
          <span>
            {fleetPopup.telemetrySource === "demo"
              ? "Demo telemetry"
              : "Real telemetry"}
          </span>
          <span>{fleetPopup.driverName ?? "No active driver"}</span>
          <span>{fleetPopup.assignmentStatus ?? "No active dispatch"}</span>
          {fleetPopup.activeRouteSummary && <span>{fleetPopup.activeRouteSummary}</span>}
          {fleetPopup.obdSource === "SIMULATED_TEST" && (
            <strong>SIMULATED TEST OBD DATA</strong>
          )}
          <span>Engine RPM: {fleetPopup.rpm ?? "—"}</span>
          <span>Coolant temperature: {fleetPopup.coolantC ?? "—"}</span>
          <span>Engine load: {fleetPopup.engineLoadPct ?? "—"}</span>
          <button onClick={onVehiclePopupClose}>
            Close vehicle map details
          </button>
          <button>Zoom to</button>
          <button>Replay</button>
          <button onClick={() => onVehicleStatus(fleetPopup.deviceId)}>View Vehicle Status</button>
        </article>
      )}
    </div>
  ),
}));

const assignment = {
  assignment_id: 1,
  execution_status: "IN_TRANSIT",
  driver_id: 4,
  driver_code: "DRV-004",
  driver_name: "Ana Santos",
  request_id: "request-1",
  request_number: "TR-HMS-001",
  request_status: "READY_FOR_DISPATCH",
  source_system: "HOTEL_MANAGEMENT_SYSTEM",
  scheduled_pickup_at: "2026-08-21T09:00:00Z",
  pickup_name: "FTMS Hotel",
  pickup_latitude: "14.560000",
  pickup_longitude: "121.020000",
  destination_name: "NAIA Terminal 3",
  destination_latitude: "14.508600",
  destination_longitude: "121.019800",
};
const snapshot = {
  generated_at: "2026-08-21T08:00:00Z",
  capabilities: {
    telemetry_trail: true,
    safety_events: true,
    geofence: false,
    demo_telemetry: true,
  },
  demo_telemetry: { enabled: false, active: false, simulated_vehicle_count: 0 },
  vehicles: [
    {
      vehicle_id: 1,
      device_id: "LIVE-001",
      display_name: "Hotel Shuttle",
      plate_number: "ABC-123",
      vehicle_type: "VAN",
      is_active: true,
      telemetry_state: "live",
      telemetry: {
        latitude: 14.56,
        longitude: 121.02,
        speed_kph: 32,
        position_source: "GNSS",
        position_accuracy_m: null,
        recorded_at: "2026-08-21T07:59:50Z",
        age_seconds: 10,
        driving_event: "NORMAL",
        telemetry_source: "real",
        is_demo_telemetry: false,
      },
      active_assignment: assignment,
    },
    {
      vehicle_id: 2,
      device_id: "STALE-001",
      display_name: "Service Van",
      plate_number: "DEF-456",
      vehicle_type: "VAN",
      is_active: true,
      telemetry_state: "stale",
      telemetry: {
        latitude: 14.55,
        longitude: 121.03,
        speed_kph: 0,
        position_source: "GNSS",
        position_accuracy_m: null,
        recorded_at: "2026-08-21T07:00:00Z",
        age_seconds: 3600,
        driving_event: "NORMAL",
        telemetry_source: "real",
        is_demo_telemetry: false,
      },
      active_assignment: null,
    },
    {
      vehicle_id: 3,
      device_id: "NONE-001",
      display_name: "No Position Sedan",
      plate_number: "GHI-789",
      vehicle_type: "SEDAN",
      is_active: true,
      telemetry_state: "no_telemetry",
      telemetry: null,
      active_assignment: null,
    },
  ],
};
const geofence = {
  id: "geo-1", name: "Oxford Zone", description: "Hotel loading area", category: "RESTRICTED", shape_type: "CIRCLE",
  vertices: [{ latitude: 14.56, longitude: 121.02 }, { latitude: 14.56, longitude: 121.03 }, { latitude: 14.57, longitude: 121.02 }],
  center: { latitude: 14.56, longitude: 121.02 }, radius_meters: 150, color: "#008F8C", show_on_map: true, is_active: true,
  current_vehicle_count: 1, event_count: 2, entries_today: 1, exits_today: 1, latest_event: { id: 1, event_type: "ENTER", occurred_at: "2026-08-21T07:59:50Z", latitude: 14.56, longitude: 121.02, vehicle_id: 1, device_id: "LIVE-001", vehicle_name: "Hotel Shuttle", plate_number: "ABC-123", geofence_id: "geo-1", geofence_name: "Oxford Zone", geofence_category: "RESTRICTED" }, created_at: "2026-08-21T07:00:00Z", updated_at: "2026-08-21T07:00:00Z",
  current_vehicles: [{ vehicle_id: 1, device_id: "LIVE-001", vehicle_name: "Hotel Shuttle", plate_number: "ABC-123", recorded_at: "2026-08-21T07:59:50Z" }],
  events: [],
};
const activityEvents = [
  { id: 1, event_type: "ENTER", occurred_at: "2026-08-21T07:59:50Z", latitude: 14.56, longitude: 121.02, vehicle_id: 1, device_id: "LIVE-001", vehicle_name: "Hotel Shuttle", plate_number: "ABC-123", geofence_id: "geo-1", geofence_name: "Oxford Zone", geofence_category: "RESTRICTED" },
  { id: 2, event_type: "EXIT", occurred_at: "2026-08-21T06:59:50Z", latitude: 14.57, longitude: 121.03, vehicle_id: 2, device_id: "STALE-001", vehicle_name: "Service Van", plate_number: "DEF-456", geofence_id: "geo-1", geofence_name: "Oxford Zone", geofence_category: "RESTRICTED" },
];

beforeEach(() => {
  mocks.getFleet.mockResolvedValue(snapshot);
  mocks.getDrivers.mockResolvedValue({
    count: 2,
    next: null,
    previous: null,
    results: [
      {
        id: 4,
        driver_code: "DRV-004",
        first_name: "Ana",
        last_name: "Santos",
        full_name: "Ana Santos",
        employment_status: "ACTIVE",
        eligibility_status: "ELIGIBLE",
      },
      {
        id: 5,
        driver_code: "DRV-005",
        first_name: "Luis",
        last_name: "Cruz",
        full_name: "Luis Cruz",
        employment_status: "ON_LEAVE",
        eligibility_status: "NOT_ELIGIBLE",
      },
    ],
  });
  mocks.getTrail.mockResolvedValue({
    vehicle_id: 1,
    device_id: "LIVE-001",
    points: [
      {
        event_id: "trail-1",
        latitude: 14.55,
        longitude: 121.01,
        speed_kph: 28,
        recorded_at: "2026-08-21T07:59:30Z",
      },
      {
        event_id: "trail-2",
        latitude: 14.56,
        longitude: 121.02,
        speed_kph: 32,
        recorded_at: "2026-08-21T07:59:50Z",
      },
    ],
  });
  mocks.getSafetyEvents.mockResolvedValue({
    events: [
      {
        event_id: "brake-1",
        event_type: "HARSH_BRAKING",
        recorded_at: "2026-08-21T07:58:00Z",
        latitude: 14.56,
        longitude: 121.02,
        speed_kph: 24,
        vehicle_id: 1,
        device_id: "LIVE-001",
        vehicle_name: "Hotel Shuttle",
        plate_number: "ABC-123",
      },
    ],
  });
  mocks.getRoute.mockResolvedValue({
    route: {
      phase: "TO_DESTINATION",
      execution_status: "IN_TRANSIT",
      route_status: "AVAILABLE",
      position_state: "CURRENT",
      position_recorded_at: "2026-08-21T07:59:50Z",
      position_age_seconds: 10,
      route_basis: "CURRENT_VEHICLE_POSITION",
      vehicle_position: { latitude: 14.56, longitude: 121.02, recorded_at: "2026-08-21T07:59:50Z", is_stale: false, source: "GNSS" },
      pickup: { name: "FTMS Hotel", latitude: 14.56, longitude: 121.02 },
      destination: { name: "NAIA Terminal 3", latitude: 14.5086, longitude: 121.0198 },
      route: {
        traffic_mode: "live",
        distance_meters: 1000,
        duration_seconds: 300,
        traffic_delay_seconds: 20,
        departure_time: "2026-08-21T08:00:00Z",
        arrival_time: "2026-08-21T08:05:00Z",
        geometry: { type: "LineString", coordinates: [[121.02, 14.56], [121.0198, 14.5086]] },
      },
      planned_route_status: "NOT_APPLICABLE",
      planned_route: null,
    },
  });
  mocks.getGeofences.mockResolvedValue({ results: [geofence] });
  mocks.getGeofence.mockResolvedValue(geofence);
  mocks.getGeofenceActivity.mockReset().mockResolvedValue({ count: 2, next: null, previous: null, results: activityEvents });
  mocks.createGeofence.mockResolvedValue(geofence);
  mocks.updateGeofence.mockResolvedValue(geofence);
});
afterEach(() => {
  vi.restoreAllMocks();
});

test("renders authoritative telemetry states and confirmed assignment context", async () => {
  render(<LiveFleetOperationsPage />);
  expect(screen.getByRole("status")).toHaveTextContent(
    "Loading fleet operations",
  );
  expect(await screen.findByText("ABC-123 · Van")).toBeInTheDocument();
  expect(
    screen.queryByRole("region", { name: "Fleet operations overview" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /overview/i }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Marker Hotel Shuttle" }));
  const popup = screen.getByRole("article", {
    name: "Hotel Shuttle map details",
  });
  expect(within(popup).getByText("ABC-123")).toBeInTheDocument();
  expect(within(popup).getByText("Ana Santos")).toBeInTheDocument();
  expect(within(popup).getByText("TR-HMS-001 · In Transit")).toBeInTheDocument();
  expect(within(popup).queryByText(/Street view/i)).not.toBeInTheDocument();
  expect(screen.getByTitle("No telemetry")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Marker No Position Sedan" }),
  ).not.toBeInTheDocument();
  await waitFor(() =>
    expect(mocks.getRoute).toHaveBeenCalledWith(
      1,
      expect.any(AbortSignal),
    ),
  );
  expect(within(popup).getByText("Active leg — To Destination: 1.0 km · 5 min TomTom route estimate")).toBeInTheDocument();
  expect(mocks.getTrail).not.toHaveBeenCalled();
  expect(screen.getByTestId("fleet-map")).toHaveAttribute(
    "data-trail-points",
    "0",
  );
  expect(
    screen.queryByText(/Demo telemetry mode active/),
  ).not.toBeInTheDocument();
});

test("opens vehicle status instantly from the current snapshot without navigating", async () => {
  render(<LiveFleetOperationsPage />);
  await screen.findByText("ABC-123 · Van");
  fireEvent.click(screen.getByRole("button", { name: "Marker Hotel Shuttle" }));
  fireEvent.click(screen.getByRole("button", { name: "View Vehicle Status" }));
  expect(screen.getByRole("dialog", { name: "Hotel Shuttle" })).toBeInTheDocument();
  expect(screen.queryByRole("complementary", { name: "Fleet navigator" })).not.toBeInTheDocument();
  expect(screen.getByTestId("fleet-map")).toHaveAttribute("data-focused-vehicle", "LIVE-001");
  expect(mocks.getFleet).toHaveBeenCalledTimes(1);
});

test("restores active SOS from the fleet snapshot while preserving marker selection", async () => {
  const emergencySnapshot = {
    ...snapshot,
    vehicles: snapshot.vehicles.map((item) => item.device_id === "LIVE-001" ? {
      ...item,
      emergency_sos: {
        id: 9, device_id: "LIVE-001", vehicle_id: 1, driver_id: null,
        status: "ACTIVE", source: "PHYSICAL_BUTTON",
        activated_at: "2026-09-24T01:02:03Z", cleared_at: null,
      },
    } : { ...item, emergency_sos: null }),
  };
  mocks.getFleet.mockResolvedValue(emergencySnapshot);
  render(<LiveFleetOperationsPage />);
  const marker = await screen.findByRole("button", { name: "Marker Hotel Shuttle" });
  expect(marker).toHaveAttribute("data-emergency", "active");
  fireEvent.click(marker);
  expect(screen.getByRole("article", { name: "Hotel Shuttle map details" })).toBeInTheDocument();
});

test("removes completed trip context while preserving its real vehicle marker", async () => {
  mocks.getFleet.mockResolvedValueOnce({
    ...snapshot,
    vehicles: snapshot.vehicles.map((vehicle) =>
      vehicle.device_id === "LIVE-001"
        ? { ...vehicle, active_assignment: null }
        : vehicle,
    ),
  });
  render(<LiveFleetOperationsPage />);
  await screen.findByText("ABC-123 · Van");

  fireEvent.click(screen.getByRole("button", { name: "Marker Hotel Shuttle" }));
  const popup = screen.getByRole("article", {
    name: "Hotel Shuttle map details",
  });
  expect(within(popup).getByText("No active driver")).toBeInTheDocument();
  expect(within(popup).getByText("No active dispatch")).toBeInTheDocument();
  expect(within(popup).getByText("Real telemetry")).toBeInTheDocument();
  expect(mocks.getRoute).not.toHaveBeenCalled();
});

test("labels a cellular LBS marker as approximate and shows its accuracy", async () => {
  mocks.getFleet.mockResolvedValueOnce({
    ...snapshot,
    vehicles: snapshot.vehicles.map((vehicle) =>
      vehicle.device_id === "LIVE-001" && vehicle.telemetry
        ? {
            ...vehicle,
            telemetry: {
              ...vehicle.telemetry,
              speed_kph: null,
              position_source: "CELLULAR_LBS" as const,
              position_accuracy_m: 550,
              rpm: 2345,
              coolant_c: 91,
              engine_load_pct: 47,
              obd_source: "SIMULATED_TEST" as const,
            },
          }
        : vehicle,
    ),
  });
  render(<LiveFleetOperationsPage />);
  await screen.findByText("ABC-123 · Van");
  fireEvent.click(screen.getByRole("button", { name: "Marker Hotel Shuttle" }));
  const popup = screen.getByRole("article", { name: "Hotel Shuttle map details" });
  expect(within(popup).getByText("Approximate cellular location")).toBeInTheDocument();
  expect(within(popup).getByText("Accuracy ~550 m")).toBeInTheDocument();
  expect(within(popup).getByText("SIMULATED TEST OBD DATA")).toBeInTheDocument();
  expect(within(popup).getByText("Engine RPM: 2345")).toBeInTheDocument();
  expect(within(popup).getByText("Coolant temperature: 91")).toBeInTheDocument();
  expect(within(popup).getByText("Engine load: 47")).toBeInTheDocument();
  expect(within(popup).getByText("Real telemetry")).toBeInTheDocument();
});

test("renders missing OBD readings as unavailable rather than zero", async () => {
  render(<LiveFleetOperationsPage />);
  await screen.findByText("ABC-123 · Van");
  fireEvent.click(screen.getByRole("button", { name: "Marker Hotel Shuttle" }));
  const popup = screen.getByRole("article", { name: "Hotel Shuttle map details" });
  expect(within(popup).getByText("Engine RPM: —")).toBeInTheDocument();
  expect(within(popup).getByText("Coolant temperature: —")).toBeInTheDocument();
  expect(within(popup).getByText("Engine load: —")).toBeInTheDocument();
  expect(within(popup).queryByText("SIMULATED TEST OBD DATA")).not.toBeInTheDocument();
});

test("filters the compact vehicle list and supports marker selection", async () => {
  render(<LiveFleetOperationsPage />);
  await screen.findByText("ABC-123 · Van");
  fireEvent.change(
    screen.getByRole("textbox", { name: "Search fleet vehicles" }),
    { target: { value: "Ana Santos" } },
  );
  expect(screen.getByText("ABC-123 · Van")).toBeInTheDocument();
  expect(screen.queryByText("DEF-456 · Van")).not.toBeInTheDocument();
  fireEvent.change(
    screen.getByRole("textbox", { name: "Search fleet vehicles" }),
    { target: { value: "" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Attention" }));
  const list = screen.getByRole("complementary", { name: "Fleet navigator" });
  expect(within(list).queryByText("ABC-123 · Van")).not.toBeInTheDocument();
  expect(within(list).getByText("DEF-456 · Van")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "All" }));
  fireEvent.click(screen.getByRole("button", { name: "Marker Service Van" }));
  const popup = await screen.findByRole("article", {
    name: "Service Van map details",
  });
  expect(within(popup).getByText("stale")).toBeInTheDocument();
  expect(within(popup).getByText("Speed: 0 km/h")).toBeInTheDocument();
});

test("keeps the map mounted while the fleet overlay is collapsed", async () => {
  render(<LiveFleetOperationsPage />);
  await screen.findByText("ABC-123 · Van");
  fireEvent.click(
    screen.getByRole("button", { name: "Collapse fleet navigator" }),
  );
  expect(
    screen.queryByRole("complementary", { name: "Fleet navigator" }),
  ).not.toBeInTheDocument();
  expect(screen.getByTestId("fleet-map")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Show fleet/ }));
  expect(
    screen.getByRole("complementary", { name: "Fleet navigator" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Marker Service Van" }));
  expect(
    await screen.findByRole("article", { name: "Service Van map details" }),
  ).toBeInTheDocument();
});

test("focuses the status vehicle and keeps the fleet navigator collapsed", async () => {
  render(<LiveFleetOperationsPage focusedVehicleId="LIVE-001" />);
  await screen.findByRole("button", { name: /Show fleet/ });
  expect(screen.queryByRole("complementary", { name: "Fleet navigator" })).not.toBeInTheDocument();
  expect(screen.getByTestId("fleet-map")).toHaveAttribute(
    "data-focused-vehicle",
    "LIVE-001",
  );
});

test("uses Vehicles and Drivers tabs while preserving existing driver behavior", async () => {
  render(<LiveFleetOperationsPage />);
  await screen.findByText("ABC-123 · Van");
  const navigatorHeader = screen.getByTestId("fleet-navigator-header");
  const scrollRegion = screen.getByTestId("fleet-navigator-scroll-region");
  const navigatorFooter = screen.getByTestId("fleet-navigator-footer");
  expect(within(scrollRegion).getByText("Hotel Shuttle")).toBeInTheDocument();
  expect(
    within(navigatorHeader).getByRole("textbox", {
      name: "Search fleet vehicles",
    }),
  ).toBeInTheDocument();
  expect(
    within(navigatorHeader).getByRole("button", { name: "All" }),
  ).toBeInTheDocument();
  expect(scrollRegion).not.toContainElement(navigatorHeader);
  expect(scrollRegion).not.toContainElement(navigatorFooter);
  expect(within(navigatorHeader).getByRole("tab", { name: "Vehicles" })).toHaveAttribute("aria-selected", "true");
  expect(within(navigatorHeader).getByRole("tab", { name: "Drivers" })).toHaveAttribute("aria-selected", "false");
  expect(within(navigatorHeader).queryByText("Groups")).not.toBeInTheDocument();
  expect(within(navigatorHeader).queryByRole("button", { name: "Drivers" })).not.toBeInTheDocument();
  expect(within(navigatorHeader).getByRole("button", { name: "Uncheck all visible vehicles" })).toHaveTextContent("Uncheck All");
  expect(navigatorFooter).toHaveTextContent("3 of 3 visible");
  const visibilityCheckbox = screen.getByRole("checkbox", {
    name: "Show Hotel Shuttle on map",
  });
  scrollRegion.scrollTop = 24;
  fireEvent.click(visibilityCheckbox);
  expect(screen.getByTestId("fleet-navigator-header")).toBe(navigatorHeader);
  expect(screen.getByTestId("fleet-navigator-scroll-region")).toBe(
    scrollRegion,
  );
  expect(screen.getByTestId("fleet-navigator-footer")).toBe(navigatorFooter);
  expect(scrollRegion.scrollTop).toBe(24);
  expect(visibilityCheckbox).not.toBeChecked();
  expect(navigatorFooter).toHaveTextContent("2 of 3 visible");
  expect(within(navigatorHeader).getByRole("button", { name: "Check all visible vehicles" })).toHaveTextContent("Check All");
  expect(
    screen.queryByRole("button", { name: "Marker Hotel Shuttle" }),
  ).not.toBeInTheDocument();
  fireEvent.click(within(navigatorHeader).getByRole("tab", { name: "Drivers" }));
  expect(
    await screen.findByRole("button", { name: /Ana Santos/ }),
  ).toBeInTheDocument();
  expect(screen.getByText("Assigned to Hotel Shuttle")).toBeInTheDocument();
  expect(within(navigatorHeader).queryByRole("button", { name: /all visible vehicles/i })).not.toBeInTheDocument();
  fireEvent.click(within(navigatorHeader).getByRole("tab", { name: "Vehicles" }));
  expect(screen.getByRole("checkbox", { name: "Show Hotel Shuttle on map" })).not.toBeChecked();
});

test("uses one visibility action derived from the current filtered vehicle set", async () => {
  render(<LiveFleetOperationsPage />);
  await screen.findByText("ABC-123 · Van");
  const header = screen.getByTestId("fleet-navigator-header");

  expect(within(header).getAllByRole("button", { name: /check all visible vehicles/i })).toHaveLength(1);
  fireEvent.click(within(header).getByRole("button", { name: "Uncheck all visible vehicles" }));
  expect(screen.getByRole("checkbox", { name: "Show Hotel Shuttle on map" })).not.toBeChecked();
  expect(screen.getByRole("checkbox", { name: "Show Service Van on map" })).not.toBeChecked();
  expect(within(header).getByRole("button", { name: "Check all visible vehicles" })).toHaveTextContent("Check All");

  fireEvent.click(within(header).getByRole("button", { name: "Check all visible vehicles" }));
  expect(screen.getByRole("checkbox", { name: "Show Hotel Shuttle on map" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "Show Service Van on map" })).toBeChecked();
  expect(within(header).getByRole("button", { name: "Uncheck all visible vehicles" })).toHaveTextContent("Uncheck All");

  fireEvent.click(screen.getByRole("checkbox", { name: "Show Hotel Shuttle on map" }));
  expect(within(header).getByRole("button", { name: "Check all visible vehicles" })).toBeInTheDocument();

  fireEvent.click(within(header).getByRole("button", { name: "Attention" }));
  expect(within(header).getByRole("button", { name: "Uncheck all visible vehicles" })).toBeInTheDocument();
  fireEvent.click(within(header).getByRole("button", { name: "Uncheck all visible vehicles" }));
  expect(screen.getByRole("checkbox", { name: "Show Service Van on map" })).not.toBeChecked();
  fireEvent.click(within(header).getByRole("button", { name: "All" }));
  expect(screen.getByRole("checkbox", { name: "Show Hotel Shuttle on map" })).not.toBeChecked();

  fireEvent.click(within(header).getByRole("tab", { name: "Drivers" }));
  expect(screen.queryAllByRole("button", { name: "Marker Hotel Shuttle" })).toHaveLength(0);
  expect(await screen.findByRole("button", { name: /Ana Santos/ })).toBeInTheDocument();
  expect(screen.queryByText("Groups")).not.toBeInTheDocument();
});

test("does not overlay safety-event markers on clickable vehicle markers", async () => {
  render(<LiveFleetOperationsPage />);
  await screen.findByRole("button", { name: "Marker Hotel Shuttle" });
  expect(screen.queryByRole("button", { name: /Safety marker/ })).not.toBeInTheDocument();
});

test("clearly labels opt-in simulated telemetry without presenting it as real", async () => {
  mocks.getFleet.mockResolvedValueOnce({
    ...snapshot,
    demo_telemetry: { enabled: true, active: true, simulated_vehicle_count: 1 },
    vehicles: snapshot.vehicles.map((vehicle) =>
      vehicle.device_id === "STALE-001"
        ? {
            ...vehicle,
            telemetry_state: "stale",
            telemetry: {
              ...vehicle.telemetry!,
              recorded_at: "2026-08-21T08:00:00Z",
              age_seconds: 0,
              telemetry_source: "demo",
              is_demo_telemetry: true,
            },
          }
        : vehicle,
    ),
  });
  render(<LiveFleetOperationsPage />);
  expect(
    await screen.findByText(
      "Demo telemetry mode active — 1 simulated location for capstone defense only.",
    ),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Marker Service Van" }));
  const popup = await screen.findByRole("article", {
    name: "Service Van map details",
  });
  expect(within(popup).getByText("Demo telemetry")).toBeInTheDocument();
  expect(within(popup).queryByText("Real telemetry")).not.toBeInTheDocument();
});

test("keeps the page usable when fleet loading or an operational route fails", async () => {
  mocks.getRoute.mockRejectedValueOnce(new Error("route unavailable"));
  const first = render(<LiveFleetOperationsPage />);
  await waitFor(() =>
    expect(screen.getByTestId("fleet-map")).toHaveAttribute(
      "data-route-state",
      "error",
    ),
  );
  first.unmount();
  mocks.getFleet.mockRejectedValueOnce(new Error("fleet unavailable"));
  render(<LiveFleetOperationsPage />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Unable to load fleet operations",
  );
});

test("labels an active route from stale telemetry as last known", async () => {
  mocks.getRoute.mockResolvedValueOnce({
    route: {
      phase: "TO_DESTINATION",
      execution_status: "IN_TRANSIT",
      route_status: "AVAILABLE",
      position_state: "STALE",
      position_recorded_at: "2026-08-19T20:13:50Z",
      position_age_seconds: 128160,
      route_basis: "LAST_KNOWN_VEHICLE_POSITION",
      vehicle_position: { latitude: 14.56, longitude: 121.02, recorded_at: "2026-08-19T20:13:50Z", is_stale: true, source: "GNSS" },
      pickup: { name: "FTMS Hotel", latitude: 14.56, longitude: 121.02 },
      destination: { name: "NAIA Terminal 3", latitude: 14.5086, longitude: 121.0198 },
      route: {
        traffic_mode: "live", distance_meters: 12400, duration_seconds: 1860,
        traffic_delay_seconds: 0, departure_time: "", arrival_time: "",
        geometry: { type: "LineString", coordinates: [[121.02, 14.56], [121.0198, 14.5086]] },
      },
    },
  });
  render(<LiveFleetOperationsPage />);
  await screen.findByText("ABC-123 · Van");
  fireEvent.click(screen.getByRole("button", { name: "Marker Hotel Shuttle" }));
  const popup = await screen.findByRole("article", { name: "Hotel Shuttle map details" });
  expect(within(popup).getByText("Active leg — From last known position: 12.4 km · 31 min TomTom route estimate · 35h 36m old")).toBeInTheDocument();
  expect(within(popup).queryByText(/Current ETA/i)).not.toBeInTheDocument();
});

test("renders pre-pickup TomTom legs as primary and secondary without refitting on telemetry refresh", async () => {
  mocks.getFleet.mockResolvedValue({
    ...snapshot,
    vehicles: snapshot.vehicles.map((vehicle) =>
      vehicle.device_id === "LIVE-001"
        ? { ...vehicle, active_assignment: { ...assignment, execution_status: "EN_ROUTE_TO_PICKUP" } }
        : vehicle,
    ),
  });
  mocks.getRoute.mockResolvedValueOnce({
    route: {
      phase: "TO_PICKUP",
      execution_status: "EN_ROUTE_TO_PICKUP",
      route_status: "AVAILABLE",
      position_state: "CURRENT",
      position_recorded_at: "2026-08-21T07:59:50Z",
      position_age_seconds: 10,
      route_basis: "CURRENT_VEHICLE_POSITION",
      vehicle_position: { latitude: 14.56, longitude: 121.02, recorded_at: "2026-08-21T07:59:50Z", is_stale: false, source: "GNSS" },
      pickup: { name: "FTMS Hotel", latitude: 14.56, longitude: 121.02 },
      destination: { name: "NAIA Terminal 3", latitude: 14.5086, longitude: 121.0198 },
      route: { traffic_mode: "live", distance_meters: 4200, duration_seconds: 720, traffic_delay_seconds: 60, departure_time: "", arrival_time: "", geometry: { type: "LineString", coordinates: [[121.05, 14.58], [121.02, 14.56]] } },
      planned_route_status: "AVAILABLE",
      planned_route: { traffic_mode: "live", distance_meters: 7400, duration_seconds: 1140, traffic_delay_seconds: 80, departure_time: "", arrival_time: "", geometry: { type: "LineString", coordinates: [[121.02, 14.56], [121.0198, 14.5086]] } },
    },
  });

  render(<LiveFleetOperationsPage />);
  const map = await screen.findByTestId("fleet-map");
  await waitFor(() => expect(map).toHaveAttribute("data-active-route", "primary"));
  expect(map).toHaveAttribute("data-planned-route", "secondary");
  expect(map).toHaveAttribute("data-route-camera-key", "1:EN_ROUTE_TO_PICKUP");
  fireEvent.click(screen.getByRole("button", { name: "Marker Hotel Shuttle" }));
  expect(await screen.findByText(/Next — Pickup to Destination: 7.4 km · 19 min/)).toBeInTheDocument();
});

test("lists geofence occupancy and activity and creates a customizable map boundary", async () => {
  render(<LiveFleetOperationsPage />);
  await screen.findByText("ABC-123 · Van");
  fireEvent.click(screen.getByRole("button", { name: /Geofences/ }));
  expect(screen.getByRole("complementary", { name: "Geofence workspace" })).toHaveClass(
    "live-fleet-geofence-panel--browser",
  );
  expect(await screen.findByText("Saved Geofences")).toBeInTheDocument();
  expect(screen.getByText("Saved Geofences").parentElement).toHaveTextContent("1");
  fireEvent.click(await screen.findByRole("button", { name: /Oxford Zone/ }));
  expect(screen.getByRole("button", { name: /Oxford Zone/ })).toHaveAttribute("aria-pressed", "true");
  const detail = await screen.findByRole("region", { name: "Oxford Zone geofence details" });
  expect(within(detail).getByText("Selected Geofence")).toBeInTheDocument();
  expect(within(detail).getByText("150 m radius · Circle")).toBeInTheDocument();
  expect(within(detail).getByText("Monitoring")).toBeInTheDocument();
  expect(within(detail).getByText("Assets inside")).toHaveTextContent("1Assets inside");
  expect(within(detail).getByText("Entries today")).toHaveTextContent("1Entries today");
  expect(within(detail).getByText("Exits today")).toHaveTextContent("1Exits today");
  expect(within(detail).getByText("Latest activity").parentElement).not.toHaveTextContent("—");
  expect(await within(detail).findByText("Restricted Entry")).toBeInTheDocument();
  expect(within(detail).getAllByText("EXIT")).toHaveLength(2);
  fireEvent.click(within(detail).getAllByRole("button", { name: "View on map" })[0]);
  expect(screen.getByTestId("historical-geofence-marker")).toHaveTextContent("Historical ENTER: Hotel Shuttle");
  fireEvent.change(within(detail).getByLabelText("Filter geofence activity by event type"), { target: { value: "EXIT" } });
  await waitFor(() => expect(mocks.getGeofenceActivity).toHaveBeenLastCalledWith(expect.objectContaining({ geofence: "geo-1", event_type: "EXIT", page: 1 }), expect.any(AbortSignal)));
  fireEvent.change(within(detail).getByLabelText("Filter geofence activity by vehicle"), { target: { value: "2" } });
  fireEvent.change(within(detail).getByLabelText("Geofence activity date from"), { target: { value: "2026-08-01" } });
  fireEvent.change(within(detail).getByLabelText("Geofence activity date to"), { target: { value: "2026-08-21" } });
  await waitFor(() => expect(mocks.getGeofenceActivity).toHaveBeenLastCalledWith(expect.objectContaining({ vehicle: 2, date_from: "2026-08-01", date_to: "2026-08-21" }), expect.any(AbortSignal)));
  fireEvent.click(screen.getByRole("button", { name: "+ New Geofence" }));
  fireEvent.click(
    screen.getByRole("button", { name: "Place geofence on map" }),
  );
  fireEvent.change(screen.getByLabelText("Geofence name"), {
    target: { value: "New Depot" },
  });
  fireEvent.change(screen.getByLabelText("Geofence radius"), {
    target: { value: "300" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create geofence" }));
  await waitFor(() => expect(mocks.createGeofence).toHaveBeenCalledWith(expect.objectContaining({ name: "New Depot", radius_meters: 300, shape_type: "CIRCLE" })));
  await screen.findByRole("button", { name: "+ New Geofence" });
  expect(await screen.findByText("Restricted Entry")).toBeInTheDocument();
});

test("edits a geofence with populated compact sections and the existing payload", async () => {
  render(<LiveFleetOperationsPage />);
  await screen.findByText("ABC-123 · Van");
  fireEvent.click(screen.getByRole("button", { name: /Geofences/ }));
  fireEvent.click(await screen.findByRole("button", { name: /Oxford Zone/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Edit" }));

  const panel = screen.getByRole("complementary", { name: "Geofence workspace" });
  expect(panel).toHaveClass("live-fleet-geofence-panel--editor");
  expect(within(panel).getByText("Geofence Details")).toBeInTheDocument();
  expect(within(panel).getByText("Boundary Settings")).toBeInTheDocument();
  expect(within(panel).getByText("Appearance & Monitoring")).toBeInTheDocument();
  expect(screen.getByLabelText("Geofence name")).toHaveValue("Oxford Zone");
  expect(screen.getByLabelText("Geofence category")).toHaveValue("RESTRICTED");
  expect(screen.getByLabelText("Geofence boundary shape")).toHaveValue("CIRCLE");
  expect(screen.getByLabelText("Geofence radius")).toHaveValue("150");
  expect(screen.getByLabelText("Geofence description")).toHaveValue("Hotel loading area");
  expect(screen.getByLabelText("Geofence color")).toHaveValue("#008f8c");
  expect(screen.getByRole("checkbox", { name: /Show on map/ })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: /Track activity/ })).toBeChecked();

  fireEvent.change(screen.getByLabelText("Geofence name"), { target: { value: "Oxford Operations Zone" } });
  fireEvent.change(screen.getByLabelText("Geofence category"), { target: { value: "DEPOT" } });
  fireEvent.change(screen.getByLabelText("Geofence radius"), { target: { value: "300" } });
  fireEvent.change(screen.getByLabelText("Geofence description"), { target: { value: "Updated operating notes" } });
  fireEvent.click(screen.getByRole("checkbox", { name: /Show on map/ }));
  fireEvent.click(screen.getByRole("checkbox", { name: /Track activity/ }));
  fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));

  await waitFor(() => expect(mocks.updateGeofence).toHaveBeenCalledWith("geo-1", expect.objectContaining({
    name: "Oxford Operations Zone",
    category: "DEPOT",
    shape_type: "CIRCLE",
    radius_meters: 300,
    description: "Updated operating notes",
    color: "#008F8C",
    show_on_map: false,
    is_active: false,
  })));
  await waitFor(() =>
    expect(screen.queryByLabelText("Geofence name")).not.toBeInTheDocument(),
  );
});

test("cancels geofence editing without saving", async () => {
  render(<LiveFleetOperationsPage />);
  await screen.findByText("ABC-123 · Van");
  fireEvent.click(screen.getByRole("button", { name: /Geofences/ }));
  fireEvent.click(await screen.findByRole("button", { name: /Oxford Zone/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
  fireEvent.change(screen.getByLabelText("Geofence name"), { target: { value: "Unsaved" } });
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByLabelText("Geofence name")).not.toBeInTheDocument();
  expect(mocks.updateGeofence).not.toHaveBeenCalled();
});

test("shows geofence activity loading and empty states", async () => {
  let resolveActivity!: (value: { count: number; next: null; previous: null; results: never[] }) => void;
  mocks.getGeofenceActivity.mockImplementationOnce(() => new Promise(resolve => { resolveActivity = resolve; }));
  render(<LiveFleetOperationsPage />);
  await screen.findByText("ABC-123 · Van");
  fireEvent.click(screen.getByRole("button", { name: /Geofences/ }));
  fireEvent.click(await screen.findByRole("button", { name: /Oxford Zone/ }));
  expect(await screen.findByRole("status", { name: "" })).toHaveTextContent("Loading geofence activity");
  resolveActivity({ count: 0, next: null, previous: null, results: [] });
  expect(await screen.findByText("No persisted activity matches these filters.")).toBeInTheDocument();
});

test("shows a geofence activity error without hiding the monitoring summary", async () => {
  mocks.getGeofenceActivity.mockRejectedValueOnce(new Error("activity unavailable"));
  render(<LiveFleetOperationsPage />);
  await screen.findByText("ABC-123 · Van");
  fireEvent.click(screen.getByRole("button", { name: /Geofences/ }));
  fireEvent.click(await screen.findByRole("button", { name: /Oxford Zone/ }));
  expect(await screen.findByRole("alert", { name: "" })).toHaveTextContent("Unable to load geofence activity");
  expect(screen.getByText("Entries today")).toBeInTheDocument();
});
