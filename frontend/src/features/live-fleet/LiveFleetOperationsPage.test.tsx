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
  getFleetVehicleTrail: mocks.getTrail,
  getFleetSafetyEvents: mocks.getSafetyEvents,
  getGeofences: mocks.getGeofences,
  getGeofence: mocks.getGeofence,
  getGeofenceActivity: mocks.getGeofenceActivity,
  createGeofence: mocks.createGeofence,
  updateGeofence: mocks.updateGeofence,
}));
vi.mock("../transport-requests/api", () => ({
  getRequestRoute: mocks.getRoute,
}));
vi.mock("../../services/drivers", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../services/drivers")>()),
  getDrivers: mocks.getDrivers,
}));
vi.mock("../transport-requests/components/RequestMap", () => ({
  default: ({
    fleetLocations,
    fleetTrail,
    fleetPopup,
    safetyEvents,
    geofenceActivityEvent,
    onVehicleSelect,
    onVehiclePopupClose,
    onSafetyEventSelect,
    onGeofenceCreateAt,
    routeState,
  }: {
    fleetLocations: Array<{ deviceId: string; label: string }>;
    fleetTrail: Array<unknown>;
    fleetPopup: null | {
      label: string;
      plateNumber: string;
      telemetryState: string;
      speedKph: number;
      driverName?: string;
      assignmentStatus?: string;
      telemetrySource: string;
    };
    safetyEvents: Array<{ event_id: string; vehicle_name: string }>;
    geofenceActivityEvent?: null | {
      vehicleName: string;
      eventType: string;
    };
    onVehicleSelect: (id: string) => void;
    onVehiclePopupClose: () => void;
    onSafetyEventSelect: (id: string) => void;
    onGeofenceCreateAt: (point: {
      latitude: number;
      longitude: number;
    }) => void;
    routeState: string;
  }) => (
    <div
      data-testid="fleet-map"
      data-route-state={routeState}
      data-trail-points={fleetTrail.length}
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
          <span>
            {fleetPopup.telemetrySource === "demo"
              ? "Demo telemetry"
              : "Real telemetry"}
          </span>
          <span>{fleetPopup.driverName ?? "No active driver"}</span>
          <span>{fleetPopup.assignmentStatus ?? "No active dispatch"}</span>
          <button onClick={onVehiclePopupClose}>
            Close vehicle map details
          </button>
          <button>Zoom to</button>
          <button>Replay</button>
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
    request_id: "request-1",
    traffic_mode: "live",
    distance_meters: 1000,
    duration_seconds: 300,
    traffic_delay_seconds: 20,
    departure_time: "2026-08-21T08:00:00Z",
    arrival_time: "2026-08-21T08:05:00Z",
    geometry: {
      type: "LineString",
      coordinates: [
        [121.02, 14.56],
        [121.0198, 14.5086],
      ],
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
  const overview = screen.getByRole("region", {
    name: "Fleet operations overview",
  });
  expect(
    within(overview).getByRole("heading", {
      name: "Live Fleet Operations Map",
    }),
  ).toBeInTheDocument();
  expect(
    within(overview).getByText("Total vehicles").previousSibling,
  ).toHaveTextContent("3");
  expect(
    within(overview).getByText("Live telemetry").previousSibling,
  ).toHaveTextContent("1");
  expect(
    within(overview).getByText("Stale / offline").previousSibling,
  ).toHaveTextContent("1");
  expect(
    within(overview).getByText("Active assignments").previousSibling,
  ).toHaveTextContent("1");
  expect(
    within(overview).getByText("No telemetry").previousSibling,
  ).toHaveTextContent("1");
  fireEvent.click(screen.getByRole("button", { name: "Marker Hotel Shuttle" }));
  const popup = screen.getByRole("article", {
    name: "Hotel Shuttle map details",
  });
  expect(within(popup).getByText("ABC-123")).toBeInTheDocument();
  expect(within(popup).getByText("Ana Santos")).toBeInTheDocument();
  expect(within(popup).getByText("In Transit")).toBeInTheDocument();
  expect(within(popup).queryByText(/Street view/i)).not.toBeInTheDocument();
  expect(screen.getByTitle("No telemetry")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Marker No Position Sedan" }),
  ).not.toBeInTheDocument();
  await waitFor(() =>
    expect(mocks.getRoute).toHaveBeenCalledWith(
      "request-1",
      expect.any(AbortSignal),
    ),
  );
  await waitFor(() =>
    expect(screen.getByTestId("fleet-map")).toHaveAttribute(
      "data-trail-points",
      "2",
    ),
  );
  expect(
    screen.queryByText(/Demo telemetry mode active/),
  ).not.toBeInTheDocument();
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

test("switches between real vehicle and driver lists and controls marker visibility", async () => {
  render(<LiveFleetOperationsPage />);
  await screen.findByText("ABC-123 · Van");
  fireEvent.click(
    screen.getByRole("checkbox", { name: "Show Hotel Shuttle on map" }),
  );
  expect(
    screen.queryByRole("button", { name: "Marker Hotel Shuttle" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show drivers" }));
  expect(
    await screen.findByRole("button", { name: /Ana Santos/ }),
  ).toBeInTheDocument();
  expect(screen.getByText("Assigned to Hotel Shuttle")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Drivers/ }));
  fireEvent.click(screen.getByRole("menuitem", { name: /Groups/ }));
  expect(screen.getByText("No groups configured")).toBeInTheDocument();
});

test("opens the associated vehicle popup when a safety marker is selected", async () => {
  render(<LiveFleetOperationsPage />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Safety marker Hotel Shuttle" }),
  );
  expect(
    screen.getByRole("article", { name: "Hotel Shuttle map details" }),
  ).toBeInTheDocument();
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

test("lists geofence occupancy and activity and creates a customizable map boundary", async () => {
  render(<LiveFleetOperationsPage />);
  await screen.findByText("ABC-123 · Van");
  fireEvent.click(screen.getByRole("button", { name: /Geofences/ }));
  fireEvent.click(await screen.findByRole("button", { name: /Oxford Zone/ }));
  const detail = await screen.findByRole("region", { name: "Oxford Zone geofence details" });
  expect(within(detail).getByText("Assets inside")).toHaveTextContent("1Assets inside");
  expect(within(detail).getByText("Entries today")).toHaveTextContent("1Entries today");
  expect(within(detail).getByText("Exits today")).toHaveTextContent("1Exits today");
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
  fireEvent.click(screen.getByRole("button", { name: "+ New geofence" }));
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
  await screen.findByRole("button", { name: "+ New geofence" });
  expect(await screen.findByText("Restricted Entry")).toBeInTheDocument();
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
