import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import DispatchBoardPage from "./DispatchBoardPage";
import { plannedPaths } from "../../utils/navigation";

const mapMarkers = vi.hoisted(() => [] as Array<{ element: HTMLElement }>);

vi.mock("maplibre-gl", () => {
  class MockMap {
    sources = new Map();
    layers: unknown[] = [];
    handlers = new Map();
    fitBounds = vi.fn();
    jumpTo = vi.fn();
    resize = vi.fn();
    remove = vi.fn();
    setStyle = vi.fn();
    moveLayer = vi.fn();
    dragRotate = { disable: vi.fn() };
    touchZoomRotate = { disableRotation: vi.fn() };
    addSource(id: string, source: Record<string, unknown>) { this.sources.set(id, { ...source, setData: vi.fn() }); }
    getSource(id: string) { return this.sources.get(id); }
    addLayer(layer: unknown) { this.layers.push(layer); }
    getLayer(id: string) { return this.layers.find((l) => (l as { id?: string }).id === id); }
    setLayoutProperty() {}
    on(event: string, cb: (e?: unknown) => void) { this.handlers.set(event, cb); if (event === "load") cb(); return this; }
    off(event: string) { this.handlers.delete(event); return this; }
    addControl() { return this; }
  }
  return { Map: MockMap, Marker: vi.fn((options: { element: HTMLElement }) => { mapMarkers.push(options); return { setLngLat: vi.fn().mockReturnThis(), addTo: vi.fn().mockReturnThis(), remove: vi.fn() }; }), Popup: vi.fn(() => ({ setLngLat: vi.fn().mockReturnThis(), setDOMContent: vi.fn().mockReturnThis(), addTo: vi.fn().mockReturnThis(), remove: vi.fn() })), NavigationControl: vi.fn(), LngLatBounds: vi.fn(() => ({ extend: vi.fn().mockReturnThis() })) };
});

const request = {
  id: "request-1",
  request_number: "TR-001",
  source_system: "HOTEL_MANAGEMENT_SYSTEM",
  external_reference: "HMS-1",
  request_type: "GUEST_TRANSFER",
  request_category: "PASSENGER_TRANSPORT",
  requester_name: "Front Desk",
  requester_contact: "",
  pickup_name: "Oxford Suites",
  pickup_address: "Makati",
  pickup_latitude: "14.5",
  pickup_longitude: "121",
  destination_name: "NAIA",
  destination_address: "Pasay",
  destination_latitude: "14.4",
  destination_longitude: "121.1",
  scheduled_pickup_at: "2026-08-14T02:00:00Z",
  required_vehicle_type: "VAN",
  estimated_duration_minutes: 60,
  passenger_count: 2,
  luggage_count: 1,
  load_description: "",
  load_quantity: null,
  estimated_weight_kg: null,
  handling_instructions: "",
  temperature_requirement: "",
  priority: "NORMAL",
  notes: "",
  status: "READY_FOR_DISPATCH",
  assigned_vehicle: null,
  created_by: "Manager",
  approved_by: "Manager",
  approved_at: "2026-08-13T00:00:00Z",
  created_at: "2026-08-13T00:00:00Z",
  updated_at: "2026-08-13T00:00:00Z",
  latest_event_type: "APPROVED",
  latest_event_at: "2026-08-13T00:00:00Z",
};
const secondRequest = {
  ...request,
  id: "request-2",
  request_number: "TR-002",
  external_reference: "HMS-2",
  pickup_name: "BGC",
  destination_name: "Oxford Suites",
};
const driver = {
  id: 1,
  driver_code: "DRV-001",
  full_name: "Juan Dela Cruz",
  eligibility_status: "ELIGIBLE",
};
const vehicle = {
  id: 1,
  device_id: "VAN-01",
  plate_number: "ABC-123",
  display_name: "Guest Van",
  vehicle_type: "VAN",
  passenger_capacity: 8,
  is_active: true,
  current_location_available: true,
};
const fuelEstimate = {
  status: "UNAVAILABLE",
  reason: "NO_VALID_PREFERRED_PARTNER_PRICE",
  fuel_rate_basis: "FLEET_REFERENCE_BASELINE",
  fuel_rate_lph: "7.0000",
  travel_time_seconds: "600",
  estimated_fuel_liters: "1.1667",
  fuel_type: "DIESEL",
  fuel_grade: "REGULAR_DIESEL",
  price_per_liter: null,
  currency: null,
  price_provider: null,
  price_source_mode: null,
  price_effective_at: null,
  estimated_fuel_cost_php: null,
  fuel_source_timestamp: null,
  history_sample_count: 0,
  fuel_rate_provenance: "CAPSTONE_REFERENCE",
};
const board = {
  summary: {
    approved_requests: 1,
    awaiting_assignment: 1,
    confirmed_assignments: 0,
    ready_for_dispatch: 1,
    optimizer_eligible: 1,
    needs_attention: 0,
    no_eligible_driver: 0,
    no_gis_vehicle: 0,
    schedule_conflict: 0,
  },
  requests: [request],
  assignments: [],
  eligible_drivers: [driver],
  active_vehicles: [vehicle],
  assignment_audit: { "request-1": [] },
  recommendation_fingerprints: { "request-1": "fp-1" },
};
const assignmentFixture = (index: number, overrides = {}) => ({
  id: index,
  transport_request_id: `confirmed-${index}`,
  request_number: `TR-C${index}`,
  vehicle: { ...vehicle, id: index, display_name: `Vehicle ${index}` },
  driver: { ...driver, id: index, full_name: `Driver ${index}` },
  selection_mode: "OPTIMIZED" as const,
  override_reason: "",
  confirmed_by: "Operator",
  confirmed_at: `2026-08-${String(20 - index).padStart(2, "0")}T00:00:00Z`,
  is_accepted: index % 2 === 0,
  accepted_at: index % 2 === 0 ? "2026-08-14T00:05:00Z" : null,
  execution_status: index % 2 === 0 ? "IN_TRANSIT" as const : "ASSIGNED" as const,
  execution_status_label: index % 2 === 0 ? "In Transit" : "Assigned",
  completed_at: null,
  created_at: "2026-08-14T00:00:00Z",
  updated_at: "2026-08-14T00:05:00Z",
  ...overrides,
});
const recommendation = {
  generated_at: "2026-08-14T00:00:00Z",
  optimizer: "GOOGLE_OR_TOOLS",
  routing_source: "TOMTOM",
  requests_considered: 1,
  requests_recommended: 1,
  recommendations: [
    {
      transport_request_id: "request-1",
      request_number: "TR-001",
      recommended_vehicle: vehicle,
      recommended_driver: driver,
      travel_time_seconds: 600,
      distance_meters: 5200,
      traffic_delay_seconds: 60,
      recommendation_token: "signed",
      planning_fingerprint: "fp-1",
      fuel_estimate: fuelEstimate,
      explanation: [
        "Driver eligibility is ELIGIBLE",
        "TomTom route/matrix cell is valid",
      ],
      schedule_context: {
        selected: {
          start: "2026-08-14T02:00:00Z",
          end: "2026-08-14T03:00:00Z",
        },
        driver: { status: "AVAILABLE", windows: [] },
        vehicle: { status: "AVAILABLE", windows: [] },
      },
      gis_preview: {
        status: "METRICS_AVAILABLE",
        vehicle_location: {
          vehicle_id: "VAN-01",
          latitude: 14.5,
          longitude: 121,
        },
        pickup: { latitude: "14.5", longitude: "121", label: "Oxford Suites" },
        destination: { latitude: "14.4", longitude: "121.1", label: "NAIA" },
        geometry: null,
      },
    },
  ],
  unassigned: [],
  candidate_comparison: {
    "request-1": [
      {
        driver,
        vehicle,
        travel_time_seconds: 600,
        distance_meters: 5200,
        traffic_delay_seconds: 60,
        result: "RECOMMENDED",
        fuel_estimate: fuelEstimate,
      },
    ],
  },
  excluded_candidates: {
    "request-1": [
      {
        kind: "VEHICLE",
        name: "Old Van",
        code: "OLD-01",
        reason: "NO_FRESH_TELEMETRY",
        details: ["No fresh telemetry"],
      },
    ],
  },
  comparison_scope: { limit: 50, limited: false },
};
const json = (value: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(value), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
const isOptimization = (input: RequestInfo | URL) =>
  String(input).endsWith("recommendations/");
const isRecommendationRoute = (input: RequestInfo | URL) =>
  String(input).endsWith("recommendation-route/");
const unavailableRecommendationRoute = {
  route: {
    route: null,
    planned_route: null,
    route_status: "TEMPORARILY_UNAVAILABLE",
  },
};
const requestIds = (init?: RequestInit) =>
  JSON.parse(String(init?.body ?? "{}")).request_ids as string[] | undefined;
beforeEach(() => {
  vi.restoreAllMocks();
  mapMarkers.length = 0;
});

test("dispatch board is a real route rather than a planned module", () => {
  expect(plannedPaths.some((item) => item.path === "/dispatch-board")).toBe(
    false,
  );
});

test("renders the real approved queue and honest empty-safe dispatch controls", async () => {
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation((input) =>
      isOptimization(input)
        ? json({
            ...recommendation,
            recommendations: [],
            candidate_comparison: {},
            excluded_candidates: {},
            unassigned: [
              {
                transport_request_id: "request-1",
                request_number: "TR-001",
                reason: "No fresh vehicle telemetry",
              },
            ],
          })
        : json(board),
    );
  render(<DispatchBoardPage />);
  expect(screen.getByText("Loading dispatch board…")).toBeInTheDocument();
  expect(await screen.findByText("TR-001")).toBeInTheDocument();
  const requestScroll = screen.getByRole("region", {
    name: "Dispatch requests",
  });
  expect(requestScroll).toHaveClass("dispatch-queue-list");
  expect(requestScroll.closest(".dispatch-page")).toHaveClass("dispatch-page");
  expect(requestScroll.closest(".dispatch-workspace")).toHaveClass("dispatch-workspace");
  expect(requestScroll.closest(".dispatch-queue")).toHaveClass("dispatch-queue");
  expect(screen.getByText("Recommendation Workspace").closest(".dispatch-recommendation-workspace")).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Assignment Review" })).toHaveClass("dispatch-review");
  expect(screen.getByRole("tab", { name: "Dispatch Queue 1" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tab", { name: "Confirmed Assignments 0" })).toHaveAttribute("aria-selected", "false");
  expect(screen.getByRole("tab", { name: "Dispatch Queue 1" }).closest(".dispatch-view-toolbar")).toBeInTheDocument();
  expect(screen.queryByText("Review ready requests, validate optimizer recommendations, and confirm assignments.")).not.toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Confirmed Assignments" })).not.toBeInTheDocument();
  expect(requestScroll).toHaveAttribute("tabindex", "0");
  expect(requestScroll).toContainElement(screen.getByText("TR-001"));
  expect(
    (await screen.findAllByText("No fresh vehicle telemetry")).length,
  ).toBeGreaterThan(0);
  expect(
    screen.getByRole("button", { name: "Recompute Recommendation" }),
  ).toBeInTheDocument();
  const call = fetchMock.mock.calls.find(([input]) => isOptimization(input));
  expect(requestIds(call?.[1])).toEqual(["request-1"]);
  expect(
    screen.queryByText(/Safety Score|Driver Accepted|Start Trip|Complete Trip/),
  ).not.toBeInTheDocument();
});

test("renders authoritative KPI values as read-only statistics", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) =>
    isOptimization(input)
      ? json({ ...recommendation, recommendations: [], unassigned: [] })
      : json({
          ...board,
          summary: {
            ...board.summary,
            awaiting_assignment: 7,
            optimizer_eligible: 5,
            needs_attention: 2,
            confirmed_assignments: 3,
            no_eligible_driver: 1,
            no_gis_vehicle: 4,
            schedule_conflict: 2,
          },
        }),
  );
  render(<DispatchBoardPage />);
  await screen.findByText("TR-001");
  await waitFor(() =>
    expect(fetchMock.mock.calls.filter(([input]) => isOptimization(input))).toHaveLength(1),
  );
  const expected = [
    ["unassigned", "7", "Ready / Unassigned"],
    ["eligible", "5", "Optimizer Eligible"],
    ["attention", "2", "Needs Attention"],
    ["confirmed", "3", "Confirmed"],
    ["no_driver", "1", "No Eligible Driver"],
    ["no_gis", "4", "No GIS Vehicle"],
    ["conflict", "2", "Schedule Conflict"],
  ];
  for (const [key, value, name] of expected) {
    const card = screen.getByTestId(`dispatch-kpi-${key}`);
    expect(card).toHaveTextContent(value);
    expect(card).toHaveTextContent(name);
    expect(card.tagName).toBe("ARTICLE");
    expect(card).not.toHaveAttribute("role", "button");
    expect(card).not.toHaveAttribute("tabindex");
    fireEvent.click(card);
  }
  expect(screen.queryByRole("button", { name: /Ready \/ Unassigned|Optimizer Eligible|Needs Attention|Confirmed|No Eligible Driver|No GIS Vehicle|Schedule Conflict/ })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /TR-001 Guest Transfer/ })).toHaveClass("selected");
  expect(fetchMock.mock.calls.filter(([input]) => isOptimization(input))).toHaveLength(1);
});

test("shows OR-Tools recommendation with real TomTom metrics and confirms only on click", async () => {
  let confirmed = false;
  const savedAssignment = {
    id: 1,
    transport_request_id: "request-1",
    request_number: "TR-001",
    vehicle,
    driver,
    selection_mode: "OPTIMIZED",
    override_reason: "",
    confirmed_by: "Operator",
    confirmed_at: "2026-08-14T00:01:00Z",
    is_accepted: false,
    accepted_at: null,
    execution_status: "ASSIGNED",
    execution_status_label: "Assigned",
    completed_at: null,
    created_at: "2026-08-14T00:01:00Z",
    updated_at: "2026-08-14T00:01:00Z",
  };
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation((input) => {
      if (isOptimization(input)) return json(recommendation);
      if (String(input).endsWith("confirm/")) {
        confirmed = true;
        return json(savedAssignment, 201);
      }
      return json(
        confirmed
          ? {
              ...board,
              requests: [],
              assignments: [savedAssignment],
              summary: { ...board.summary, awaiting_assignment: 0, confirmed_assignments: 1 },
            }
          : board,
      );
    });
  render(<DispatchBoardPage />);
  await screen.findByText("TR-001");
  expect((await screen.findAllByText("Juan Dela Cruz")).length).toBeGreaterThan(
    0,
  );
  expect(screen.getAllByText("10 min").length).toBeGreaterThan(0);
  expect(screen.getAllByText("5.2 km").length).toBeGreaterThan(0);
  expect(screen.getByText("7.0000 L/h")).toBeInTheDocument();
  expect(screen.getByText("1.1667 L")).toBeInTheDocument();
  expect(screen.getByText("Regular Diesel")).toBeInTheDocument();
  expect(screen.getByText("Fleet Reference Baseline")).toBeInTheDocument();
  expect(screen.getByText("No valid Shell partner price")).toBeInTheDocument();
  expect(screen.getByText(/Recommendation ready · updated/)).toBeInTheDocument();
  expect(
    fetchMock.mock.calls.some((call) => String(call[0]).endsWith("confirm/")),
  ).toBe(false);
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm Recommendation" }),
  );
  let drawer = screen.getByRole("dialog", { name: "Confirm assignment" });
  expect(within(drawer).getByText("TR-001")).toBeInTheDocument();
  expect(within(drawer).getByText("Juan Dela Cruz")).toBeInTheDocument();
  expect(within(drawer).getByText("7.0000 L/h")).toBeInTheDocument();
  expect(within(drawer).getByText("1.1667 L")).toBeInTheDocument();
  expect(within(drawer).getByText("Regular Diesel")).toBeInTheDocument();
  expect(within(drawer).getAllByText("Unavailable")).toHaveLength(2);
  expect(within(drawer).getByText("No valid Shell partner price")).toBeInTheDocument();
  expect(within(drawer).getByRole("button", { name: "Confirm Assignment" })).toBeEnabled();
  expect(
    fetchMock.mock.calls.some((call) => String(call[0]).endsWith("confirm/")),
  ).toBe(false);
  fireEvent.click(within(drawer).getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog", { name: "Confirm assignment" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Confirm Recommendation" }));
  drawer = screen.getByRole("dialog", { name: "Confirm assignment" });
  fireEvent.click(within(drawer).getByRole("button", { name: "Confirm Assignment" }));
  expect(await screen.findByRole("tab", { name: "Confirmed Assignments 1" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Dispatch Queue 0" })).toHaveAttribute("aria-selected", "true");
  expect(within(screen.getByRole("region", { name: "Dispatch requests" })).queryByText("TR-001")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Confirmed Assignments 1" }));
  expect(await screen.findByRole("region", { name: "Confirmed Assignments" })).toBeInTheDocument();
  expect(screen.getAllByText("Awaiting Driver Acceptance").length).toBeGreaterThan(0);
});

test("manual modification requires a reason and identifies no-location vehicles", async () => {
  const noLocation = {
    ...vehicle,
    id: 2,
    device_id: "VAN-02",
    current_location_available: false,
  };
  vi.spyOn(globalThis, "fetch").mockImplementation((input) =>
    isOptimization(input)
      ? json({
          ...recommendation,
          recommendations: [],
          candidate_comparison: {},
          excluded_candidates: {},
          unassigned: [],
        })
      : json({ ...board, active_vehicles: [noLocation] }),
  );
  render(<DispatchBoardPage />);
  await screen.findByText("TR-001");
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Recompute Recommendation" }),
    ).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Manual Override" }));
  fireEvent.change(screen.getByLabelText("Eligible Driver"), {
    target: { value: "1" },
  });
  fireEvent.change(screen.getByLabelText("Valid Vehicle"), {
    target: { value: "2" },
  });
  expect(
    screen.getByRole("option", {
      name: /Current location unavailable — manual assignment only/,
    }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Confirm Manual Assignment" }),
  ).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Override reason"), {
    target: { value: "Guest requirement" },
  });
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Confirm Manual Assignment" }),
    ).toBeEnabled(),
  );
  expect(screen.queryByText(/ETA/)).not.toBeInTheDocument();
});

test("shows number coding checks, exclusions, explanations, and disables blocked manual vehicles", async () => {
  const restricted = { ...vehicle, number_coding:{ status:"RESTRICTED", reason:"Number coding restriction applies to this vehicle for the scheduled pickup time.", plate_last_digit:3 } };
  const unknown = { ...vehicle, id:2, device_id:"VAN-02", plate_number:"NO-DIGIT", number_coding:{ status:"UNKNOWN", reason:"Vehicle plate number has no numeric digit that can be evaluated.", plate_last_digit:null } };
  const exempt = { ...vehicle, id:3, device_id:"VAN-03", number_coding:{ status:"EXEMPT", reason:"A verified vehicle number coding exemption is active.", plate_last_digit:3 } };
  const suspended = { ...vehicle, id:4, device_id:"VAN-04", number_coding:{ status:"SUSPENDED", reason:"A temporary number coding suspension is active.", plate_last_digit:3 } };
  const clear = { ...vehicle, id:5, device_id:"VAN-05", number_coding:{ status:"CLEAR", reason:"Number coding is clear for the scheduled pickup time.", plate_last_digit:3 } };
  const codingRecommendation = { ...recommendation, recommendations:[{ ...recommendation.recommendations[0], explanation:[...recommendation.recommendations[0].explanation, "Number coding: verified exemption"] }], excluded_candidates:{ "request-1":[{ kind:"VEHICLE", name:"Guest Van", code:"VAN-01", reason:"NUMBER_CODING_RESTRICTION", details:[restricted.number_coding.reason] }] } };
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => isOptimization(input) ? json(codingRecommendation) : isRecommendationRoute(input) ? json(unavailableRecommendationRoute) : json({ ...board, summary:{ ...board.summary, number_coding_blocked:2 }, manual_candidates:{ "request-1":{ drivers:[driver], vehicles:[restricted,unknown,exempt,suspended,clear] } } }));
  render(<DispatchBoardPage />);
  await screen.findByText("TR-001");
  await screen.findByText("Why recommended");
  expect(await screen.findByText("2 restricted")).toBeInTheDocument();
  expect(await screen.findByText("Number coding: verified exemption")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name:/Exclusions/ }));
  expect(screen.getByText("Number Coding Restriction")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name:"Manual Override" }));
  expect(screen.getByRole("option", { name:/Number Coding/ })).toBeDisabled();
  expect(screen.getByRole("option", { name:/Needs Verification/ })).toBeDisabled();
  expect(screen.getByRole("option", { name:/Verified Exempt/ })).toBeEnabled();
  expect(screen.getByRole("option", { name:/Coding Suspended/ })).toBeEnabled();
  expect(screen.getByRole("option", { name:/Clear/ })).toBeEnabled();
});

test("renders controlled recommendation errors and backend infeasibility reasons", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) =>
    isOptimization(input)
      ? json({
          ...recommendation,
          recommendations: [],
          requests_recommended: 0,
          unassigned: [
            {
              transport_request_id: "request-1",
              request_number: "TR-001",
              reason: "No fresh vehicle telemetry",
            },
          ],
        })
      : json(board),
  );
  render(<DispatchBoardPage />);
  await screen.findByText("TR-001");
  expect(
    (await screen.findAllByText("No fresh vehicle telemetry")).length,
  ).toBeGreaterThan(0);
});

test("renders explainability, candidates, GIS truth, schedules, and no fabricated safety score", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) =>
    isOptimization(input) ? json(recommendation) : isRecommendationRoute(input) ? json(unavailableRecommendationRoute) : json(board),
  );
  render(<DispatchBoardPage />);
  await screen.findByText("TR-001");
  expect(await screen.findByText("Why recommended")).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Candidate Comparison" })).not.toBeInTheDocument();
  expect(screen.getByText("GIS Recommendation Preview")).toBeInTheDocument();
  expect(await screen.findByText("Route geometry temporarily unavailable")).toBeInTheDocument();
  expect(screen.getByText("Recommended vehicle position unavailable.")).toBeInTheDocument();
  expect(mapMarkers.some(({ element }) =>
    element.getAttribute("aria-label")?.startsWith("Recommended vehicle:"),
  )).toBe(false);
  expect(screen.getByText("Resource Schedule")).toBeInTheDocument();
  expect(screen.getByText(/Driver timeline · AVAILABLE/)).toBeInTheDocument();
  expect(screen.getByText(/Vehicle timeline · AVAILABLE/)).toBeInTheDocument();
  const review = screen.getByRole("region", { name: "Assignment Review" });
  fireEvent.click(screen.getByRole("tab", { name: "Candidates (1)" }));
  expect(screen.getByRole("region", { name: "Candidate Comparison" })).toBeInTheDocument();
  expect(screen.getByText("Recommended")).toBeInTheDocument();
  expect(review).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Exclusions (1)" }));
  expect(screen.getByText("No Fresh Telemetry")).toBeInTheDocument();
  expect(screen.queryByText("Old Van")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /No Fresh Telemetry/ }));
  expect(screen.getByText("Old Van")).toBeInTheDocument();
  expect(review).toBeInTheDocument();
  expect(screen.queryByText(/Safety Score/)).not.toBeInTheDocument();
  expect(screen.queryByText("Consolidation Opportunity")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Analyze Consolidation" })).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([input]) =>
    String(input).includes("consolidation-recommendations")
  )).toBe(false);
});

test("fetches both road legs only for the selected recommendation", async () => {
  const roadLeg = {
    geometry: { type: "LineString", coordinates: [[121, 14.5], [121.02, 14.56]] },
    distance_meters: 5200,
    duration_seconds: 600,
    traffic_delay_seconds: 60,
    departure_time: "2026-08-14T02:00:00Z",
    arrival_time: "2026-08-14T02:10:00Z",
    traffic_mode: "live",
  };
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) =>
    isOptimization(input)
      ? json(recommendation)
      : isRecommendationRoute(input)
        ? json({ route: { route: roadLeg, planned_route: roadLeg, route_status: "AVAILABLE", position_state: "CURRENT", vehicle_position: { latitude: 14.5, longitude: 121, recorded_at: "2026-08-14T01:59:00Z", is_stale: false, source: "GNSS" } } })
        : json(board),
  );

  render(<DispatchBoardPage />);
  await waitFor(() =>
    expect(fetchMock.mock.calls.some(([input]) => isRecommendationRoute(input))).toBe(true),
  );
  expect(await screen.findByText(/Road route preview/)).toBeInTheDocument();
  expect(screen.getByLabelText("Recommendation map legend")).toHaveTextContent(
    "Recommended VehiclePickup — Oxford SuitesDestination — NAIA",
  );
  const activeMarkers = mapMarkers.map(({ element }) => element);
  expect(activeMarkers.some((element) => element.title === "Pickup: Oxford Suites")).toBe(true);
  expect(activeMarkers.some((element) => element.title === "Destination: NAIA")).toBe(true);
  const vehicleMarker = activeMarkers.find((element) =>
    element.getAttribute("aria-label")?.startsWith("Recommended vehicle:"),
  );
  expect(vehicleMarker).toHaveClass("request-map-fleet-marker");
  expect(vehicleMarker).toHaveClass("request-map-marker--live");
  expect(vehicleMarker).toHaveAttribute("title", "Guest Van · ABC-123 · Current");
  expect(activeMarkers.some((element) =>
    element.classList.contains("request-map-marker--numbered"),
  )).toBe(false);
  const routeCalls = fetchMock.mock.calls.filter(([input]) => isRecommendationRoute(input));
  expect(routeCalls).toHaveLength(1);
  expect(JSON.parse(String(routeCalls[0][1]?.body))).toEqual({
    transport_request_id: "request-1",
    vehicle_id: 1,
    driver_id: 1,
    recommendation_token: "signed",
  });
});

test("shows automatic optimization loading without any automatic confirmation", async () => {
  let resolveOptimization: (value: Response) => void = () => {};
  const pending = new Promise<Response>((resolve) => {
    resolveOptimization = resolve;
  });
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation((input) =>
      isOptimization(input) ? pending : json(board),
    );
  render(<DispatchBoardPage />);
  await screen.findByText("TR-001");
  expect(await screen.findByRole("status", { name: "Loading" })).toHaveTextContent(
    "Calculating recommendation…",
  );
  expect(
    screen.queryByRole("button", { name: "Confirm Recommendation" }),
  ).not.toBeInTheDocument();
  expect(
    fetchMock.mock.calls.some(([input]) => String(input).endsWith("confirm/")),
  ).toBe(false);
  resolveOptimization(await json(recommendation));
  expect(
    await screen.findByRole("button", { name: "Confirm Recommendation" }),
  ).toBeInTheDocument();
});

test("changing approved selection optimizes only the new request and ignores a stale prior response", async () => {
  let resolveFirst: (value: Response) => void = () => {};
  const firstPending = new Promise<Response>((resolve) => {
    resolveFirst = resolve;
  });
  const secondRecommendation = {
    ...recommendation,
    recommendations: [
      {
        ...recommendation.recommendations[0],
        transport_request_id: "request-2",
        request_number: "TR-002",
      },
    ],
    candidate_comparison: {
      "request-2": recommendation.candidate_comparison["request-1"],
    },
    excluded_candidates: { "request-2": [] },
  };
  const twoRequestBoard = {
    ...board,
    requests: [request, secondRequest],
    summary: {
      ...board.summary,
      approved_requests: 2,
      awaiting_assignment: 2,
      optimizer_eligible: 2,
    },
    assignment_audit: { "request-1": [], "request-2": [] },
    recommendation_fingerprints: {
      "request-1": "fp-1",
      "request-2": "fp-1",
    },
  };
  const calls: string[][] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    if (!isOptimization(input)) return json(twoRequestBoard);
    const ids = requestIds(init) ?? [];
    calls.push(ids);
    return ids[0] === "request-1" ? firstPending : json(secondRecommendation);
  });
 render(<DispatchBoardPage />);
 await screen.findByText("TR-001");
 await waitFor(() => expect(calls).toEqual([["request-1"]]));
 fireEvent.click(screen.getByRole("button", { name: /TR-002 Guest Transfer/ }));
 expect(
   await screen.findByRole("heading", { level: 2, name: "TR-002" }),
 ).toBeInTheDocument();
  resolveFirst(await json(recommendation));
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { level: 2, name: "TR-002" }),
    ).toBeInTheDocument(),
  );
  expect(calls).toEqual([["request-1"], ["request-2"]]);
});

test("defensively removes already confirmed requests from the optimizer queue", async () => {
  const ready = { ...request, status: "READY_FOR_DISPATCH" };
  const confirmed = {
    ...board,
    requests: [ready],
    assignments: [
      {
        id: 1,
        transport_request_id: "request-1",
        request_number: "TR-001",
        vehicle,
        driver,
        selection_mode: "MANUAL",
        override_reason: "Fixture",
        confirmed_by: "Operator",
        confirmed_at: "2026-08-14T00:01:00Z",
        is_accepted: true,
        accepted_at: "2026-08-14T00:05:00Z",
        execution_status: "COMPLETED",
        execution_status_label: "Completed",
        completed_at: "2026-08-14T01:05:00Z",
        created_at: "2026-08-14T00:01:00Z",
        updated_at: "2026-08-14T00:01:00Z",
      },
    ],
  };
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(() => json(confirmed));
  render(<DispatchBoardPage />);
  expect(
    await screen.findByText("No requests in this operational bucket."),
  ).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Dispatch requests" })).queryByText("TR-001")).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([input]) => isOptimization(input))).toBe(
    false,
  );
  expect(
    screen.getByRole("button", { name: "Recompute Recommendation" }),
  ).toBeDisabled();
  expect(
    screen.queryByRole("button", { name: "Modify Assignment" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Confirm Manual Assignment" }),
  ).not.toBeInTheDocument();
});

test("renders confirmed assignments with fifteen-row pagination in API order", async () => {
  const assignments = Array.from({ length: 16 }, (_, index) => assignmentFixture(index + 1));
  vi.spyOn(globalThis, "fetch").mockImplementation(() =>
    json({
      ...board,
      requests: [],
      assignments,
      summary: { ...board.summary, awaiting_assignment: 0, confirmed_assignments: 16 },
      assignment_audit: Object.fromEntries(assignments.map((item) => [item.transport_request_id, []])),
      recommendation_fingerprints: {},
    }),
  );

  render(<DispatchBoardPage />);
  const queueTab = await screen.findByRole("tab", { name: "Dispatch Queue 0" });
  const confirmedTab = screen.getByRole("tab", { name: "Confirmed Assignments 16" });
  expect(queueTab).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("Recommendation Workspace")).toBeInTheDocument();
  const optimizationCalls = vi.mocked(globalThis.fetch).mock.calls.filter(([input]) => isOptimization(input)).length;
  fireEvent.click(confirmedTab);
  const list = await screen.findByRole("region", { name: "Confirmed Assignments" });
  expect(screen.queryByText("Recommendation Workspace")).not.toBeInTheDocument();
  expect(list).toHaveTextContent("Confirmed Assignments (16)");
  expect(list).toHaveTextContent("Showing 1–15 of 16");
  expect(within(list).getAllByRole("row")).toHaveLength(16);
  expect(within(list).getByText("TR-C1")).toBeInTheDocument();
  expect(within(list).queryByText("TR-C16")).not.toBeInTheDocument();
  expect(within(list).getAllByText("Awaiting Driver Acceptance")[0]).toHaveAttribute("data-status", "awaiting");
  expect(within(list).getAllByText("In Transit").length).toBeGreaterThan(0);
  expect(within(list).getByText("TR-C1").compareDocumentPosition(within(list).getByText("TR-C2")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

  fireEvent.click(within(list).getByRole("button", { name: "Next" }));
  expect(within(list).getByText("Showing 16–16 of 16")).toBeInTheDocument();
  expect(within(list).getByText("TR-C16")).toBeInTheDocument();
  expect(within(list).getByRole("button", { name: "Next" })).toBeDisabled();
  expect(within(list).getByRole("button", { name: "Previous" })).toBeEnabled();

  fireEvent.click(within(list).getByRole("button", { name: "View" }));
  const review = screen.getByRole("complementary", { name: "Confirmed Assignment Details" });
  expect(within(review).getByText("Confirmed Assignment")).toBeInTheDocument();
  expect(within(review).getByText("TR-C16")).toBeInTheDocument();
  expect(within(review).getByText("Resource Schedule")).toBeInTheDocument();
  fireEvent.click(queueTab);
  expect(screen.getByText("Recommendation Workspace").closest(".dispatch-workspace")).toBeInTheDocument();
  expect(vi.mocked(globalThis.fetch).mock.calls.filter(([input]) => isOptimization(input))).toHaveLength(optimizationCalls);
});

test("hides confirmed assignment pagination controls for fifteen or fewer rows", async () => {
  const assignments = Array.from({ length: 15 }, (_, index) => assignmentFixture(index + 1));
  vi.spyOn(globalThis, "fetch").mockImplementation(() =>
    json({
      ...board,
      requests: [],
      assignments,
      summary: { ...board.summary, awaiting_assignment: 0, confirmed_assignments: 15 },
      assignment_audit: {},
      recommendation_fingerprints: {},
    }),
  );

  render(<DispatchBoardPage />);
  fireEvent.click(await screen.findByRole("tab", { name: "Confirmed Assignments 15" }));
  const list = await screen.findByRole("region", { name: "Confirmed Assignments" });
  expect(within(list).getAllByRole("row")).toHaveLength(16);
  expect(within(list).queryByRole("navigation", { name: "Confirmed assignments pagination" })).not.toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Latest confirmed assignment" })).not.toBeInTheDocument();
});

test("shows a compact empty confirmed assignments tab", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) =>
    isOptimization(input) ? json(recommendation) : json(board),
  );
  render(<DispatchBoardPage />);
  const confirmedTab = await screen.findByRole("tab", { name: "Confirmed Assignments 0" });
  await waitFor(() =>
    expect(fetchMock.mock.calls.filter(([input]) => isOptimization(input))).toHaveLength(1),
  );
  fireEvent.click(confirmedTab);
  expect(screen.getByText("No confirmed assignments yet.")).toHaveClass("dispatch-confirmed-empty");
  expect(screen.queryByText("Recommendation Workspace")).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.filter(([input]) => isOptimization(input))).toHaveLength(1);
});

test("defensively excludes approved and non-ready requests from the queue", async () => {
  const nonReadyBoard = {
    ...board,
    requests: [
      { ...request, id: "approved", status: "APPROVED" },
      { ...request, id: "pending", status: "FOR_APPROVAL" },
      { ...request, id: "completed", status: "COMPLETED" },
    ],
    recommendation_fingerprints: {},
  };
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(() => json(nonReadyBoard));

  render(<DispatchBoardPage />);

  expect(
    await screen.findByText("No requests in this operational bucket."),
  ).toBeInTheDocument();
  expect(screen.queryByText("TR-001")).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([input]) => isOptimization(input))).toBe(
    false,
  );
  expect(
    screen.getByRole("button", { name: "Recompute Recommendation" }),
  ).toBeDisabled();
});

test("keeps auto-optimization errors out of the layout and allows explicit retry", async () => {
  let attempts = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    if (!isOptimization(input)) return json(board);
    attempts += 1;
    return attempts === 1
      ? json({ detail: "Dispatch matrix is temporarily unavailable." }, 502)
      : json(recommendation);
  });
  render(<DispatchBoardPage />);
  await screen.findByText("TR-001");
  await waitFor(() => expect(attempts).toBe(1));
  expect(
    screen.queryByText("Unable to compute recommendation."),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Recompute Recommendation" }));
  expect(
    await screen.findByRole("button", { name: "Confirm Recommendation" }),
  ).toBeInTheDocument();
  expect(attempts).toBe(2);
});

test("renders a truthful Smart Consolidation recommendation and keeps it non-persistent", async () => {
  const delivery = {
    ...request,
    request_type: "SUPPLIER_PICKUP",
    request_category: "DELIVERY_LOGISTICS",
    passenger_count: 0,
    estimated_weight_kg: "400.00",
    load_description: "Supplies",
  };
  const deliveryBoard = { ...board, requests: [delivery] };
  const consolidation = {
    generated_at: "2026-08-14T00:00:00Z",
    optimizer: "GOOGLE_OR_TOOLS_ROUTING_MODEL",
    routing_source: "TOMTOM",
    candidate_limit: 4,
    exclusions: [],
    recommendation: {
      request_ids: ["request-1", "request-2"],
      requests: [
        delivery,
        {
          ...delivery,
          id: "request-2",
          request_number: "TR-002",
          estimated_weight_kg: "300.00",
        },
      ],
      driver,
      vehicle,
      route: {
        stops: [
          {
            sequence: 1,
            request_id: "request-1",
            request_number: "TR-001",
            stop_type: "PICKUP",
            label: "Oxford Suites",
            latitude: "14.5",
            longitude: "121",
            load_change_kg: "400.00",
          },
          {
            sequence: 2,
            request_id: "request-2",
            request_number: "TR-002",
            stop_type: "PICKUP",
            label: "BGC",
            latitude: "14.5",
            longitude: "121",
            load_change_kg: "300.00",
          },
          {
            sequence: 3,
            request_id: "request-1",
            request_number: "TR-001",
            stop_type: "DELIVERY",
            label: "NAIA",
            latitude: "14.4",
            longitude: "121.1",
            load_change_kg: "-400.00",
          },
          {
            sequence: 4,
            request_id: "request-2",
            request_number: "TR-002",
            stop_type: "DELIVERY",
            label: "Oxford Suites",
            latitude: "14.4",
            longitude: "121.1",
            load_change_kg: "-300.00",
          },
        ],
        peak_load_kg: "700.00",
        capacity_kg: "1000.00",
        capacity_utilization_percent: 70,
        separate: {
          vehicles: 2,
          travel_time_seconds: 5640,
          distance_meters: 61000,
        },
        consolidated: {
          vehicles: 1,
          travel_time_seconds: 4320,
          distance_meters: 43000,
        },
        difference: {
          vehicles: 1,
          travel_time_seconds: 1320,
          distance_meters: 18000,
        },
      },
      explanation: ["Peak load remains within payload capacity."],
      recommendation_token: "signed-consolidation",
      geometry: null,
    },
  };
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation((input) =>
      String(input).includes("consolidation-recommendations")
        ? json(consolidation)
        : isOptimization(input)
          ? json({
              ...recommendation,
              recommendations: [
                {
                  ...recommendation.recommendations[0],
                  recommended_vehicle: vehicle,
                },
              ],
            })
          : json(deliveryBoard),
    );
  render(<DispatchBoardPage />);
  expect(
    await screen.findByText("2 compatible delivery requests"),
  ).toBeInTheDocument();
  expect(screen.getByText("Consolidation Opportunity")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Analyze Consolidation" })).not.toBeInTheDocument();
  expect(screen.getByText("TR-002")).toBeInTheDocument();
  expect(screen.getByText("94 min")).toBeInTheDocument();
  expect(screen.getByText("72 min")).toBeInTheDocument();
  expect(screen.getByText("22 min")).toBeInTheDocument();
  expect(screen.queryByText("700.00 / 1000.00 kg")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Review Consolidation" }));
  expect(screen.getByText("700.00 / 1000.00 kg")).toBeInTheDocument();
  expect(
    screen.getByText(/Multi-stop geometry unavailable/),
  ).toBeInTheDocument();
  expect(
    screen.queryByText(/₱|fuel saved|emissions saved/i),
  ).not.toBeInTheDocument();
  expect(
    fetchMock.mock.calls.some(([input]) =>
      String(input).includes("consolidations/confirm"),
    ),
  ).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Keep Separate" }));
  expect(
    screen.queryByText("2 compatible delivery requests"),
  ).not.toBeInTheDocument();
  expect(
    fetchMock.mock.calls.some(([input]) =>
      String(input).includes("consolidations/confirm"),
    ),
  ).toBe(false);
});

test("automatically analyzes delivery requests and renders nothing for no result", async () => {
  const delivery = {
    ...request,
    request_type: "SUPPLIER_PICKUP",
    request_category: "DELIVERY_LOGISTICS",
    passenger_count: 0,
    estimated_weight_kg: "400.00",
    load_description: "Supplies",
  };
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) =>
    String(input).includes("consolidation-recommendations")
      ? json({
          generated_at: "2026-08-14T00:00:00Z",
          optimizer: "GOOGLE_OR_TOOLS_ROUTING_MODEL",
          routing_source: "TOMTOM",
          candidate_limit: 4,
          recommendation: null,
          exclusions: ["TR-002: Combined load exceeds vehicle payload."],
        })
      : isOptimization(input)
        ? json(recommendation)
        : json({ ...board, requests: [delivery] }),
  );
  render(<DispatchBoardPage />);
  expect(await screen.findByText("Why recommended")).toBeInTheDocument();
  await waitFor(() => expect(fetchMock.mock.calls.some(([input]) =>
    String(input).includes("consolidation-recommendations")
  )).toBe(true));
  expect(screen.queryByText("Consolidation Opportunity")).not.toBeInTheDocument();
  expect(screen.queryByText("No feasible consolidation opportunity.")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Analyze Consolidation" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Confirm Recommendation" })).toBeEnabled();
});

test("failed automatic consolidation stays silent and leaves recommendation usable", async () => {
  const delivery = {
    ...request,
    request_type: "SUPPLIER_PICKUP",
    request_category: "DELIVERY_LOGISTICS",
    passenger_count: 0,
    estimated_weight_kg: "400.00",
  };
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) =>
    String(input).includes("consolidation-recommendations")
      ? json({ detail: "Temporarily unavailable" }, 502)
      : isOptimization(input)
        ? json(recommendation)
        : json({ ...board, requests: [delivery] }),
  );
  render(<DispatchBoardPage />);
  expect(await screen.findByText("Why recommended")).toBeInTheDocument();
  await waitFor(() => expect(fetchMock.mock.calls.some(([input]) =>
    String(input).includes("consolidation-recommendations")
  )).toBe(true));
  expect(screen.queryByText("Consolidation Opportunity")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Analyze Consolidation" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Confirm Recommendation" })).toBeEnabled();
  expect(screen.queryByText(/Unable to analyze consolidation/i)).not.toBeInTheDocument();
});
