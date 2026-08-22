import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import App from "../../App";
import type { Role } from "../../services/auth";
import RequestMap from "./components/RequestMap";
import LocationAutocomplete from "./components/LocationAutocomplete";
import { PriorityChip, WorkflowStatusBadge } from "./components/RequestIndicators";
import { canCancelRequest, canEditRequest, canResubmitRequest } from "./requestActionRules";
import { priorities, statuses, type TransportRequestBase } from "./types";

const auth = vi.hoisted(() => ({
  user: { id: 1, username: "staff", display_name: "Staff User", role: "FLEET_MANAGER" as Role } as { id: number; username: string; display_name: string; role: Role } | null,
  loading: false, signIn: vi.fn(), signOut: vi.fn(), expire: vi.fn(),
}));
vi.mock("../../AuthContext", () => ({ useAuth: () => auth }));
type MockMapEvent = { error?: Error; point?: { x: number; y: number }; lngLat?: { lng: number; lat: number } };
type MockMapLayer = { id: string; source?: string; paint?: Record<string, unknown>; layout?: Record<string, string> };
type MockMapSource = Record<string, unknown> & { tiles: string[]; setData: ReturnType<typeof vi.fn> };
type MockMapOptions = Record<string, unknown> & {
  style: string;
  transformRequest: (url: string) => { url: string; headers?: Record<string, string> };
};
type MockMarker = { position?: [number, number]; removed: boolean; options: { element: HTMLElement }; remove: () => void };
type MockPopup = { position?: [number, number]; content?: HTMLElement; removed: boolean; remove: () => void };
type MockMapInstance = {
  options: MockMapOptions; sources: Map<string, MockMapSource>; layers: MockMapLayer[];
  layout: Map<string, string>; handlers: Map<string, (event?: MockMapEvent) => void>;
  fitBounds: ReturnType<typeof vi.fn>; jumpTo: ReturnType<typeof vi.fn>; resize: ReturnType<typeof vi.fn>;
  remove: ReturnType<typeof vi.fn>; setStyle: ReturnType<typeof vi.fn>;
};
const maplibre = vi.hoisted(() => ({ instances: [] as MockMapInstance[], markers: [] as MockMarker[], popups: [] as MockPopup[], controls: [] as unknown[], autoLoad: true, controlsAvailable: true, failConstruction: false }));
const latestMap = () => {
  const map = maplibre.instances.at(-1);
  if (!map) throw new Error("Expected a MapLibre test instance.");
  return map;
};
vi.mock("maplibre-gl", () => {
  class Bounds {
    points: [number, number][];
    constructor(first: [number, number]) { this.points = [first]; }
    extend(point: [number, number]) { this.points.push(point); return this; }
  }
  class Marker {
    position?: [number, number]; removed = false;
    constructor(public options: { element: HTMLElement }) { maplibre.markers.push(this); }
    setLngLat(position: [number, number]) { this.position = position; return this; }
    addTo() { return this; }
    remove() { this.removed = true; }
  }
  class Popup {
    position?: [number, number]; content?: HTMLElement; removed = false;
    constructor(public options: Record<string, unknown>) { maplibre.popups.push(this); }
    setLngLat(position: [number, number]) { this.position = position; return this; }
    setDOMContent(content: HTMLElement) { this.content = content; return this; }
    addTo() { return this; }
    remove() { this.removed = true; }
  }
  class Map {
    sources = new MapStore(); layers: MockMapLayer[] = []; layout = new globalThis.Map<string, string>(); handlers = new globalThis.Map<string, (event?: MockMapEvent) => void>();
    fitBounds = vi.fn(); jumpTo = vi.fn(); resize = vi.fn(); remove = vi.fn();
    dragRotate = maplibre.controlsAvailable ? { disable: vi.fn() } : undefined;
    touchZoomRotate = maplibre.controlsAvailable ? { disableRotation: vi.fn() } : undefined;
    constructor(public options: MockMapOptions) { if (maplibre.failConstruction) throw new Error("WebGL unavailable"); maplibre.instances.push(this); }
    on(event: string, callback: (event?: MockMapEvent) => void) { this.handlers.set(event, callback); if (event === "load" && maplibre.autoLoad) callback(); return this; }
    off(event: string) { this.handlers.delete(event); return this; }
    addControl(control: unknown) { maplibre.controls.push(control); return this; }
    addSource(id: string, source: Record<string, unknown> & { tiles?: string[] }) { this.sources.set(id, { ...source, tiles: source.tiles ?? [], setData: vi.fn() }); }
    getSource(id: string) { return this.sources.get(id)!; }
    addLayer(layer: MockMapLayer) { this.layers.push(layer); }
    getLayer(id: string) { return this.layers.find(layer => layer.id === id); }
    setLayoutProperty(id: string, _property: string, value: string) { this.layout.set(id, value); }
    setStyle = vi.fn((style: string) => { this.options.style = style; this.sources.clear(); this.layers = []; this.handlers.get("style.load")?.(); });
  }
  class MapStore extends globalThis.Map<string, MockMapSource> {}
  class NavigationControl { constructor(public options: unknown) {} }
  const api = { Map, Marker, Popup, LngLatBounds: Bounds, NavigationControl };
  return { default: api, ...api };
});

const request = {
  id: "8f97093a-17bd-49a0-bf64-8ccbd533c8d5", request_number: "TR-20260806-A1B2C3",
  source_system: "HOTEL_MANAGEMENT_SYSTEM", external_reference: "HMS-1", request_type: "AIRPORT_PICKUP",
  request_category: "PASSENGER_TRANSPORT",
  requester_name: "Front Desk", requester_contact: "100", pickup_name: "NAIA Terminal 3", pickup_address: "Pasay",
  pickup_latitude: "14.508600", pickup_longitude: "121.019800", destination_name: "Oxford Suites Makati",
  destination_address: "Makati", destination_latitude: "14.565200", destination_longitude: "121.028600",
  scheduled_pickup_at: "2026-08-06T10:00:00Z", required_vehicle_type: "VAN", estimated_duration_minutes: 60,
  passenger_count: 2, luggage_count: 1, load_description: "", load_quantity: null, estimated_weight_kg: null,
  handling_instructions: "", temperature_requirement: "", priority: "HIGH", notes: "", status: "FOR_APPROVAL", assigned_vehicle: null,
  created_by: "Manager", approved_by: null, approved_at: null, created_at: "2026-08-06T01:00:00Z", updated_at: "2026-08-06T01:00:00Z",
  latest_event_type: "CREATED", latest_event_at: "2026-08-06T01:00:00Z",
  events: [{ id: 1, event_type: "CREATED", previous_status: "", new_status: "FOR_APPROVAL", performed_by: "Manager", note: "", created_at: "2026-08-06T01:00:00Z" }],
};
const summary = { total: 1, for_approval: 1, needs_more_details: 0, approval_queue: 1, dispatch_queue: 0, approved_unassigned: 0, approved_assigned: 0, ready_for_dispatch: 0, scheduled_today: 1, high_priority: 1 };
const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
const errorJson = (body: unknown, status = 400) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
const localDate = (value: Date) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;

beforeEach(() => {
  maplibre.instances.length = 0; maplibre.markers.length = 0; maplibre.popups.length = 0; maplibre.controls.length = 0; maplibre.autoLoad = true; maplibre.controlsAvailable = true; maplibre.failConstruction = false; localStorage.clear(); vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "");
  auth.user = { id: 1, username: "staff", display_name: "Staff User", role: "FLEET_MANAGER" };
  vi.spyOn(globalThis, "fetch").mockImplementation(input => {
    const url = String(input);
    if (url.endsWith("summary/")) return json(summary);
    if (url.endsWith(`${request.id}/route/`)) return json({ request_id: request.id, traffic_mode: "live", distance_meters: 12400, duration_seconds: 1860, traffic_delay_seconds: 360, departure_time: "2026-08-07T10:00:00+08:00", arrival_time: "2026-08-07T10:31:00+08:00", geometry: { type: "LineString", coordinates: [[121.0198, 14.5086], [121.025, 14.54], [121.0286, 14.5652]] } });
    if (url.includes("calendar/?")) return json({ start: "2026-08-03", end: "2026-08-09", timezone: "Asia/Manila", results: [{ ...request, calendar_date: localDate(new Date()), planning_end_at: "2026-08-06T11:00:00Z", vehicle_conflict: true, conflicting_requests: ["TR-OTHER"] }] });
    if (url.includes("/vehicles/")) return json({ count: 0, next: null, previous: null, results: [] });
    if (url.endsWith(`${request.id}/`)) return json(request);
    return json({ count: 1, next: null, previous: null, results: [request] });
  });
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllEnvs(); vi.unstubAllGlobals(); });
const renderAt = (path: string) => render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);

describe("Sprint 4 Transport Requests corrections", () => {
  test("Places autocomplete waits for three characters, debounces, and cancels stale searches", async () => {
    vi.useFakeTimers(); const fetchMock = vi.mocked(globalThis.fetch); const calls: { query: string; signal?: AbortSignal }[] = [];
    fetchMock.mockImplementation((_input, init) => { const body = JSON.parse(String(init?.body)); calls.push({ query: body.query, signal: init?.signal ?? undefined }); return json({ results: [{ id: body.query, type: "poi", title: body.query, subtitles: ["Makati"] }] }); });
    render(<LocationAutocomplete kind="pickup" errors={{}} />); const input = screen.getByLabelText("Pickup address");
    fireEvent.change(input, { target: { value: "Ox" } }); await act(async () => { vi.advanceTimersByTime(350); }); expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: "Oxf" } }); await act(async () => { vi.advanceTimersByTime(300); await Promise.resolve(); }); expect(calls[0].query).toBe("Oxf");
    fireEvent.change(input, { target: { value: "Oxford" } }); expect(calls[0].signal?.aborted).toBe(true); expect(screen.getByText("Searching locations…")).toBeInTheDocument();
    await act(async () => { vi.advanceTimersByTime(300); await Promise.resolve(); await Promise.resolve(); }); expect(screen.getByText("Oxford")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("api.tomtom.com"))).toBe(false);
  });
  test("Places selection reuses its session, populates coordinates, and manual edits clear them", async () => {
    const session = "11111111-1111-4111-8111-111111111111"; vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue(session);
    const fetchMock = vi.mocked(globalThis.fetch); fetchMock.mockImplementation(input => String(input).includes("places/suggest/") ? json({ results: [{ id: "oxford", type: "poi", title: "Oxford Suites Makati", subtitles: ["Poblacion, Makati"] }] }) : json({ id: "oxford", type: "poi", title: "Oxford Suites Makati", subtitles: ["Poblacion, Makati"], display_address: "Poblacion, Makati, Philippines", latitude: 14.5652, longitude: 121.0286 }));
    render(<form data-testid="location-form"><LocationAutocomplete kind="pickup" errors={{}} /></form>); const input = screen.getByLabelText("Pickup address"); fireEvent.change(input, { target: { value: "Oxford" } });
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 320)); }); fireEvent.keyDown(input, { key: "ArrowDown" }); fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(input).toHaveValue("Poblacion, Makati, Philippines")); expect(screen.getByLabelText("Pickup name")).toHaveValue("Oxford Suites Makati");
    const form = screen.getByTestId("location-form") as HTMLFormElement; let data = new FormData(form); expect(data.get("pickup_latitude")).toBe("14.5652"); expect(data.get("pickup_longitude")).toBe("121.0286");
    const suggestCall = fetchMock.mock.calls.find(([url]) => String(url).includes("places/suggest/"))!; const detailCall = fetchMock.mock.calls.find(([url]) => String(url).includes("places/details/"))!;
    expect(JSON.parse(String(suggestCall[1]?.body)).session_id).toBe(session); expect(String(detailCall[0])).toContain(`session_id=${session}`);
    fireEvent.change(input, { target: { value: "Another address" } }); data = new FormData(form); expect(data.get("pickup_latitude")).toBe(""); expect(data.get("pickup_longitude")).toBe("");
  });
  test("Destination supports no-results, failures, and Escape without blocking the form", async () => {
    vi.useFakeTimers(); const fetchMock = vi.mocked(globalThis.fetch); fetchMock.mockImplementation(() => json({ results: [] })); render(<LocationAutocomplete kind="destination" errors={{}} />); const input = screen.getByLabelText("Destination address"); fireEvent.change(input, { target: { value: "Unknown" } });
    await act(async () => { vi.advanceTimersByTime(300); await Promise.resolve(); await Promise.resolve(); }); expect(screen.getByText("No matching locations found.")).toBeInTheDocument(); fireEvent.keyDown(input, { key: "Escape" }); expect(screen.queryByText("No matching locations found.")).not.toBeInTheDocument();
    fetchMock.mockImplementation(() => errorJson({ detail: "Unavailable" }, 503)); fireEvent.change(input, { target: { value: "Unavailable place" } }); await act(async () => { vi.advanceTimersByTime(300); await Promise.resolve(); await Promise.resolve(); }); expect(screen.getByText("Location search temporarily unavailable.")).toBeInTheDocument();
  });
  test("Create submits coordinates resolved independently for Pickup and Destination", async () => {
    const fetchMock = vi.mocked(globalThis.fetch); fetchMock.mockImplementation((input, init) => { const url = String(input); if (url.includes("places/suggest/")) { const query = JSON.parse(String(init?.body)).query; return json({ results: [{ id: query, type: "address", title: query, subtitles: [`${query} subtitle`] }] }); } if (url.includes("places/details/")) { const pickup = url.includes("Pickup%20place"); return json({ id: pickup ? "Pickup place" : "Destination place", type: "address", title: pickup ? "Pickup selected" : "Destination selected", subtitles: [], display_address: pickup ? "Pickup address, PH" : "Destination address, PH", latitude: pickup ? 14.5 : 14.6, longitude: pickup ? 121.0 : 121.1 }); } if (url.endsWith("/transport-requests/") && init?.method === "POST") return json({ ...request, id: "created-id" }); return json({}); });
    renderAt("/transport-requests/new"); fireEvent.change(screen.getByLabelText("Requester name"), { target: { value: "Front Desk" } }); fireEvent.change(screen.getByLabelText("Scheduled pickup"), { target: { value: "2026-08-08T10:00" } });
    for (const [label, value, resolved] of [["Pickup address", "Pickup place", "Pickup address, PH"], ["Destination address", "Destination place", "Destination address, PH"]] as const) { const input = screen.getByLabelText(label); fireEvent.change(input, { target: { value } }); await act(async () => { await new Promise(resolve => setTimeout(resolve, 320)); }); fireEvent.click(await screen.findByRole("option", { name: new RegExp(value) })); await waitFor(() => expect(input).toHaveValue(resolved)); }
    fireEvent.submit(screen.getByRole("button", { name: "Create Request" }).closest("form")!);
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith("/transport-requests/") && init?.method === "POST")).toBe(true));
    const createCall = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith("/transport-requests/") && init?.method === "POST")!; const payload = JSON.parse(String(createCall[1]?.body));
    expect(payload).toMatchObject({ source_system: "MANUAL_STAFF_ENTRY", request_category: "PASSENGER_TRANSPORT", pickup_latitude: "14.5", pickup_longitude: "121", destination_latitude: "14.6", destination_longitude: "121.1" });
  });
  test("development delivery intake uses delivery fields and zero passenger semantics", async () => {
    const fetchMock = vi.mocked(globalThis.fetch);
    fetchMock.mockImplementation((_input, init) => init?.method === "POST" ? json({ ...request, id: "delivery-created" }) : json({}));
    renderAt("/transport-requests/new");
    expect(screen.getByText("Development intake — production requests are normally received from connected hotel and restaurant systems.")).toBeInTheDocument();
    expect(screen.getByText(/Recorded as manual staff entry/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Request type"), { target: { value: "FOOD_DELIVERY" } });
    expect(screen.queryByLabelText("Passengers")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Luggage/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Requester name"), { target: { value: "Test operator" } });
    fireEvent.change(screen.getByLabelText("Scheduled pickup"), { target: { value: "2026-08-13T10:00" } });
    fireEvent.change(screen.getByLabelText("Load description"), { target: { value: "Prepared meal trays" } });
    fireEvent.change(screen.getByLabelText("Load quantity"), { target: { value: "12" } });
    fireEvent.change(screen.getByLabelText("Handling instructions"), { target: { value: "Keep upright" } });
    fireEvent.change(screen.getByLabelText("Temperature requirement"), { target: { value: "Keep warm" } });
    fireEvent.submit(screen.getByRole("button", { name: "Create Request" }).closest("form")!);
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
    const createCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(String(createCall[1]?.body))).toMatchObject({
      source_system: "MANUAL_STAFF_ENTRY", request_type: "FOOD_DELIVERY",
      request_category: "DELIVERY_LOGISTICS", passenger_count: 0, luggage_count: 0,
      load_description: "Prepared meal trays", load_quantity: 12,
      handling_instructions: "Keep upright", temperature_requirement: "Keep warm",
    });
  });
  test("Edit preserves unchanged saved addresses and coordinates without searching", async () => {
    const fetchMock = vi.mocked(globalThis.fetch); renderAt(`/transport-requests/${request.id}/edit`); await screen.findByRole("heading", { name: "Edit Transport Request" });
    expect(screen.getByLabelText("Pickup address")).toHaveValue(request.pickup_address); expect(screen.getByLabelText("Destination address")).toHaveValue(request.destination_address);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("places/"))).toBe(false); fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true)); const patchCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH")!; const payload = JSON.parse(String(patchCall[1]?.body));
    expect(payload).toMatchObject({ pickup_latitude: request.pickup_latitude, pickup_longitude: request.pickup_longitude, destination_latitude: request.destination_latitude, destination_longitude: request.destination_longitude });
  });
  test("keeps the stable MapLibre canvas mounted and reports a missing TomTom key", () => {
    render(<RequestMap request={null} />);
    expect(screen.getByTestId("request-map").closest(".request-map")).toHaveClass("tomtom-request-map", "maplibre-request-map", "request-map--empty");
    expect(screen.getByRole("alert")).toHaveTextContent("TomTom map key is not configured.");
    expect(screen.getByText("No request selected")).toBeInTheDocument();
    expect(maplibre.instances).toHaveLength(0);
  });
  test("initializes MapLibre with the TomTom Orbis vector driving style without plus/minus controls", () => {
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test"); render(<RequestMap request={null} />);
    expect(maplibre.instances).toHaveLength(1);
    expect(maplibre.instances[0].options.style).toContain("/maps/orbis/assets/styles/0.*/style?apiVersion=1&map=basic_street-light-driving");
    expect(maplibre.instances[0].options.style).not.toContain("key=");
    expect(maplibre.instances[0].options.attributionControl).toBe(false);
    expect(maplibre.controls).toHaveLength(0);
  });
  test("keeps the map usable when optional rotation controls are unavailable", () => {
    maplibre.controlsAvailable = false; vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test"); render(<RequestMap request={null} />);
    expect(screen.getByTestId("request-map")).toBeInTheDocument(); expect(screen.queryByText("Unable to load TomTom map.")).not.toBeInTheDocument();
  });
  test("keeps the map shell mounted and reports an initialization failure", async () => {
    maplibre.failConstruction = true; vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test"); render(<RequestMap request={null} />);
    expect(screen.getByTestId("request-map")).toBeInTheDocument(); expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load TomTom map.");
  });
  test("opens the compact map settings menu, defaults to Street, and closes on Escape or outside click", () => {
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test"); render(<RequestMap request={null} />); const button = screen.getByRole("button", { name: "Map settings" });
    expect(button).toHaveAttribute("title", "Map settings"); expect(screen.queryByRole("dialog", { name: "Map settings" })).not.toBeInTheDocument();
    fireEvent.click(button); expect(screen.getByRole("radio", { name: "Street" })).toBeChecked(); expect(screen.queryByRole("button", { name: /Traffic on/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close map settings" })); expect(screen.queryByRole("dialog", { name: "Map settings" })).not.toBeInTheDocument();
    fireEvent.click(button); fireEvent.keyDown(document, { key: "Escape" }); expect(screen.queryByRole("dialog", { name: "Map settings" })).not.toBeInTheDocument();
    fireEvent.click(button); fireEvent.mouseDown(document.body); expect(screen.queryByRole("dialog", { name: "Map settings" })).not.toBeInTheDocument();
  });
  test("switches and persists valid map styles while invalid saved styles fall back to Street", () => {
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test"); const first = render(<RequestMap request={null} />); fireEvent.click(screen.getByRole("button", { name: "Map settings" })); fireEvent.click(screen.getByRole("radio", { name: "Mono" }));
    expect(maplibre.instances[0].setStyle).toHaveBeenCalledWith(expect.stringContaining("map=basic_mono-light")); expect(localStorage.getItem("ftms.transportRequests.mapStyle")).toBe("mono"); first.unmount();
    render(<RequestMap request={null} />); expect(latestMap().options.style).toContain("map=basic_mono-light");
    localStorage.setItem("ftms.transportRequests.mapStyle", "unsupported"); const second = render(<RequestMap request={null} />); fireEvent.click(screen.getAllByRole("button", { name: "Map settings" }).at(-1)!); expect(screen.getAllByRole("radio", { name: "Street" }).at(-1)).toBeChecked(); second.unmount();
  });
  test("authenticates only TomTom MapLibre resources with the existing browser key", () => {
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test"); render(<RequestMap request={null} />); const transformRequest = maplibre.instances[0].options.transformRequest;
    expect(transformRequest("https://api.tomtom.com/maps/orbis/assets/fonts/0.*/font.pbf")).toEqual({ url: "https://api.tomtom.com/maps/orbis/assets/fonts/0.*/font.pbf", headers: { "TomTom-Api-Key": "configured-in-test" } });
    expect(transformRequest("https://example.com/unrelated.json")).toEqual({ url: "https://example.com/unrelated.json" });
  });
  test("keeps the stable canvas visible while loading and clears it on map load", () => {
    maplibre.autoLoad = false; vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test"); render(<RequestMap request={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading TomTom map…"); expect(screen.getByTestId("request-map")).toBeInTheDocument();
    act(() => maplibre.instances[0].handlers.get("load")?.()); expect(screen.queryByText("Loading TomTom map…")).not.toBeInTheDocument();
  });
  test("stops the loading state and shows a compact error when style loading fails", () => {
    maplibre.autoLoad = false; vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test"); render(<RequestMap request={null} />);
    act(() => maplibre.instances[0].handlers.get("error")?.({ error: new Error("Style failed to load") }));
    expect(screen.queryByText("Loading TomTom map…")).not.toBeInTheDocument(); expect(screen.getByRole("alert")).toHaveTextContent("Unable to load TomTom map.");
  });
  test("configures Orbis raster traffic and incidents below the backend route and represents both markers", () => {
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test"); render(<RequestMap request={request as TransportRequestBase} />);
    const map = maplibre.instances[0];
    expect(map.sources.get("tomtom-traffic-source")!.tiles[0]).toContain("/maps/orbis/traffic/flow/raster/tile/{z}/{x}/{y}?apiVersion=2");
    expect(map.sources.get("tomtom-incidents-source")!.tiles[0]).toContain("/maps/orbis/traffic/incidents/raster/tile/{z}/{x}/{y}?apiVersion=2");
    expect(map.layers.map(layer => layer.id)).toEqual(["tomtom-traffic-layer", "tomtom-incidents-layer", "request-route-casing", "request-route-line"]);
    expect(map.layers.find(layer => layer.id === "tomtom-traffic-layer")!.paint).toEqual({ "raster-opacity": 0.5 });
    expect(map.layers.find(layer => layer.id === "request-route-casing")!.paint).toMatchObject({ "line-color": "#fffdf9", "line-width": 10, "line-opacity": 0.72 });
    expect(map.layers.find(layer => layer.id === "request-route-line")!.paint).toMatchObject({ "line-color": "#263d73", "line-width": 6, "line-opacity": 0.96 });
    expect(maplibre.markers.map(marker => marker.position)).toEqual([[121.0198, 14.5086], [121.0286, 14.5652]]);
    expect(maplibre.markers.map(marker => marker.options.element.title)).toEqual(["Pickup: NAIA Terminal 3", "Destination: Oxford Suites Makati"]);
    expect(map.fitBounds).toHaveBeenCalled();
  });
  test("renders real fleet trail and safety layers with selectable stateful markers", () => {
    const onVehicleSelect = vi.fn(); const onSafetyEventSelect = vi.fn();
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test");
    render(<RequestMap request={request as TransportRequestBase} fleetLocations={[
      { deviceId: "LIVE-001", latitude: 14.56, longitude: 121.02, label: "Hotel Shuttle", telemetryState: "live", selected: true },
      { deviceId: "OFF-001", latitude: 14.55, longitude: 121.03, label: "Inactive Sedan", telemetryState: "offline" },
      { deviceId: "STALE-002", latitude: 14.54, longitude: 121.04, label: "Stale Van", telemetryState: "stale" },
    ]} fleetTrail={[
      { event_id: "trail-1", latitude: 14.55, longitude: 121.01, recorded_at: "2026-08-21T07:59:30Z" },
      { event_id: "trail-2", latitude: 14.56, longitude: 121.02, recorded_at: "2026-08-21T07:59:50Z" },
    ]} safetyEvents={[
      { event_id: "brake-1", event_type: "HARSH_BRAKING", latitude: 14.56, longitude: 121.02, vehicle_name: "Hotel Shuttle" },
    ]} onVehicleSelect={onVehicleSelect} onSafetyEventSelect={onSafetyEventSelect} />);
    const map = latestMap();
    expect(map.layers.filter(layer => layer.source === "fleet-trail-source").map(layer => layer.id)).toEqual(["fleet-trail-line", "fleet-trail-points"]);
    expect(map.sources.get("fleet-trail-source")!.setData).toHaveBeenCalledWith(expect.objectContaining({ geometry: { type: "LineString", coordinates: [[121.01, 14.55], [121.02, 14.56]] } }));
    expect(maplibre.markers.map(marker => marker.options.element.title)).toEqual(["Hotel Shuttle — Live telemetry", "Inactive Sedan — Offline telemetry", "Stale Van — Stale telemetry", "Harsh braking: Hotel Shuttle", "Pickup: NAIA Terminal 3", "Destination: Oxford Suites Makati"]);
    expect((map.fitBounds.mock.calls[0][0] as { points: [number, number][] }).points).toEqual(expect.arrayContaining([[121.02, 14.56], [121.03, 14.55], [121.04, 14.54]]));
    expect(screen.getByLabelText("Fleet map legend")).toHaveTextContent("LiveStaleOfflineNo telemetrySelected vehicleActive dispatch routeRecent breadcrumb trailSafety event");
    fireEvent.click(maplibre.markers[0].options.element); fireEvent.click(maplibre.markers[3].options.element);
    expect(onVehicleSelect).toHaveBeenCalledWith("LIVE-001"); expect(onSafetyEventSelect).toHaveBeenCalledWith("brake-1");
  });
  test("anchors a professional vehicle card to the selected marker without Street View", () => {
    const onClose = vi.fn();
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test");
    render(<RequestMap request={null} fleetLocations={[
      { deviceId: "LIVE-001", latitude: 14.56, longitude: 121.02, label: "Hotel Shuttle", telemetryState: "live", selected: true },
    ]} fleetTrail={[
      { event_id: "trail-1", latitude: 14.55, longitude: 121.01, recorded_at: "2026-08-21T07:59:30Z" },
      { event_id: "trail-2", latitude: 14.56, longitude: 121.02, recorded_at: "2026-08-21T07:59:50Z" },
    ]} fleetPopup={{ deviceId: "LIVE-001", label: "Hotel Shuttle", plateNumber: "ABC-123", telemetryState: "live", latitude: 14.56, longitude: 121.02, speedKph: 32, recordedAt: "2026-08-21T07:59:50Z", ageSeconds: 10, driverName: "Ana Santos", assignmentStatus: "In Transit", telemetrySource: "demo" }} onVehiclePopupClose={onClose} />);
    expect(maplibre.popups).toHaveLength(1);
    const popup = maplibre.popups[0];
    expect(popup.position).toEqual([121.02, 14.56]);
    expect(popup.content).toHaveTextContent("ABC-123Hotel Shuttle");
    expect(popup.content).toHaveTextContent("10sSpeed: 32 km/h");
    expect(popup.content).toHaveTextContent("Demo snapshot");
    expect(popup.content).toHaveTextContent("Driver Ana Santos");
    expect(popup.content).not.toHaveTextContent(/Street View/i);
    fireEvent.click(within(popup.content!).getByRole("button", { name: "Zoom to" }));
    expect(latestMap().jumpTo).toHaveBeenLastCalledWith({ center: [121.02, 14.56], zoom: 17, bearing: 0, pitch: 0 });
    fireEvent.click(within(popup.content!).getByRole("button", { name: "Replay" }));
    expect(latestMap().fitBounds).toHaveBeenLastCalledWith(expect.anything(), { padding: 80, maxZoom: 17, duration: 500 });
    fireEvent.click(within(popup.content!).getByRole("button", { name: "Close vehicle map details" }));
    expect(onClose).toHaveBeenCalled();
  });
  test("preserves the operator camera when refreshed fleet markers arrive", () => {
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test");
    const initialLocations = [
      { deviceId: "LIVE-001", latitude: 14.56, longitude: 121.02, label: "Hotel Shuttle", telemetryState: "live" as const },
      { deviceId: "OFF-001", latitude: 14.55, longitude: 121.03, label: "Inactive Sedan", telemetryState: "offline" as const },
    ];
    const { rerender } = render(<RequestMap request={null} fleetLocations={initialLocations} />);
    const map = latestMap();
    expect(map.fitBounds).toHaveBeenCalledTimes(1);
    map.jumpTo({ center: [121.021, 14.561], zoom: 18 });
    rerender(<RequestMap request={null} fleetLocations={initialLocations.map(location => ({ ...location }))} />);
    expect(map.fitBounds).toHaveBeenCalledTimes(1);
    expect(map.jumpTo).toHaveBeenCalledTimes(1);
    expect(maplibre.markers.filter(marker => !marker.removed)).toHaveLength(2);
  });
  test("opens fleet-only map actions for nearest asset, zoom, and an honest geofence draft", () => {
    const onVehicleSelect = vi.fn(); const onPopupClose = vi.fn();
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test");
    render(<RequestMap request={null} fleetLocations={[
      { deviceId: "NEAR-001", latitude: 14.56, longitude: 121.02, label: "Near Van", telemetryState: "live" },
      { deviceId: "FAR-001", latitude: 15.2, longitude: 122.1, label: "Far Van", telemetryState: "offline" },
    ]} onVehicleSelect={onVehicleSelect} onVehiclePopupClose={onPopupClose} />);
    const map = latestMap();
    const clickMap = () => act(() => map.handlers.get("click")?.({ point: { x: 120, y: 90 }, lngLat: { lng: 121.021, lat: 14.561 } }));
    clickMap();
    expect(screen.getByRole("menu", { name: "Map actions" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /Street View/i })).not.toBeInTheDocument();
    expect(onPopupClose).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("menuitem", { name: "Nearest fleet asset" }));
    expect(onVehicleSelect).toHaveBeenCalledWith("NEAR-001");
    expect(map.jumpTo).toHaveBeenLastCalledWith({ center: [121.02, 14.56], zoom: 16, bearing: 0, pitch: 0 });
    clickMap();
    fireEvent.click(screen.getByRole("menuitem", { name: "Zoom to" }));
    expect(map.jumpTo).toHaveBeenLastCalledWith({ center: [121.021, 14.561], zoom: 17, bearing: 0, pitch: 0 });
    clickMap();
    fireEvent.click(screen.getByRole("menuitem", { name: "Create geofence" }));
    expect(screen.getByRole("status")).toHaveTextContent("Geofence center selected14.56100, 121.02100Not saved. Geofence persistence is not configured yet.");
  });
  test("renders persistent geofence boundaries and routes map creation to the editor", () => {
    const onGeofenceSelect = vi.fn(); const onGeofenceCreateAt = vi.fn();
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test");
    render(<RequestMap request={null} fleetLocations={[]} geofences={[{
      id: "geo-1", name: "Oxford Zone", color: "#008F8C", showOnMap: true, selected: true,
      center: { latitude: 14.56, longitude: 121.02 },
      vertices: [{ latitude: 14.55, longitude: 121.01 }, { latitude: 14.55, longitude: 121.03 }, { latitude: 14.57, longitude: 121.02 }],
    }]} geofenceDraft={{ color: "#CF4B4B", vertices: [{ latitude: 14.56, longitude: 121.02 }, { latitude: 14.56, longitude: 121.03 }, { latitude: 14.57, longitude: 121.02 }] }} onGeofenceSelect={onGeofenceSelect} onGeofenceCreateAt={onGeofenceCreateAt} />);
    const map = latestMap();
    expect(map.sources.get("fleet-geofences-source")!.setData).toHaveBeenCalledWith(expect.objectContaining({ features: [expect.objectContaining({ properties: expect.objectContaining({ id: "geo-1", selected: true }) })] }));
    expect(map.sources.get("fleet-geofence-draft-source")!.setData).toHaveBeenCalled();
    const label = maplibre.markers.find(marker => marker.options.element.title === "Open geofence: Oxford Zone")!;
    fireEvent.click(label.options.element); expect(onGeofenceSelect).toHaveBeenCalledWith("geo-1");
    act(() => map.handlers.get("click")?.({ point: { x: 120, y: 90 }, lngLat: { lng: 121.021, lat: 14.561 } }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Create geofence" }));
    expect(onGeofenceCreateAt).toHaveBeenCalledWith({ latitude: 14.561, longitude: 121.021 });
    expect(screen.queryByText("Not saved. Geofence persistence is not configured yet.")).not.toBeInTheDocument();
  });
  test("searches backend places from the fleet map and focuses the selected result", async () => {
    vi.useFakeTimers();
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test");
    const fetchMock = vi.mocked(globalThis.fetch);
    fetchMock.mockImplementation(input => String(input).includes("places/suggest/")
      ? json({ results: [{ id: "oxford", type: "poi", title: "Oxford Suites Makati", subtitles: ["Poblacion, Makati"] }] })
      : json({ id: "oxford", type: "poi", title: "Oxford Suites Makati", subtitles: ["Poblacion, Makati"], display_address: "Poblacion, Makati, Philippines", latitude: 14.5652, longitude: 121.0286 }));
    render(<RequestMap request={null} fleetLocations={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "Search map places" }));
    const input = screen.getByRole("combobox", { name: "Search map places" });
    expect(input).toHaveFocus();
    fireEvent.change(input, { target: { value: "Ox" } });
    await act(async () => { vi.advanceTimersByTime(350); });
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: "Oxford" } });
    await act(async () => { vi.advanceTimersByTime(300); await Promise.resolve(); await Promise.resolve(); });
    fireEvent.click(screen.getByRole("option", { name: /Oxford Suites Makati/ }));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(input).toHaveValue("Poblacion, Makati, Philippines");
    expect(latestMap().jumpTo).toHaveBeenLastCalledWith({ center: [121.0286, 14.5652], zoom: 17, bearing: 0, pitch: 0 });
    expect(maplibre.markers.at(-1)?.options.element.title).toBe("Search result: Oxford Suites Makati");
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("api.tomtom.com"))).toBe(false);
  });
  test("toggles traffic without remounting the base map", () => {
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test"); render(<RequestMap request={null} />);
    const canvas = screen.getByTestId("request-map"); const map = maplibre.instances[0]; fireEvent.click(screen.getByRole("button", { name: "Map settings" })); fireEvent.click(screen.getByRole("checkbox", { name: "Live traffic" }));
    expect(screen.getByRole("checkbox", { name: "Live traffic" })).not.toBeChecked(); expect(map.layout.get("tomtom-traffic-layer")).toBe("none"); expect(localStorage.getItem("ftms.transportRequests.trafficEnabled")).toBe("false"); expect(maplibre.instances).toHaveLength(1); expect(screen.getByTestId("request-map")).toBe(canvas);
  });
  test("toggles incidents independently and preserves the map on a load failure", async () => {
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test"); render(<RequestMap request={null} />);
    const map = maplibre.instances[0]; fireEvent.click(screen.getByRole("button", { name: "Map settings" })); fireEvent.click(screen.getByRole("checkbox", { name: "Traffic incidents" })); expect(screen.getByRole("checkbox", { name: "Traffic incidents" })).not.toBeChecked(); expect(map.layout.get("tomtom-incidents-layer")).toBe("none"); expect(map.layout.get("tomtom-traffic-layer")).toBe("visible"); expect(localStorage.getItem("ftms.transportRequests.incidentsEnabled")).toBe("false");
    act(() => map.handlers.get("error")?.()); expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load TomTom map."); expect(screen.getByTestId("request-map")).toBeInTheDocument();
  });
  test("restores persisted traffic and incident preferences", () => {
    localStorage.setItem("ftms.transportRequests.trafficEnabled", "false"); localStorage.setItem("ftms.transportRequests.incidentsEnabled", "false"); vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test"); render(<RequestMap request={null} />); const map = maplibre.instances[0];
    fireEvent.click(screen.getByRole("button", { name: "Map settings" })); expect(screen.getByRole("checkbox", { name: "Live traffic" })).not.toBeChecked(); expect(screen.getByRole("checkbox", { name: "Traffic incidents" })).not.toBeChecked(); expect(map.layers.find(layer => layer.id === "tomtom-traffic-layer")!.layout!.visibility).toBe("none"); expect(map.layers.find(layer => layer.id === "tomtom-incidents-layer")!.layout!.visibility).toBe("none");
  });
  test("returns the no-selection map to the Oxford Suites fallback", () => {
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test"); render(<RequestMap request={null} />);
    expect(maplibre.instances[0].jumpTo).toHaveBeenCalledWith({ center: [121.0286, 14.5652], zoom: 13, bearing: 0, pitch: 0 }); expect(screen.getByText("No request selected")).toBeInTheDocument(); expect(maplibre.markers).toHaveLength(0);
  });
  test("adds only backend road GeoJSON to the casing and main route layers", () => {
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test");
    const route = { request_id: request.id, traffic_mode: "live" as const, distance_meters: 12400, duration_seconds: 1860, traffic_delay_seconds: 360, departure_time: "2026-08-07T10:00:00+08:00", arrival_time: "2026-08-07T10:31:00+08:00", geometry: { type: "LineString" as const, coordinates: [[121.0198, 14.5086], [121.025, 14.54], [121.0286, 14.5652]] as [number, number][] } };
    render(<RequestMap request={request as TransportRequestBase} route={route} routeState="ready" />);
    const source = maplibre.instances[0].sources.get("request-route-source");
    expect(source!.setData).toHaveBeenCalledWith(expect.objectContaining({ geometry: { type: "LineString", coordinates: route.geometry.coordinates } }));
    expect(maplibre.instances[0].layers.filter(layer => layer.source === "request-route-source").map(layer => layer.id)).toEqual(["request-route-casing", "request-route-line"]);
  });
  test("reconciles operational layers and route without duplication across repeated style changes", () => {
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test"); const route = { request_id: request.id, traffic_mode: "live" as const, distance_meters: 12400, duration_seconds: 1860, traffic_delay_seconds: 360, departure_time: "2026-08-07T10:00:00+08:00", arrival_time: "2026-08-07T10:31:00+08:00", geometry: { type: "LineString" as const, coordinates: [[121.0198, 14.5086], [121.0286, 14.5652]] as [number, number][] } };
    render(<RequestMap request={request as TransportRequestBase} route={route} routeState="ready" />); const map = maplibre.instances[0]; fireEvent.click(screen.getByRole("button", { name: "Map settings" }));
    for (const [style, tomTomStyle] of [["Satellite", "basic_street-satellite"], ["Dark", "basic_street-dark-driving"], ["Street", "basic_street-light-driving"]]) { fireEvent.click(screen.getByRole("radio", { name: style })); expect(map.setStyle).toHaveBeenLastCalledWith(expect.stringContaining(`map=${tomTomStyle}`)); expect(map.layers.map(layer => layer.id)).toEqual(["tomtom-traffic-layer", "tomtom-incidents-layer", "request-route-casing", "request-route-line"]); expect(map.sources.size).toBe(3); }
    expect(maplibre.instances).toHaveLength(1); expect(map.sources.get("request-route-source")!.setData).toHaveBeenCalledWith(expect.objectContaining({ geometry: { type: "LineString", coordinates: route.geometry.coordinates } })); expect(maplibre.markers.filter(marker => !marker.removed)).toHaveLength(2);
  });
  test("updates selection without recreating MapLibre and resizes through ResizeObserver", () => {
    let resizeCallback!: () => void; const disconnect = vi.fn();
    vi.stubGlobal("ResizeObserver", class { constructor(callback: () => void) { resizeCallback = callback; } observe() {} disconnect() { disconnect(); } });
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test"); const { rerender, unmount } = render(<RequestMap request={request as TransportRequestBase} />); const map = maplibre.instances[0];
    const second = { ...request, id: "second-request", pickup_longitude: "121.05", destination_longitude: "121.08" }; rerender(<RequestMap request={second as TransportRequestBase} />);
    expect(maplibre.instances).toHaveLength(1); expect(map.fitBounds).toHaveBeenCalledTimes(2); act(() => resizeCallback()); expect(map.resize).toHaveBeenCalled();
    unmount(); expect(disconnect).toHaveBeenCalled(); expect(map.remove).toHaveBeenCalled(); expect(maplibre.markers.at(-1)!.removed).toBe(true);
  });
  test("loads routing only for the selected request and renders live metrics", async () => {
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test"); renderAt("/transport-requests");
    await waitFor(() => expect(latestMap().sources.get("request-route-source")!.setData).toHaveBeenCalledWith(expect.objectContaining({ geometry: expect.objectContaining({ type: "LineString" }) })));
    fireEvent.click(screen.getByRole("tab", { name: "Route" }));
    expect((await screen.findAllByText("12.4 km")).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/31 min/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/\+6 min/).length).toBeGreaterThan(0);
    expect(screen.getByText("Live traffic")).toBeInTheDocument();
    const routeCalls = vi.mocked(globalThis.fetch).mock.calls.filter(([input]) => String(input).endsWith("/route/"));
    expect(routeCalls).toHaveLength(1);
    expect(vi.mocked(globalThis.fetch).mock.calls.some(([input]) => String(input).includes("api.tomtom.com/maps/orbis/routing"))).toBe(false);
  });
  test("closes and restores the selected request information card", async () => {
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test"); renderAt("/transport-requests"); const close = await screen.findByRole("button", { name: "Close request information" }); fireEvent.click(close);
    expect(screen.queryByRole("button", { name: "Close request information" })).not.toBeInTheDocument(); const restore = screen.getByRole("button", { name: "Request info" }); fireEvent.click(restore); expect(screen.getByRole("button", { name: "Close request information" })).toBeInTheDocument();
  });
  test("shows non-blocking route loading and reuses a calculated route on reselection", async () => {
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test");
    const second = { ...request, id: "49bc47e8-74f8-4340-a94c-e9cc5619e734", request_number: "TR-SECOND" };
    const routeBody = (id: string) => ({ request_id: id, traffic_mode: "live", distance_meters: 12400, duration_seconds: 1860, traffic_delay_seconds: 360, departure_time: "2026-08-07T10:00:00+08:00", arrival_time: "2026-08-07T10:31:00+08:00", geometry: { type: "LineString", coordinates: [[121.0198, 14.5086], [121.0286, 14.5652]] } });
    let releaseFirst!: () => void; const firstPending = new Promise<Response>(resolve => { releaseFirst = () => resolve(new Response(JSON.stringify(routeBody(request.id)), { status: 200, headers: { "Content-Type": "application/json" } })); });
    vi.mocked(globalThis.fetch).mockImplementation(input => { const url = String(input); if (url.endsWith("summary/")) return json({ ...summary, total: 2, for_approval: 2, approval_queue: 2 }); if (url.endsWith(`${request.id}/route/`)) return firstPending; if (url.endsWith(`${second.id}/route/`)) return json(routeBody(second.id)); return json({ count: 2, next: null, previous: null, results: [request, second] }); });
    renderAt("/transport-requests"); expect(await screen.findAllByText("Calculating route…")).not.toHaveLength(0); expect(screen.getByTestId("request-map")).toBeInTheDocument();
    releaseFirst(); await waitFor(() => expect(latestMap().sources.get("request-route-source")!.setData).toHaveBeenCalledWith(expect.objectContaining({ geometry: expect.objectContaining({ type: "LineString" }) })));
    fireEvent.click(screen.getByRole("button", { name: /TR-SECOND/ })); await waitFor(() => expect(vi.mocked(globalThis.fetch).mock.calls.some(([input]) => String(input).endsWith(`${second.id}/route/`))).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: new RegExp(request.request_number) }));
    await waitFor(() => expect(vi.mocked(globalThis.fetch).mock.calls.filter(([input]) => String(input).endsWith(`${request.id}/route/`))).toHaveLength(1));
  });
  test("keeps the map usable when routing fails", async () => {
    vi.stubEnv("VITE_TOMTOM_MAPS_KEY", "configured-in-test");
    vi.mocked(globalThis.fetch).mockImplementation(input => { const url = String(input); if (url.endsWith("summary/")) return json(summary); if (url.endsWith("/route/")) return errorJson({ detail: "Route unavailable." }, 502); return json({ count: 1, next: null, previous: null, results: [request] }); });
    renderAt("/transport-requests");
    expect(await screen.findAllByText("Route unavailable")).not.toHaveLength(0);
    expect(screen.getByTestId("request-map")).toBeInTheDocument(); expect(latestMap().sources.get("request-route-source")!.setData).toHaveBeenCalledWith({ type: "FeatureCollection", features: [] });
  });
  test("protects the route", async () => {
    auth.user = null; renderAt("/transport-requests");
    expect(await screen.findByRole("heading", { name: "Sign in to FTMS" })).toBeInTheDocument();
  });
  test("redirects the legacy standalone Active Trips bookmark", async () => {
    renderAt("/active-trips");
    expect(await screen.findByRole("heading", { name: "Transport Requests" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Active Trips" })).toBeInTheDocument();
  });
  test("renders API data and all records on the page", async () => {
    const rows = Array.from({ length: 8 }, (_, index) => ({ ...request, id: `${request.id.slice(0, -1)}${index}`, request_number: `TR-PAGE-${index}` }));
    vi.mocked(globalThis.fetch).mockImplementation(input => String(input).endsWith("summary/") ? json({ ...summary, total: 8, for_approval: 8, approval_queue: 8 }) : json({ count: 8, next: null, previous: null, results: rows }));
    renderAt("/transport-requests");
    expect(await screen.findAllByText("TR-PAGE-7")).not.toHaveLength(0);
    expect(screen.getAllByText("NAIA Terminal 3").length).toBeGreaterThan(0);
  });
  test("renders only supported priority chips and semantically distinct workflow badges", () => {
    render(<>{priorities.map(value => <PriorityChip key={value} value={value} />)}{statuses.map(value => <WorkflowStatusBadge key={value} value={value} />)}</>);
    const priorityIndicators = document.querySelectorAll('[data-indicator="priority"]');
    const workflowIndicators = document.querySelectorAll('[data-indicator="workflow-status"]');
    expect(priorityIndicators).toHaveLength(priorities.length);
    expect(workflowIndicators).toHaveLength(statuses.length);
    expect(Array.from(priorityIndicators).every(item => item.classList.contains("priority-chip"))).toBe(true);
    expect(Array.from(workflowIndicators).every(item => item.classList.contains("workflow-badge"))).toBe(true);
    expect(screen.getByText("Normal")).toBeInTheDocument();
    expect(screen.getByText("Awaiting Decision")).toBeInTheDocument();
    expect(screen.getByText("Ready for Dispatch")).toBeInTheDocument();
  });
  test("opens and closes the request details drawer without resetting list state", async () => {
    renderAt("/transport-requests");
    const search = screen.getByLabelText("Search requests");
    fireEvent.change(search, { target: { value: "TR" } });
    const requestButton = await screen.findByRole("button", { name: new RegExp(request.request_number) });
    fireEvent.click(requestButton);
    expect(screen.queryByRole("dialog", { name: request.request_number })).not.toBeInTheDocument();
    const actionsButton = within(requestButton.parentElement!).getByRole("button", { name: "More options" });
    fireEvent.click(actionsButton);
    fireEvent.click(screen.getByRole("menuitem", { name: "View details" }));
    const drawer = await screen.findByRole("dialog", { name: request.request_number });
    const queue = screen.getByLabelText("Request queue");
    const mapWorkspace = screen.getByLabelText("Request map");
    const rightWorkspace = screen.getByLabelText("Request workspace");
    const pageHeader = document.querySelector(".topbar");
    const overview = within(rightWorkspace).getByRole("heading", { name: "Selected Request Overview" }).closest(".selected-request-overview") as HTMLElement;
    expect(within(overview).getByText("Passenger summary")).toBeInTheDocument();
    expect(within(overview).getByText("Passengers").nextElementSibling).toHaveTextContent("2");
    expect(within(overview).getByText("Luggage items").nextElementSibling).toHaveTextContent("1");
    expect(queue).toBeInTheDocument();
    expect(queue.parentElement).toHaveClass("request-workspace", "request-workspace--fixed", "request-workspace--drawer-open");
    expect(queue.nextElementSibling).toBe(rightWorkspace);
    expect(rightWorkspace).toContainElement(drawer);
    expect(rightWorkspace).toContainElement(mapWorkspace);
    expect(rightWorkspace).toContainElement(screen.getByRole("heading", { name: "Selected Request Overview" }));
    expect(mapWorkspace).not.toContainElement(drawer);
    expect(queue).not.toContainElement(drawer);
    expect(rightWorkspace).toContainElement(screen.getByTestId("request-workspace-backdrop"));
    expect(pageHeader).not.toContainElement(drawer);
    expect(within(requestButton).getByText(request.request_number)).toBeInTheDocument();
    expect(within(requestButton).getByText("Airport Pickup")).toBeInTheDocument();
    expect(within(requestButton).getByText(/Front Desk/)).toHaveTextContent("Hotel Management System");
    expect(within(requestButton).getByText(/NAIA Terminal 3 → Oxford Suites Makati/)).toBeInTheDocument();
    expect(within(requestButton).queryByText("High")).not.toBeInTheDocument();
    expect(within(requestButton).getByText("Awaiting Decision")).toHaveClass("workflow-badge");
    expect(within(drawer).getByText("Passenger details")).toBeInTheDocument();
    expect(within(drawer).getByText("Passengers").nextElementSibling).toHaveTextContent("2");
    expect(within(drawer).getByText("Luggage items").nextElementSibling).toHaveTextContent("1");
    expect(within(drawer).queryByRole("link", { name: "Open full request" })).not.toBeInTheDocument();
    expect(within(drawer).getByText("Audit timeline")).toBeInTheDocument();
    expect(within(drawer).getByText("Created")).toBeInTheDocument();
    expect(within(drawer).getByText("Hotel Management System")).toBeInTheDocument();
    expect(within(drawer).getAllByText("High").some(item => item.classList.contains("priority-chip"))).toBe(true);
    expect(within(drawer).getAllByText("Awaiting Decision").every(item => item.classList.contains("workflow-badge"))).toBe(true);
    expect(within(drawer).getByRole("link", { name: "Edit request" })).toHaveAttribute("href", `/transport-requests/${request.id}/edit`);
    expect(within(drawer).queryByRole("button", { name: "Cancel Request" })).not.toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    fireEvent.click(within(drawer).getByRole("button", { name: "Close request details" }));
    expect(screen.queryByRole("dialog", { name: request.request_number })).not.toBeInTheDocument();
    expect(queue.parentElement).not.toHaveClass("request-workspace--drawer-open");
    expect(within(mapWorkspace).getByTestId("request-map")).toBeInTheDocument();
    expect(within(rightWorkspace).getByRole("heading", { name: "Selected Request Overview" })).toBeInTheDocument();
    expect(search).toHaveValue("TR");
    await waitFor(() => expect(actionsButton).toHaveFocus());
    fireEvent.click(within(rightWorkspace).getByRole("button", { name: "View Details" }));
    await screen.findByRole("dialog", { name: request.request_number });
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: request.request_number })).not.toBeInTheDocument();
  });
  test("shows delivery semantics in the request details drawer without luggage cargo", async () => {
    const delivery = {
      ...request, request_category: "DELIVERY_LOGISTICS", request_type: "FOOD_DELIVERY",
      passenger_count: 0, luggage_count: 9, load_description: "Prepared meal trays",
      load_quantity: 12, estimated_weight_kg: "42.50", handling_instructions: "Keep upright",
      temperature_requirement: "Keep warm",
    };
    vi.mocked(globalThis.fetch).mockImplementation(input => {
      const url = String(input);
      if (url.endsWith("summary/")) return json(summary);
      if (url.endsWith(`${delivery.id}/`)) return json(delivery);
      return json({ count: 1, next: null, previous: null, results: [delivery] });
    });
    renderAt("/transport-requests");
    const deliveryButton = await screen.findByRole("button", { name: new RegExp(delivery.request_number) });
    const overview = screen.getByRole("heading", { name: "Selected Request Overview" }).closest(".selected-request-overview") as HTMLElement;
    expect(within(overview).getByText("Delivery summary")).toBeInTheDocument();
    expect(within(overview).getByText("Prepared meal trays")).toBeInTheDocument();
    expect(within(overview).getByText("42.50 kg")).toBeInTheDocument();
    expect(within(overview).queryByText(/luggage/i)).not.toBeInTheDocument();
    fireEvent.click(within(deliveryButton.parentElement!).getByRole("button", { name: "More options" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "View details" }));
    const drawer = await screen.findByRole("dialog", { name: delivery.request_number });
    expect(within(drawer).getByText("Delivery details")).toBeInTheDocument();
    expect(within(drawer).getByText("Load description").nextElementSibling).toHaveTextContent("Prepared meal trays");
    expect(within(drawer).getByText("Quantity").nextElementSibling).toHaveTextContent("12");
    expect(within(drawer).getByText("Estimated weight").nextElementSibling).toHaveTextContent("42.50 kg");
    expect(within(drawer).getByText("Handling instructions").nextElementSibling).toHaveTextContent("Keep upright");
    expect(within(drawer).getByText("Temperature requirement").nextElementSibling).toHaveTextContent("Keep warm");
    expect(within(drawer).queryByText(/luggage/i)).not.toBeInTheDocument();
  });
  test("shows review actions without cancellation in the For Approval drawer", async () => {
    renderAt("/transport-requests");
    await screen.findAllByText(request.request_number);
    fireEvent.click(screen.getByRole("tab", { name: /For Approval/ }));
    const queue = await screen.findByLabelText("Request queue");
    fireEvent.click(within(queue).getByRole("button", { name: "More options" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "View details" }));
    const drawer = await screen.findByRole("dialog", { name: request.request_number });
    expect(within(drawer).getByRole("button", { name: "Approve Request" })).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "Request More Details" })).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "Reject" })).toBeInTheDocument();
    expect(within(drawer).getByRole("link", { name: "Edit request" })).toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "Cancel Request" })).not.toBeInTheDocument();
  });
  test("keeps correction, accepted, and terminal action eligibility status-specific", () => {
    const role = "FLEET_MANAGER";
    expect(canEditRequest("NEEDS_MORE_DETAILS", role)).toBe(true);
    expect(canResubmitRequest("NEEDS_MORE_DETAILS", role)).toBe(true);
    expect(canCancelRequest("NEEDS_MORE_DETAILS", role)).toBe(false);
    for (const status of ["APPROVED", "READY_FOR_DISPATCH"] as const) {
      expect(canEditRequest(status, role)).toBe(false);
      expect(canResubmitRequest(status, role)).toBe(false);
      expect(canCancelRequest(status, role)).toBe(true);
    }
    for (const status of ["REJECTED", "CANCELLED"] as const) {
      expect(canEditRequest(status, role)).toBe(false);
      expect(canResubmitRequest(status, role)).toBe(false);
      expect(canCancelRequest(status, role)).toBe(false);
    }
  });
  test("uses compact Overview, Route, and Activity tabs without changing selection", async () => {
    renderAt("/transport-requests");
    const overview = await screen.findByRole("heading", { name: "Selected Request Overview" });
    const panel = overview.closest(".selected-request-overview") as HTMLElement;
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    expect(panel).toHaveTextContent(request.request_number);
    fireEvent.click(screen.getByRole("tab", { name: "Route" }));
    expect(within(panel).getByText("NAIA Terminal 3")).toBeInTheDocument();
    expect(within(panel).getByText("Oxford Suites Makati")).toBeInTheDocument();
    expect(await within(panel).findByText("12.4 km")).toBeInTheDocument();
    expect(within(panel).getByText("+6 min")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Activity" }));
    expect(within(panel).getByText("Created")).toBeInTheDocument();
    expect(panel).toHaveTextContent(request.request_number);
    expect(screen.queryByRole("dialog", { name: request.request_number })).not.toBeInTheDocument();
  });
  test("shows honest route and activity empty states when data is unavailable", async () => {
    const noHistory = { ...request, latest_event_type: null, latest_event_at: null };
    vi.mocked(globalThis.fetch).mockImplementation(input => {
      const url = String(input);
      if (url.endsWith("summary/")) return json(summary);
      if (url.endsWith(`${request.id}/route/`)) return errorJson({ detail: "Unavailable" }, 503);
      return json({ count: 1, next: null, previous: null, results: [noHistory] });
    });
    renderAt("/transport-requests"); await screen.findByRole("heading", { name: "Selected Request Overview" });
    fireEvent.click(screen.getByRole("tab", { name: "Route" }));
    const overview = screen.getByRole("heading", { name: "Selected Request Overview" }).closest(".selected-request-overview") as HTMLElement;
    expect(await within(overview).findByText("Route unavailable")).toBeInTheDocument();
    expect(screen.queryByText(/km$/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Activity" }));
    expect(screen.getByText("No recorded request activity is available yet.")).toBeInTheDocument();
  });
  test("opens temporary Add Request in the vehicle-sized right drawer", async () => {
    renderAt("/transport-requests");
    await screen.findAllByText(request.request_number);
    const add = screen.getByRole("button", { name: /Add Request/i });
    expect(add).toHaveAttribute("title", "Temporary development/testing intake");
    fireEvent.click(add);
    const drawer = screen.getByRole("dialog", { name: "Add Transport Request" });
    expect(drawer).toHaveClass("request-create-drawer");
    expect(within(drawer).getByRole("button", { name: "Create Request" })).toBeInTheDocument();
    fireEvent.click(within(drawer).getByRole("button", { name: "Close Add Transport Request" }));
    expect(screen.queryByRole("dialog", { name: "Add Transport Request" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Refresh/ })).toBeInTheDocument();
    const selectedSummary = document.querySelector(".selected-summary") as HTMLElement;
    expect(within(selectedSummary).getByText("Passengers").nextElementSibling).toHaveTextContent("2");
  });
  test("uses passenger semantics in details and delivery fields without treating luggage as cargo", async () => {
    const passengerView = renderAt(`/transport-requests/${request.id}`);
    await screen.findByRole("heading", { name: request.request_number });
    expect(screen.getByText("Passengers / luggage").nextElementSibling).toHaveTextContent("2 / 1");
    passengerView.unmount();

    const delivery = {
      ...request,
      request_category: "DELIVERY_LOGISTICS",
      request_type: "CATERING_DELIVERY",
      passenger_count: 0,
      luggage_count: 17,
      load_description: "Twelve banquet meal trays",
      load_quantity: 12,
      estimated_weight_kg: "42.50",
      handling_instructions: "Keep upright",
      temperature_requirement: "Keep warm",
    };
    vi.mocked(globalThis.fetch).mockImplementation(input => {
      const url = String(input);
      if (url.includes("/vehicles/")) return json({ count: 0, next: null, previous: null, results: [] });
      if (url.endsWith(`${request.id}/`)) return json(delivery);
      return json({ count: 1, next: null, previous: null, results: [delivery] });
    });
    renderAt(`/transport-requests/${request.id}`);
    const details = (await screen.findByRole("heading", { name: "Request information" })).closest(".detail-card") as HTMLElement;
    expect(within(details).getByText("Load description").nextElementSibling).toHaveTextContent("Twelve banquet meal trays");
    expect(within(details).getByText("Load quantity").nextElementSibling).toHaveTextContent("12");
    expect(within(details).getByText("Estimated weight").nextElementSibling).toHaveTextContent("42.50 kg");
    expect(within(details).getByText("Handling instructions").nextElementSibling).toHaveTextContent("Keep upright");
    expect(within(details).getByText("Temperature requirement").nextElementSibling).toHaveTextContent("Keep warm");
    expect(within(details).queryByText(/luggage/i)).not.toBeInTheDocument();
  });
  test("keeps operational structures and queue count when filters return no results", async () => {
    const emptySummary = Object.fromEntries(Object.keys(summary).map(key => [key, 0]));
    vi.mocked(globalThis.fetch).mockImplementation(input => String(input).endsWith("summary/")
      ? json(emptySummary)
      : json({ count: 0, next: null, previous: null, results: [] }));
    renderAt("/transport-requests");
    expect(await screen.findByText("No request selected")).toBeInTheDocument();
    const queue = screen.getByLabelText("Request queue");
    expect(queue).toHaveTextContent("No transport requests match your filters.");
    expect(queue).toHaveClass("request-picker--scroll");
    expect(document.querySelector(".transport-page")).toHaveClass("transport-page--workspace");
    expect(document.body).not.toHaveClass("scroll-locked", "transport-page--workspace");
    expect(document.querySelector(".app-layout")).not.toHaveClass("scroll-locked", "transport-page--workspace");
    expect(screen.getByLabelText("Request map")).toBeInTheDocument();
    expect(screen.getByTestId("request-map")).toBeInTheDocument();
    expect(screen.getByLabelText("Request queue").closest(".request-workspace")).toHaveClass("request-workspace--fixed");
    expect(screen.getByText("Scheduled today")).toBeInTheDocument();
    const scheduledKpi = screen.getByText("Scheduled today").closest(".kpi-card") as HTMLElement;
    expect(scheduledKpi).toHaveClass("kpi-card--schedule");
    expect(scheduledKpi.firstElementChild?.tagName).toBe("STRONG");
    expect(scheduledKpi).not.toHaveTextContent("Real pickup date");
    expect(screen.getByLabelText("Request workspace")).toContainElement(scheduledKpi.closest(".kpi-grid"));
    const overview = screen.getByRole("heading", { name: "Selected Request Overview" }).closest(".selected-request-overview") as HTMLElement;
    expect(overview).toHaveClass("selected-request-overview--empty");
    expect(overview).toHaveTextContent("Select a request from the queue to view its operational summary.");
    expect(screen.queryByRole("table", { name: "Operational requests" })).not.toBeInTheDocument();
    expect(queue).toHaveTextContent("0 requests");
    expect(screen.queryByRole("button", { name: "Previous page" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Next page" })).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Request pages" })).not.toBeInTheDocument();
  });
  test("keeps search in the toolbar and moves Filters into the Request Queue header", async () => {
    renderAt("/transport-requests");
    await screen.findAllByText("TR-20260806-A1B2C3");
    expect(screen.queryByRole("button", { name: "Apply" })).not.toBeInTheDocument();
    const toolbar = screen.getByRole("tablist", { name: "Transport request views" }).closest(".request-toolbar");
    expect(within(toolbar as HTMLElement).getByLabelText("Search requests")).toBeInTheDocument();
    expect(within(toolbar as HTMLElement).queryByRole("button", { name: "Filters" })).not.toBeInTheDocument();
    const queue = screen.getByLabelText("Request queue");
    expect(within(queue).getByRole("button", { name: "Filters" })).toBeInTheDocument();
    expect(within(queue).getByRole("button", { name: "Filters" }).closest(".panel-title")).not.toBeNull();
  });
  test("live-filters search after 400ms without changing results while typing", async () => {
    const fetchMock = vi.mocked(globalThis.fetch); renderAt("/transport-requests");
    await screen.findAllByText(request.request_number); fetchMock.mockClear(); vi.useFakeTimers();
    fireEvent.change(screen.getByLabelText("Search requests"), { target: { value: "hotel" } });
    await act(async () => { vi.advanceTimersByTime(399); });
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("search=hotel") && !String(input).includes("page_size=5"))).toBe(false);
    await act(async () => { vi.advanceTimersByTime(1); await Promise.resolve(); });
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("search=hotel") && !String(input).includes("page_size=5"))).toBe(true);
  });
  test("Filters panel opens, closes on Escape, and reports active filter count", async () => {
    renderAt("/transport-requests"); await screen.findAllByText(request.request_number);
    const queue = screen.getByLabelText("Request queue");
    const toggle = within(queue).getByRole("button", { name: "Filters" }); fireEvent.click(toggle);
    expect(screen.getByLabelText("Priority")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "HIGH" } });
    fireEvent.change(screen.getByLabelText("Assignment"), { target: { value: "assigned" } });
    expect(screen.getByRole("button", { name: /^Filters/ })).toHaveTextContent("2");
    expect(screen.getByLabelText("2 active filters")).toBeInTheDocument();
    fireEvent.keyDown(screen.getByLabelText("Priority"), { key: "Escape" });
    expect(screen.queryByLabelText("Priority")).not.toBeInTheDocument(); expect(toggle).toHaveFocus();
  });
  test("an advanced filter applies immediately without retaining a page query", async () => {
    const fetchMock = vi.mocked(globalThis.fetch); fetchMock.mockImplementation(input => {
      const url = String(input); if (url.endsWith("summary/")) return json(summary);
      return json({ count: 2, next: url.includes("page=2") ? null : "http://localhost/api/v1/transport-requests/?page=2", previous: url.includes("page=2") ? "http://localhost/api/v1/transport-requests/" : null, results: [request] });
    });
    renderAt("/transport-requests"); await screen.findAllByText(request.request_number);
    fireEvent.change(screen.getByLabelText("Search requests"), { target: { value: "hotel" } });
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => String(input).includes("search=hotel") && !String(input).includes("page_size=5"))).toBe(true));
    fetchMock.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Filters" })); fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "HIGH" } });
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => String(input).includes("search=hotel") && String(input).includes("priority=HIGH") && !String(input).includes("page="))).toBe(true));
    expect(screen.getByRole("tab", { name: /Requests/ })).toHaveAttribute("aria-selected", "true");
  });
  test("starts suggestions only after two characters and the debounce", async () => {
    const fetchMock = vi.mocked(globalThis.fetch); renderAt("/transport-requests");
    await screen.findAllByText(request.request_number); fetchMock.mockClear(); vi.useFakeTimers();
    const search = screen.getByLabelText("Search requests"); fireEvent.change(search, { target: { value: "T" } });
    await act(async () => { vi.advanceTimersByTime(350); });
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("page_size=5"))).toBe(false);
    fireEvent.change(search, { target: { value: "TR" } });
    await act(async () => { vi.advanceTimersByTime(299); });
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("page_size=5"))).toBe(false);
    await act(async () => { vi.advanceTimersByTime(1); await Promise.resolve(); });
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("search=TR") && String(input).includes("page_size=5"))).toBe(true);
  });
  test("shows the suggestion no-results state", async () => {
    vi.mocked(globalThis.fetch).mockImplementation(input => {
      const url = String(input); if (url.endsWith("summary/")) return json(summary);
      if (url.includes("page_size=5")) return json({ count: 0, next: null, previous: null, results: [] });
      return json({ count: 1, next: null, previous: null, results: [request] });
    });
    renderAt("/transport-requests"); await screen.findAllByText(request.request_number); vi.useFakeTimers();
    fireEvent.change(screen.getByLabelText("Search requests"), { target: { value: "ZZ" } });
    await act(async () => { vi.advanceTimersByTime(300); await Promise.resolve(); }); vi.useRealTimers();
    expect(await screen.findByText("No results found")).toBeInTheDocument();
  });
  test("selecting a suggestion applies it on page one and selects the loaded request", async () => {
    const suggested = { ...request, id: "suggested-request", request_number: "TR-SUGGESTED", request_type: "GUEST_TRANSFER" };
    const fetchMock = vi.mocked(globalThis.fetch); fetchMock.mockImplementation(input => {
      const url = String(input); if (url.endsWith("summary/")) return json(summary);
      if (url.includes("page_size=5")) return json({ count: 1, next: null, previous: null, results: [suggested] });
      if (url.includes("search=TR-SUGGESTED")) return json({ count: 1, next: null, previous: null, results: [suggested] });
      return json({ count: 1, next: null, previous: null, results: [request] });
    });
    renderAt("/transport-requests"); await screen.findAllByText(request.request_number); vi.useFakeTimers();
    fireEvent.change(screen.getByLabelText("Search requests"), { target: { value: "TR" } });
    await act(async () => { vi.advanceTimersByTime(300); await Promise.resolve(); }); vi.useRealTimers();
    fireEvent.click(await screen.findByRole("option", { name: /TR-SUGGESTED/ }));
    expect(screen.getByLabelText("Search requests")).toHaveValue("TR-SUGGESTED");
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => String(input).includes("search=TR-SUGGESTED") && !String(input).includes("page="))).toBe(true));
    const queue = await screen.findByLabelText("Request queue");
    expect(within(queue).getByRole("button", { name: /TR-SUGGESTED/ })).toHaveClass("selected");
  });
  test("zero filtered results clear selection and Reset Filters reloads page one", async () => {
    const fetchMock = vi.mocked(globalThis.fetch); fetchMock.mockImplementation(input => {
      const url = String(input); if (url.endsWith("summary/")) return json(summary);
      if (url.includes("search=none")) return json({ count: 0, next: null, previous: null, results: [] });
      return json({ count: 1, next: null, previous: null, results: [request] });
    });
    renderAt("/transport-requests"); await screen.findAllByText(request.request_number);
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "HIGH" } });
    fireEvent.change(screen.getByLabelText("Source"), { target: { value: "MANUAL_STAFF_ENTRY" } });
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "GUEST_TRANSFER" } });
    fireEvent.change(screen.getByLabelText("Assignment"), { target: { value: "assigned" } });
    fireEvent.change(screen.getByLabelText("Scheduled date"), { target: { value: "2026-08-07" } });
    vi.useFakeTimers();
    fireEvent.change(screen.getByLabelText("Search requests"), { target: { value: "none" } });
    await act(async () => { vi.advanceTimersByTime(400); await Promise.resolve(); }); vi.useRealTimers();
    expect(await screen.findByText("No transport requests match your filters.")).toBeInTheDocument();
    expect(screen.getByText("No request selected")).toBeInTheDocument(); expect(screen.getByTestId("request-map")).toBeInTheDocument();
    expect(screen.queryByText(request.requester_name)).not.toBeInTheDocument();
    const emptyQueue = screen.getByText("No transport requests match your filters.").closest(".request-picker-empty") as HTMLElement;
    fireEvent.click(within(emptyQueue).getByRole("button", { name: "Reset Filters" }));
    await screen.findAllByText(request.request_number);
    expect(screen.getByLabelText("Search requests")).toHaveValue(""); expect(screen.queryByLabelText("Priority")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    expect(screen.getByLabelText("Priority")).toHaveValue(""); expect(screen.getByLabelText("Source")).toHaveValue(""); expect(screen.getByLabelText("Type")).toHaveValue(""); expect(screen.getByLabelText("Assignment")).toHaveValue("all"); expect(screen.getByLabelText("Scheduled date")).toHaveValue("");
    expect(screen.queryByLabelText(/active filters/)).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("ordering=scheduled_pickup_at") && !String(input).includes("page="))).toBe(true);
  });
  test("For Approval requests both approval statuses", async () => {
    const fetchMock = vi.mocked(globalThis.fetch); renderAt("/transport-requests");
    await screen.findAllByText("TR-20260806-A1B2C3"); fireEvent.click(screen.getByRole("tab", { name: /For Approval/ }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => String(input).includes("status=FOR_APPROVAL%2CNEEDS_MORE_DETAILS"))).toBe(true));
  });
  test("uses the same rigid workspace and selected overview across operational tabs", async () => {
    renderAt("/transport-requests");
    for (const name of ["Requests", "For Approval", "Dispatch Queue"]) {
      if (name !== "Requests") fireEvent.click(screen.getByRole("tab", { name: new RegExp(name) }));
      const queue = await screen.findByLabelText("Request queue");
      const workspace = queue.closest(".request-workspace");
      expect(workspace).toHaveClass("request-workspace--fixed");
      expect(within(workspace as HTMLElement).getByLabelText("Request map")).toBeInTheDocument();
      expect(within(workspace as HTMLElement).getByRole("heading", { name: "Selected Request Overview" })).toBeInTheDocument();
      expect(screen.queryByRole("table", { name: "Operational requests" })).not.toBeInTheDocument();
      expect(within(queue).getByText(/request(s)?$/)).toHaveClass("queue-count");
      expect(within(queue).queryByLabelText("Request pages")).not.toBeInTheDocument();
      expect(screen.queryByRole("navigation", { name: "Request pages" })).not.toBeInTheDocument();
    }
  });
  test("manager action visibility and required-note dialog", async () => {
    renderAt(`/transport-requests/${request.id}`);
    expect(await screen.findByRole("button", { name: "Approve" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Request More Details" }));
    const confirm = screen.getByRole("button", { name: "Request Details" }); expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Reason (required)"), { target: { value: "Confirm passenger names" } });
    expect(confirm).toBeEnabled();
  });
  test("dispatcher can resubmit but cannot approve or reject", async () => {
    auth.user = { id: 2, username: "dispatch", display_name: "Dispatcher", role: "DISPATCHER" };
    const needsDetails = { ...request, status: "NEEDS_MORE_DETAILS" };
    vi.mocked(globalThis.fetch).mockImplementation(input => String(input).includes("/vehicles/") ? json({ count: 0, next: null, previous: null, results: [] }) : json(needsDetails));
    renderAt(`/transport-requests/${request.id}`);
    expect(await screen.findByRole("button", { name: "Resubmit for Approval" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
  });
  test("Dispatch Queue requests APPROVED and future fields stay honest", async () => {
    const fetchMock = vi.mocked(globalThis.fetch); renderAt("/transport-requests");
    await screen.findAllByText("TR-20260806-A1B2C3"); fireEvent.click(screen.getByRole("tab", { name: /Dispatch Queue/ }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => String(input).includes("status=APPROVED"))).toBe(true));
    expect(screen.getByText("Approved requests ready for dispatch planning. Assignment and optimization are handled in Dispatch Board.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Manual vehicle")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Assign Vehicle|Reassign Vehicle|Mark Ready for Dispatch/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Planned")).not.toBeInTheDocument();
    expect(screen.queryByText(/Juan Dela Cruz|₱/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Route" }));
    expect(screen.getAllByText(/12\.4 km/).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Selected Request Overview" })).toBeInTheDocument();
  });
  test("Calendar hides KPIs and preserves its full-height scroll structure across views", async () => {
    renderAt("/transport-requests"); await screen.findAllByText("TR-20260806-A1B2C3");
    expect(screen.getByText("Scheduled today")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Calendar View" }));
    expect(await screen.findByRole("button", { name: "Daily" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Weekly" })).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText("Vehicle conflict")).toBeInTheDocument();
    expect(screen.queryByText("Scheduled today")).not.toBeInTheDocument();
    expect(document.querySelector(".transport-page")).toHaveClass("transport-page--calendar");
    expect(screen.getByLabelText("Transport request calendar")).toHaveClass("schedule-calendar");
    const weeklyRegion = screen.getByRole("region", { name: "Calendar schedule grid" });
    expect(weeklyRegion).toHaveClass("calendar-scroll-region--weekly");
    expect(weeklyRegion.querySelector(".calendar-grid--weekly")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Daily" }));
    await waitFor(() => expect(screen.getByRole("region", { name: "Calendar schedule grid" })).toHaveClass("calendar-scroll-region--daily"));
    await waitFor(() => expect(document.querySelector(".calendar-grid--daily")).not.toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "Weekly" }));
    await waitFor(() => expect(screen.getByRole("region", { name: "Calendar schedule grid" })).toHaveClass("calendar-scroll-region--weekly"));
    await waitFor(() => expect(document.querySelector(".calendar-grid--weekly")).not.toBeNull());
  });
  test("all tabs retain one full-width panel and planned tabs stay honest", async () => {
    renderAt("/transport-requests"); await screen.findAllByText("TR-20260806-A1B2C3");
    expect(screen.getByRole("tab", { name: /Requests/ }).querySelector(".tab-count")).toHaveTextContent("1");
    for (const name of ["Active Trips", "Completed", "Calendar View"]) {
      expect(screen.getByRole("tab", { name }).querySelector(".tab-count")).toBeNull();
    }
    for (const name of ["Requests", "For Approval", "Dispatch Queue", "Active Trips", "Completed", "Calendar View"]) {
      fireEvent.click(screen.getByRole("tab", { name: new RegExp(name) }));
      expect(document.querySelectorAll(".transport-tab-panel")).toHaveLength(1);
      expect(document.querySelector(".transport-tab-panel")).toHaveClass(`transport-tab-panel--${name.toLowerCase().replaceAll(" ", "-")}`);
    }
    fireEvent.click(screen.getByRole("tab", { name: "Active Trips" }));
    expect(screen.getByText("Active trip execution is not available yet")).toBeInTheDocument();
    expect(screen.getByText("Active trip execution will appear here once driver assignment and trip lifecycle functionality are available.")).toBeInTheDocument();
    expect(document.querySelector(".transport-page")).toHaveClass("transport-page--workspace", "transport-page--planned");
    fireEvent.click(screen.getByRole("tab", { name: "Completed" }));
    expect(screen.getByText("Completed trip history is not available yet")).toBeInTheDocument();
    expect(screen.getByText("Completed lifecycle records will appear here once real trip completion functionality is available. No completed trips are fabricated.")).toBeInTheDocument();
    expect(screen.getByText("Completed trip history is not available yet").closest(".transport-tab-panel")).toHaveClass("transport-tab-panel--completed");
    expect(screen.queryByText(/completed trip #|proof uploaded|final cost/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Calendar View" }));
    expect(await screen.findByTestId("calendar-scroll-region")).toHaveClass("calendar-scroll-region--weekly");
    expect(screen.getByLabelText("Transport request calendar").closest(".transport-tab-panel")).not.toBeNull();
  });
  test("Dispatch Queue is a read-only lifecycle handoff without assignment controls", async () => {
    const assignedVehicle = { device_id: "VAN-01", plate_number: "VAN-01", display_name: "Guest Van", vehicle_type: "VAN", passenger_capacity: 6, is_active: true };
    const assigned = { ...request, id: "assigned-request", request_number: "TR-ASSIGNED", status: "APPROVED", assigned_vehicle: assignedVehicle };
    const unassigned = { ...request, id: "unassigned-request", request_number: "TR-UNASSIGNED", status: "APPROVED", assigned_vehicle: null };
    vi.mocked(globalThis.fetch).mockImplementation(input => {
      const url = String(input);
      if (url.endsWith("summary/")) return json({ ...summary, dispatch_queue: 2, approved_assigned: 1, approved_unassigned: 1 });
      if (url.includes("/vehicles/")) return json({ count: 1, next: null, previous: null, results: [assignedVehicle] });
      return json({ count: 2, next: null, previous: null, results: [assigned, unassigned] });
    });
    renderAt("/transport-requests"); await screen.findAllByText("TR-ASSIGNED");
    fireEvent.click(screen.getByRole("tab", { name: /Dispatch Queue/ }));
    await screen.findByText("Approved requests ready for dispatch planning. Assignment and optimization are handled in Dispatch Board.");
    expect(screen.queryByLabelText("Manual vehicle")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Assign Vehicle|Reassign Vehicle|Mark Ready for Dispatch/i })).not.toBeInTheDocument();
    const unassignedButton = screen.getAllByRole("button").find(button => button.textContent?.includes("TR-UNASSIGNED"));
    expect(unassignedButton).toBeDefined(); fireEvent.click(unassignedButton!);
    fireEvent.click(screen.getByRole("button", { name: /Refresh/ }));
    await waitFor(() => expect(screen.queryByLabelText("Manual vehicle")).not.toBeInTheDocument());
    expect(screen.getAllByText("Awaiting dispatch planning").length).toBeGreaterThan(0);
  });
  test("uses the full-width responsive layout for Edit Transport Request", async () => {
    renderAt(`/transport-requests/${request.id}/edit`);
    const heading = await screen.findByRole("heading", { name: "Edit Transport Request" });
    const page = heading.closest(".form-page"); const form = screen.getByRole("button", { name: "Save Changes" }).closest("form");
    expect(page).toHaveClass("form-page--edit-request"); expect(form).toHaveClass("request-form--edit");
    expect(screen.getByLabelText("Pickup address").closest("label")).toHaveClass("edit-field--wide");
    expect(screen.getByLabelText("Destination address").closest("label")).toHaveClass("edit-field--wide");
    expect(screen.getByLabelText("Notes").closest("label")).toHaveClass("edit-field--long");
    expect(within(form as HTMLElement).getByRole("link", { name: "Cancel" })).toBeInTheDocument();
  });
  test("renders backend field and non-field errors without discarding form values", async () => {
    vi.mocked(globalThis.fetch).mockImplementation((_input, init) => init?.method === "POST"
      ? errorJson({ request_type: ["Choose a supported request type."], passenger_count: ["Too many passengers."], pickup_address: ["Confirm the pickup address."], notes: ["Notes need review."], non_field_errors: ["Pickup and destination must differ."] })
      : json(summary));
    renderAt("/transport-requests/new");
    fireEvent.change(screen.getByLabelText("Scheduled pickup"), { target: { value: "2026-08-07T10:00" } });
    fireEvent.change(screen.getByLabelText("Requester name"), { target: { value: "Keep this value" } });
    fireEvent.submit(screen.getByRole("button", { name: "Create Request" }).closest("form")!);
    expect(await screen.findByText("Choose a supported request type.")).toBeInTheDocument();
    expect(screen.getByText("Pickup and destination must differ.")).toBeInTheDocument();
    expect(screen.getByLabelText(/Request type/)).toHaveAttribute("aria-describedby", "request_type-error");
    expect(screen.getByLabelText(/Passengers/)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Requester name")).toHaveValue("Keep this value");
  });
});
