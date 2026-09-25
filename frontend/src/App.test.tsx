import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryHistory } from "history";
import { MemoryRouter, Router } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import type { Role } from "./services/auth";

const auth = vi.hoisted(() => ({
  user: { id: 1, username: "staff", display_name: "Staff User", role: "DISPATCHER" as Role, capabilities: [
    "TRANSPORT_REQUESTS.VIEW", "TRANSPORT_REQUESTS.EDIT", "DISPATCH_BOARD.VIEW",
    "DISPATCH_BOARD.DISPATCH", "LIVE_MAP.VIEW", "DRIVERS.VIEW", "VEHICLES.VIEW",
    "VEHICLES.EDIT", "FUEL_ANALYTICS.VIEW", "MAINTENANCE.VIEW",
    "ALERTS_SOS.VIEW", "SYSTEM_SETTINGS.VIEW", "USERS_ACCESS.VIEW_USERS",
  ] },
  loading: false, sessionMessage: "", signIn: vi.fn(), completeTwoFactor: vi.fn(),
  completeRequiredMfaEnrollment: vi.fn(), signOut: vi.fn(), expire: vi.fn(),
  activateEnrolledSession: vi.fn(),
}));
vi.mock("./contexts/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("./services/sidebarService", () => ({
  fetchSidebarCounts: async () => ({}),
}));
vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="map">{children}</div>,
  TileLayer: () => <span>© OpenStreetMap contributors</span>,
  CircleMarker: ({ center }: { center: [number, number] }) => <span data-testid="marker">{center.join(",")}</span>,
  useMap: () => ({ setView: vi.fn() }),
}));

const vehicle = {
  device_id: "LILYGO-001", plate_number: "DEMO-001", display_name: "Sprint 1 Demo Vehicle",
  vehicle_type: "OTHER", manufacturer: "", model: "", model_year: null,
  passenger_capacity: null, payload_capacity_kg: null, gvwr_kg: null, is_active: true,
  vin: "", engine_number: "", chassis_number: "", color: "", fuel_type: "", fuel_grade: "",
  transmission_type: "", ownership_type: "", supplier_name: "",
  purchase_order_number: "", acquisition_date: null, purchase_price: null,
  purchase_currency: "", warranty_expiry_date: null, registration_expiry_date: null,
  insurance_expiry_date: null, document_count: 0, document_health: "INCOMPLETE",
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
  latest_inspection: null,
};
const inspection = {
  id: 7, vehicle: 1, inspection_date: "2026-08-12", inspection_type: "PRE_TRIP", result: "NEEDS_ATTENTION",
  odometer_km: 12500, fuel_level_percent: 75, exterior_condition: "OK", interior_condition: "OK",
  tires_condition: "NEEDS_ATTENTION", lights_condition: "OK", brakes_condition: "OK", fluids_condition: "OK",
  safety_equipment_condition: "NOT_CHECKED", notes: "Recheck tires", issues_found: "Rear tire wear",
  inspected_by: 2, inspector_name: "Fleet Manager", created_at: "2026-08-12T01:00:00Z", updated_at: "2026-08-12T01:00:00Z",
};
class FakeWebSocket {
  onopen: (() => void) | null = null; onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null; onclose: ((event: CloseEvent) => void) | null = null;
  close(code = 1000) { this.onclose?.({ code } as CloseEvent); }
}
function response(value: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } }));
}
function renderAt(path: string) {
  return render(<StrictMode><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></StrictMode>);
}
function renderWithHistory(path: string, state?: unknown) {
  const history = createMemoryHistory({ initialEntries: [{ pathname: path, state }] });
  return {
    history,
    ...render(<StrictMode><Router history={history}><App /></Router></StrictMode>),
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
let intersectionCallback: IntersectionObserverCallback | null = null;
class FakeIntersectionObserver {
  constructor(callback: IntersectionObserverCallback) { intersectionCallback = callback; }
  observe() { return undefined; }
  disconnect() { return undefined; }
  unobserve() { return undefined; }
  takeRecords() { return []; }
  readonly root = null; readonly rootMargin = "0px"; readonly thresholds = [0];
}

beforeEach(() => {
  auth.user = { id: 1, username: "staff", display_name: "Staff User", role: "DISPATCHER", capabilities: [
    "TRANSPORT_REQUESTS.VIEW", "TRANSPORT_REQUESTS.EDIT", "DISPATCH_BOARD.VIEW",
    "DISPATCH_BOARD.DISPATCH", "LIVE_MAP.VIEW", "DRIVERS.VIEW", "VEHICLES.VIEW",
    "VEHICLES.EDIT", "FUEL_ANALYTICS.VIEW", "MAINTENANCE.VIEW",
    "ALERTS_SOS.VIEW", "SYSTEM_SETTINGS.VIEW", "USERS_ACCESS.VIEW_USERS",
  ] };
  auth.loading = false; auth.sessionMessage = ""; auth.signIn.mockReset(); auth.completeTwoFactor.mockReset();
  auth.completeRequiredMfaEnrollment.mockReset(); auth.signOut.mockReset();
  auth.activateEnrolledSession.mockReset();
  vi.stubGlobal("WebSocket", FakeWebSocket);
  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
  intersectionCallback = null;
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("administration workspace routing", () => {
  test("renders the real Alerts & Incidents route instead of the planned placeholder", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({
      count: 0, next: null, previous: null, results: [],
      summary: { active_attention: 0, safety_events_today: 0, restricted_entries_today: 0, vehicle_device_attention: 0 },
    }));
    renderAt("/alerts");
    expect(await screen.findByRole("heading", { name: "Alerts & Incidents" })).toBeInTheDocument();
    expect(screen.queryByText("Planned module")).not.toBeInTheDocument();
  });

  test.each([
    ["/settings", "Settings Overview"],
    ["/settings/security", "Security"],
    ["/settings/operational-rules", /Operational Rules/],
    ["/settings/integrations", "Integrations"],
  ])("renders the Settings workspace route %s", async (path, heading) => {
    renderAt(path);
    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
  });

  test("redirects the retired Settings permission route to Users & Access", async () => {
    auth.user.role = "FLEET_ADMIN";
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({
      definitions: { TRANSPORT_REQUESTS: ["VIEW"] },
      roles: { FLEET_MANAGER: { TRANSPORT_REQUESTS: ["VIEW"] }, DISPATCHER: { TRANSPORT_REQUESTS: ["VIEW"] } },
    }));
    const { history } = renderWithHistory("/settings/roles-permissions");
    await waitFor(() => expect(history.location.pathname).toBe("/users/roles-permissions"));
    expect(await screen.findByRole("link", { name: "Roles & Permissions" })).toHaveClass("active");
  });

  test("renders the truthful Audit Logs placeholder at its Users route", async () => {
    auth.user.role = "FLEET_ADMIN";
    renderAt("/users/audit-logs");
    expect(await screen.findByText("Centralized administrative audit logging is not available yet.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("Sprint 3 secure registry", () => {
  test("redirects an anonymous user to login", async () => {
    auth.user = null as unknown as typeof auth.user;
    renderAt("/vehicles");
    expect(await screen.findByRole("heading", { name: "Sign in to FTMS" })).toBeInTheDocument();
  });
  test("invalid login displays only the generic message", async () => {
    auth.user = null as unknown as typeof auth.user;
    auth.signIn.mockRejectedValueOnce(new Error("internal credential detail"));
    renderAt("/login");
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "staff" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret" } });
    fireEvent.click(screen.getByText("Sign in"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to sign in with those credentials.");
    expect(screen.queryByText(/internal credential detail/)).not.toBeInTheDocument();
    expect(screen.getByText("Sign in")).toBeEnabled();
  });
  test("temporary login lockout displays a safe wait message and countdown", async () => {
    auth.user = null as unknown as typeof auth.user;
    auth.signIn.mockRejectedValueOnce({ code: "temporarily_locked", retryAfterSeconds: 60 });
    renderAt("/login");
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "staff" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret" } });
    fireEvent.click(screen.getByText("Sign in"));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Too many failed sign-in attempts. Please try again in 1 minute.",
    );
    expect(screen.queryByText(/staff is locked|account exists|failed attempt/i)).not.toBeInTheDocument();
    expect(screen.getByText("Sign in")).toBeDisabled();

    fireEvent.click(screen.getByText("Sign in"));
    expect(auth.signIn).toHaveBeenCalledTimes(1);
  });
  test("login displays the authenticated-session expiration reason", async () => {
    auth.user = null as unknown as typeof auth.user;
    auth.sessionMessage = "Your session expired due to inactivity. Please sign in again.";
    renderAt("/login");
    expect(screen.getByRole("status")).toHaveTextContent(auth.sessionMessage);
  });
  test("successful login follows a safe internal redirect under StrictMode", async () => {
    auth.user = null as unknown as typeof auth.user;
    auth.signIn.mockImplementationOnce(async () => {
      auth.user = { id: 1, username: "staff", display_name: "Staff User", role: "DISPATCHER", capabilities: ["VEHICLES.VIEW"] };
      return { kind: "authenticated", user: auth.user };
    });
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response(vehicle));
    const { history } = renderWithHistory("/login", { from: "/vehicles/LILYGO-001" });
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "staff" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret" } });
    fireEvent.submit(screen.getByRole("button", { name: "Sign in" }).closest("form")!);
    await waitFor(() => expect(history.location.pathname).toBe("/vehicles/LILYGO-001"));
  });
  test("two-factor login keeps the user unauthenticated until verification", async () => {
    auth.user = null as unknown as typeof auth.user;
    auth.signIn.mockResolvedValueOnce({ kind: "two_factor_required", challengeToken: "memory-only-challenge" });
    auth.completeTwoFactor.mockResolvedValueOnce(undefined);
    renderAt("/login");
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "staff" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret" } });
    fireEvent.click(screen.getByText("Sign in"));
    expect(await screen.findByRole("heading", { name: "Two-Factor Authentication" })).toBeInTheDocument();
    expect(auth.user).toBeNull();
    expect(screen.queryByLabelText("Username")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Use recovery code" }));
    expect(screen.getByLabelText("Recovery code")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Use authenticator code" }));
    fireEvent.change(screen.getByLabelText("Authenticator code"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify" }));
    await waitFor(() => expect(auth.completeTwoFactor).toHaveBeenCalledWith("memory-only-challenge", "totp", "123456"));
  });
  test("mandatory MFA enrollment blocks navigation until setup is confirmed", async () => {
    auth.user = null as unknown as typeof auth.user;
    auth.signIn.mockResolvedValueOnce({
      kind: "mfa_enrollment_required",
      challengeToken: "enrollment-challenge",
      setup: {
        provisioning_uri: "otpauth://totp/FTMS:manager?secret=TEST",
        manual_setup_key: "TEST-MANUAL-KEY",
        issuer: "FTMS",
        account_label: "manager",
      },
    });
    auth.completeRequiredMfaEnrollment.mockResolvedValueOnce(["RECOVERY-ONE", "RECOVERY-TWO"]);
    auth.activateEnrolledSession.mockImplementationOnce(async () => {
      auth.user = {
        id: 2, username: "manager", display_name: "Fleet Manager",
        role: "FLEET_MANAGER", capabilities: ["DASHBOARD.VIEW"],
      };
    });
    const { history } = renderWithHistory("/login", { from: "/dashboard" });
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "manager" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret" } });
    fireEvent.click(screen.getByText("Sign in"));

    expect(await screen.findByRole("heading", { name: "Set Up Two-Factor Authentication" })).toBeInTheDocument();
    expect(screen.getByText("TEST-MANUAL-KEY")).toBeInTheDocument();
    expect(history.location.pathname).toBe("/login");
    expect(auth.user).toBeNull();

    fireEvent.change(screen.getByLabelText("Authenticator code"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Enable MFA and continue" }));
    expect(await screen.findByText(/RECOVERY-ONE/)).toBeInTheDocument();
    expect(history.location.pathname).toBe("/login");
    fireEvent.click(screen.getByRole("button", { name: "I have saved these codes" }));
    await waitFor(() => expect(history.location.pathname).toBe("/dashboard"));
  });
  test("rapid login submissions invoke sign-in once", async () => {
    auth.user = null as unknown as typeof auth.user;
    const pending = deferred<{ kind: "authenticated"; user: typeof auth.user }>(); auth.signIn.mockReturnValue(pending.promise);
    renderAt("/login");
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "staff" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret" } });
    const form = screen.getByRole("button", { name: "Sign in" }).closest("form")!;
    fireEvent.submit(form); fireEvent.submit(form);
    expect(auth.signIn).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Signing in…")).toBeDisabled();
  });
  test("restores a dispatcher list without write controls", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ count: 1, next: null, previous: null, results: [vehicle] }));
    renderAt("/vehicles");
    const row = (await screen.findByText("Sprint 1 Demo Vehicle")).closest("tr")!;
    for (const heading of ["Vehicle", "Plate", "Type", "Make / Model", "Capacity", "Inspection", "Compliance Records", "Documents", "Status", "Actions"]) expect(screen.getByRole("columnheader", { name: heading })).toBeInTheDocument();
    expect(within(row).getByText("LILYGO-001")).toBeInTheDocument();
    expect(within(row).getByText("Unavailable")).toBeInTheDocument();
    expect(within(row).getByText("Pax: —")).toBeInTheDocument();
    expect(within(row).getByText("Payload: —")).toBeInTheDocument();
    expect(within(row).getByText("Incomplete")).toBeInTheDocument();
    expect(within(row).getByText("Active")).toBeInTheDocument();
    fireEvent.click(within(row).getByRole("button", { name: "More actions for Sprint 1 Demo Vehicle" }));
    const menu = within(row).getByRole("menu");
    expect(within(menu).getByRole("menuitem", { name: "View vehicle" })).toBeInTheDocument();
    expect(menu).toHaveClass("vehicle-row-menu-popover--above");
    expect(screen.queryByText("+ Add Vehicle")).not.toBeInTheDocument();
    expect(screen.queryByText("Edit")).not.toBeInTheDocument();
    expect(screen.queryByText("Deactivate")).not.toBeInTheDocument();
    expect(screen.queryByText("Add inspection")).not.toBeInTheDocument();
  });
  test("dense rows render make, model, year, capacity, and inactive status", async () => {
    const inactive = { ...vehicle, device_id: "VAN-002", plate_number: "VAN-002", display_name: "Guest Shuttle", vehicle_type: "SHUTTLE_BUS", manufacturer: "Toyota", model: "Coaster", model_year: 2025, passenger_capacity: 28, is_active: false };
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ count: 1, next: null, previous: null, results: [inactive] }));
    renderAt("/vehicles");
    const row = (await screen.findByText("Guest Shuttle")).closest("tr")!;
    expect(within(row).getByText("Toyota Coaster")).toBeInTheDocument();
    expect(within(row).getByText("2025")).toBeInTheDocument();
    expect(within(row).getByText("Pax: 28")).toBeInTheDocument();
    expect(within(row).getByText("Shuttle Bus")).toBeInTheDocument();
    expect(within(row).getByText("Inactive")).toBeInTheDocument();
  });
  test("surfaces real payload, GVWR, and compliance records without fake rollups", async () => {
    const completed = { ...vehicle, payload_capacity_kg: "950.50", gvwr_kg: "6350.00" };
    vi.spyOn(globalThis, "fetch").mockImplementation(input => String(input).includes("/documents/")
      ? response({ count: 0, next: null, previous: null, results: [] })
      : response({ count: 1, next: null, previous: null, results: [completed] }));
    renderAt("/vehicles");
    const row = (await screen.findByText("Sprint 1 Demo Vehicle")).closest("tr")!;
    expect(within(row).getByText("Payload: 950.50 kg")).toBeInTheDocument();
    fireEvent.click(within(row).getByRole("button", { name: "More actions for Sprint 1 Demo Vehicle" }));
    fireEvent.click(within(row).getByRole("menuitem", { name: "View vehicle" }));
    const drawer = screen.getByRole("dialog");
    expect(within(drawer).getByText("6350.00 kg")).toBeInTheDocument();
    fireEvent.click(within(drawer).getByRole("tab", { name: "Compliance" }));
    expect(await within(drawer).findByText("No compliance evidence recorded.")).toBeInTheDocument();
    expect(within(drawer).queryByText(/safety score|maintenance risk|fuel trend/i)).not.toBeInTheDocument();
  });
  test("fleet manager receives row Edit but not status actions", async () => {
    auth.user.role = "FLEET_MANAGER";
    auth.user.capabilities.push("INSPECTIONS.CREATE");
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ count: 1, next: null, previous: null, results: [vehicle] }));
    const { history } = renderWithHistory("/vehicles");
    const row = (await screen.findByText("Sprint 1 Demo Vehicle")).closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: "More actions for Sprint 1 Demo Vehicle" }));
    expect(within(row).getByRole("menuitem", { name: "Add inspection" })).toBeInTheDocument();
    expect(within(row).queryByText("Deactivate")).not.toBeInTheDocument();
    fireEvent.click(within(row).getByRole("menuitem", { name: "Edit vehicle" }));
    const editDrawer = screen.getByRole("dialog", { name: "Edit Sprint 1 Demo Vehicle" });
    expect(history.location.pathname).toBe("/vehicles");
    expect(within(editDrawer).getByLabelText("Display name")).toHaveValue("Sprint 1 Demo Vehicle");
  });
  test("super admin receives compact row status action", async () => {
    auth.user.role = "FLEET_ADMIN";
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ count: 1, next: null, previous: null, results: [vehicle] }));
    renderAt("/vehicles");
    const row = (await screen.findByText("Sprint 1 Demo Vehicle")).closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: "More actions for Sprint 1 Demo Vehicle" }));
    expect(within(row).getByRole("menuitem", { name: "Edit vehicle" })).toBeInTheDocument();
    expect(within(row).getByRole("menuitem", { name: "Deactivate" })).toBeInTheDocument();
  });
  test("fleet manager can edit but cannot create or change status", async () => {
    auth.user.role = "FLEET_MANAGER";
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response(vehicle));
    renderAt("/vehicles/LILYGO-001");
    expect(await screen.findByText("Edit")).toBeInTheDocument();
    expect(screen.queryByText("Deactivate")).not.toBeInTheDocument();
  });
  test("super admin receives create and status controls", async () => {
    auth.user.role = "FLEET_ADMIN";
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ count: 0, next: null, previous: null, results: [] }));
    renderAt("/vehicles");
    expect(await screen.findByText("+ Add Vehicle")).toBeInTheDocument();
    expect(screen.getByText("No vehicles match these filters.")).toBeInTheDocument();
  });
  test("list exposes loading, filtering, and error states", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ count: 0, next: null, previous: null, results: [] }));
    renderAt("/vehicles"); expect(screen.getByText("Loading vehicles…")).toBeInTheDocument();
    await screen.findByText("No vehicles match these filters.");
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "demo" } });
    await waitFor(() => expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain("search=demo"));
  });
  test("vehicle search updates the table after typing and restores it when cleared", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(input => {
      const url = String(input);
      return response(url.includes("search=missing")
        ? { count: 0, next: null, previous: null, results: [] }
        : { count: 1, next: null, previous: null, results: [vehicle] });
    });
    renderAt("/vehicles");
    await screen.findByText("Sprint 1 Demo Vehicle");
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "missing" } });
    expect(await screen.findByText("No vehicles match these filters.")).toBeInTheDocument();
    expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain("search=missing");
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "" } });
    expect(await screen.findByText("Sprint 1 Demo Vehicle")).toBeInTheDocument();
    expect(String(fetchMock.mock.calls.at(-1)?.[0])).toMatch(/\/api\/v1\/vehicles\/$/);
  });
  test("list error remains inside the table area", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network"));
    renderAt("/vehicles");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Unable to load vehicles.");
    expect(alert.closest("td")).toHaveAttribute("colspan", "10");
  });
  test("vehicle table appends the next backend page without visible pagination controls", async () => {
    const second = { ...vehicle, device_id: "VAN-002", display_name: "Guest Shuttle", plate_number: "VAN-002" };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(input => String(input).includes("page=2")
      ? response({ count: 21, previous: "http://localhost/api/v1/vehicles/", next: null, results: [vehicle, second] })
      : response({ count: 21, previous: null, next: "http://localhost/api/v1/vehicles/?page=2", results: [vehicle] }));
    renderAt("/vehicles");
    await screen.findByText("Sprint 1 Demo Vehicle");
    expect(screen.queryByRole("button", { name: "Previous" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Next" })).not.toBeInTheDocument();
    await waitFor(() => expect(intersectionCallback).not.toBeNull());
    act(() => intersectionCallback?.([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver));
    await waitFor(() => expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain("page=2"));
    expect(await screen.findByText("Guest Shuttle")).toBeInTheDocument();
    expect(screen.getAllByText("Sprint 1 Demo Vehicle")).toHaveLength(1);
    expect(screen.getByText("21 vehicles")).toBeInTheDocument();
  });
  test("next-page loading keeps the drawer open and reports progress accessibly", async () => {
    const nextResponse = deferred<Response>();
    const second = { ...vehicle, device_id: "VAN-002", display_name: "Guest Shuttle", plate_number: "VAN-002" };
    vi.spyOn(globalThis, "fetch").mockImplementation(input => String(input).includes("page=2")
      ? nextResponse.promise
      : response({ count: 2, previous: null, next: "http://localhost/api/v1/vehicles/?page=2", results: [vehicle] }));
    renderAt("/vehicles"); await screen.findByText("Sprint 1 Demo Vehicle");
    fireEvent.click(screen.getByRole("button", { name: "More actions for Sprint 1 Demo Vehicle" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "View vehicle" }));
    await waitFor(() => expect(intersectionCallback).not.toBeNull());
    act(() => intersectionCallback?.([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver));
    expect(await screen.findByRole("status")).toHaveTextContent("Loading more vehicles…");
    await act(async () => nextResponse.resolve(await response({ count: 2, previous: null, next: null, results: [second] })));
    expect(await screen.findByText("Guest Shuttle")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Sprint 1 Demo Vehicle" })).toBeInTheDocument();
  });
  test("next-page failure preserves loaded rows and offers retry", async () => {
    let nextAttempts = 0;
    const second = { ...vehicle, device_id: "VAN-002", display_name: "Guest Shuttle", plate_number: "VAN-002" };
    vi.spyOn(globalThis, "fetch").mockImplementation(input => {
      if (!String(input).includes("page=2")) return response({ count: 2, previous: null, next: "http://localhost/api/v1/vehicles/?page=2", results: [vehicle] });
      nextAttempts += 1;
      return nextAttempts === 1 ? Promise.reject(new Error("network")) : response({ count: 2, previous: null, next: null, results: [second] });
    });
    renderAt("/vehicles"); await screen.findByText("Sprint 1 Demo Vehicle");
    await waitFor(() => expect(intersectionCallback).not.toBeNull());
    act(() => intersectionCallback?.([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load more vehicles.");
    expect(screen.getByText("Sprint 1 Demo Vehicle")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Guest Shuttle")).toBeInTheDocument();
  });
  test("filter reset prevents a stale next page from contaminating new results", async () => {
    const staleResponse = deferred<Response>();
    const filtered = { ...vehicle, device_id: "INACTIVE-001", display_name: "Inactive Van", plate_number: "VAN-009", is_active: false };
    const stale = { ...vehicle, device_id: "STALE-002", display_name: "Stale Vehicle", plate_number: "OLD-002" };
    vi.spyOn(globalThis, "fetch").mockImplementation(input => {
      const url = String(input);
      if (url.includes("is_active=false")) return response({ count: 1, previous: null, next: null, results: [filtered] });
      if (url.includes("page=2")) return staleResponse.promise;
      return response({ count: 2, previous: null, next: "http://localhost/api/v1/vehicles/?page=2", results: [vehicle] });
    });
    renderAt("/vehicles"); await screen.findByText("Sprint 1 Demo Vehicle");
    await waitFor(() => expect(intersectionCallback).not.toBeNull());
    act(() => intersectionCallback?.([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver));
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "false" } });
    expect(await screen.findByText("Inactive Van")).toBeInTheDocument();
    await act(async () => staleResponse.resolve(await response({ count: 2, previous: null, next: null, results: [stale] })));
    expect(screen.queryByText("Stale Vehicle")).not.toBeInTheDocument();
    expect(screen.queryByText("Sprint 1 Demo Vehicle")).not.toBeInTheDocument();
  });
  test("filter selections apply immediately and All options clear them", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ count: 0, next: null, previous: null, results: [] }));
    renderAt("/vehicles"); await screen.findByText("No vehicles match these filters.");
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "false" } });
    fireEvent.change(screen.getByLabelText("Vehicle Type"), { target: { value: "VAN" } });
    await waitFor(() => expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain("vehicle_type=VAN"));
    expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain("is_active=false");
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Vehicle Type"), { target: { value: "" } });
    expect(screen.getByLabelText("Status")).toHaveValue(""); expect(screen.getByLabelText("Vehicle Type")).toHaveValue("");
    await waitFor(() => expect(String(fetchMock.mock.calls.at(-1)?.[0])).toMatch(/\/api\/v1\/vehicles\/$/));
  });
  test("Export Loaded Vehicles creates CSV from only the loaded rows", async () => {
    const second = { ...vehicle, device_id: "VAN-002", display_name: "Guest Shuttle", plate_number: "VAN-002", vehicle_type: "VAN", manufacturer: "Toyota", model: "Hiace", model_year: 2025, passenger_capacity: 12, is_active: false };
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ count: 50, next: "http://localhost/api/v1/vehicles/?page=2", previous: null, results: [vehicle, second] }));
    let csv = ""; class CsvBlob { constructor(parts: BlobPart[]) { csv = String(parts[0]); } }
    vi.stubGlobal("Blob", CsvBlob); vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:vehicles"), revokeObjectURL: vi.fn() }); vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    renderAt("/vehicles"); await screen.findByText("Guest Shuttle"); fireEvent.click(screen.getByText("Export Loaded Vehicles"));
    expect(csv).toContain('"Display Name","Device ID"'); expect(csv).toContain('"Sprint 1 Demo Vehicle","LILYGO-001"'); expect(csv).toContain('"Guest Shuttle","VAN-002"'); expect(csv).not.toContain("50 vehicles");
  });
  test("View opens an in-content drawer, selection updates, Close restores the table", async () => {
    const second = { ...vehicle, device_id: "VAN-002", display_name: "Guest Shuttle", plate_number: "VAN-002" };
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ count: 2, next: null, previous: null, results: [vehicle, second] }));
    const { history } = renderWithHistory("/vehicles"); await screen.findByText("Guest Shuttle");
    fireEvent.click(screen.getByRole("button", { name: "More actions for Sprint 1 Demo Vehicle" })); fireEvent.click(screen.getByRole("menuitem", { name: "View vehicle" }));
    let drawer = screen.getByRole("dialog", { name: "Sprint 1 Demo Vehicle" }); expect(history.location.pathname).toBe("/vehicles"); expect(within(drawer).getByText("DEMO-001")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "More actions for Guest Shuttle" })); fireEvent.click(screen.getByRole("menuitem", { name: "View vehicle" })); drawer = screen.getByRole("dialog", { name: "Guest Shuttle" }); expect(within(drawer).getAllByText("VAN-002").length).toBeGreaterThan(0);
    fireEvent.click(within(drawer).getByRole("button", { name: "Close vehicle details" })); expect(screen.queryByRole("dialog")).not.toBeInTheDocument(); expect(screen.getByRole("table")).toBeInTheDocument();
  });
  test("omits the redundant Open full vehicle menu action", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ count: 1, next: null, previous: null, results: [vehicle] }));
    renderAt("/vehicles"); await screen.findByText("Sprint 1 Demo Vehicle"); fireEvent.click(screen.getByRole("button", { name: "More actions for Sprint 1 Demo Vehicle" }));
    expect(screen.queryByRole("menuitem", { name: "Open full vehicle" })).not.toBeInTheDocument();
  });
  test("table and drawer show real inspection summary, history, detail, and pagination", async () => {
    const inspectedVehicle = { ...vehicle, latest_inspection: { id: inspection.id, inspection_date: inspection.inspection_date, inspection_type: inspection.inspection_type, result: inspection.result } };
    vi.spyOn(globalThis, "fetch").mockImplementation(input => String(input).includes("/inspections/") ? response({ count: 11, previous: null, next: "http://localhost/api/v1/vehicles/LILYGO-001/inspections/?page=2", results: [inspection] }) : response({ count: 1, next: null, previous: null, results: [inspectedVehicle] }));
    renderAt("/vehicles"); const row = (await screen.findByText("Sprint 1 Demo Vehicle")).closest("tr")!; expect(within(row).getByText("Needs Attention")).toBeInTheDocument();
    fireEvent.click(within(row).getByRole("button", { name: "More actions for Sprint 1 Demo Vehicle" })); fireEvent.click(within(row).getByRole("menuitem", { name: "View vehicle" })); const drawer = screen.getByRole("dialog"); fireEvent.click(within(drawer).getByRole("tab", { name: "Inspections" }));
    await waitFor(() => expect(drawer).toHaveTextContent("Fleet Manager")); expect(within(drawer).getByText("11 inspections")).toBeInTheDocument(); expect(within(drawer).getByRole("button", { name: "Next" })).toBeEnabled();
    fireEvent.click(within(drawer).getByRole("button", { name: "View Inspection" })); expect(within(drawer).getByText("Rear tire wear")).toBeInTheDocument(); expect(within(drawer).getByText("12,500 km")).toBeInTheDocument(); expect(within(drawer).getByText("75%")).toBeInTheDocument();
  });
  test("inspection tab has an honest empty state for a dispatcher", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(input => String(input).includes("/inspections/") ? response({ count: 0, previous: null, next: null, results: [] }) : response({ count: 1, next: null, previous: null, results: [vehicle] }));
    renderAt("/vehicles"); await screen.findByText("Sprint 1 Demo Vehicle"); fireEvent.click(screen.getByRole("button", { name: "More actions for Sprint 1 Demo Vehicle" })); fireEvent.click(screen.getByRole("menuitem", { name: "View vehicle" })); const drawer = screen.getByRole("dialog"); fireEvent.click(within(drawer).getByRole("tab", { name: "Inspections" }));
    expect(await within(drawer).findByText("No inspections recorded.")).toBeInTheDocument(); expect(within(drawer).queryByText("+ Add Inspection")).not.toBeInTheDocument();
  });
  test("documents tab is truthful and dispatcher cannot upload", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(input => String(input).includes("/documents/") ? response({ count: 0, previous: null, next: null, results: [] }) : response({ count: 1, next: null, previous: null, results: [vehicle] }));
    renderAt("/vehicles"); await screen.findByText("Sprint 1 Demo Vehicle"); fireEvent.click(screen.getByRole("button", { name: "More actions for Sprint 1 Demo Vehicle" })); expect(screen.queryByRole("menuitem", { name: "View inspections" })).not.toBeInTheDocument(); expect(screen.queryByRole("menuitem", { name: "View documents" })).not.toBeInTheDocument(); fireEvent.click(screen.getByRole("menuitem", { name: "View vehicle" }));
    const drawer = screen.getByRole("dialog"); fireEvent.click(within(drawer).getByRole("tab", { name: "Documents" })); expect(await within(drawer).findByText("No vehicle documents recorded.")).toBeInTheDocument(); expect(within(drawer).queryByText("+ Upload Document")).not.toBeInTheDocument();
  });
  test("fleet manager uploads a real document without client-forged uploader", async () => {
    auth.user.role = "FLEET_MANAGER"; let submitted: FormData | null = null;
    const document = { id: 3, vehicle: 1, document_type: "INSURANCE", title: "Insurance", reference_number: "INS-1", issuer_name: "", issued_date: null, effective_date: null, expiry_date: null, file_name: "insurance.pdf", download_url: "/api/v1/vehicles/LILYGO-001/documents/3/file/", uploaded_by: 2, uploaded_by_name: "Fleet Manager", created_at: "2026-08-12T01:00:00Z", updated_at: "2026-08-12T01:00:00Z" };
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => { const url = String(input); if (url.includes("/documents/") && init?.method === "POST") { submitted = init.body as FormData; return response(document, 201); } if (url.includes("/documents/")) return response({ count: submitted ? 1 : 0, previous: null, next: null, results: submitted ? [document] : [] }); return response({ count: 1, next: null, previous: null, results: [vehicle] }); });
    renderAt("/vehicles"); await screen.findByText("Sprint 1 Demo Vehicle"); fireEvent.click(screen.getByRole("button", { name: "More actions for Sprint 1 Demo Vehicle" })); fireEvent.click(screen.getByRole("menuitem", { name: "Upload document" })); await screen.findByText("No vehicle documents recorded."); fireEvent.click(screen.getByText("+ Upload Document"));
    fireEvent.change(screen.getByLabelText("Document Type"), { target: { value: "INSURANCE" } }); fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Insurance" } }); fireEvent.change(screen.getByLabelText("File"), { target: { files: [new File(["pdf"], "insurance.pdf", { type: "application/pdf" })] } }); fireEvent.submit(screen.getByLabelText("Title").closest("form")!);
    await waitFor(() => expect(screen.queryByLabelText("Title")).not.toBeInTheDocument()); expect(submitted).not.toBeNull(); expect(submitted!.has("uploaded_by")).toBe(false);
  });
  test("fleet manager creates an inspection once and the authenticated inspector is not submitted", async () => {
    auth.user.role = "FLEET_MANAGER"; auth.user.capabilities.push("INSPECTIONS.CREATE"); const pending = deferred<Response>(); let submitted = ""; let posts = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => { const url = String(input); if (url.includes("/inspections/") && init?.method === "POST") { posts += 1; submitted = String(init.body); return pending.promise; } if (url.includes("/inspections/")) return response({ count: 0, previous: null, next: null, results: [] }); return response({ count: 1, next: null, previous: null, results: [vehicle] }); });
    renderAt("/vehicles"); await screen.findByText("Sprint 1 Demo Vehicle"); fireEvent.click(screen.getByRole("button", { name: "More actions for Sprint 1 Demo Vehicle" })); fireEvent.click(screen.getByRole("menuitem", { name: "Add inspection" }));
    fireEvent.change(screen.getByLabelText("Inspection Date"), { target: { value: "2026-08-12" } }); fireEvent.change(screen.getByLabelText("Inspection Type"), { target: { value: "PRE_TRIP" } }); fireEvent.change(screen.getByLabelText("Result"), { target: { value: "NEEDS_ATTENTION" } });
    const save = screen.getByRole("button", { name: "Save Inspection" }); fireEvent.click(save); fireEvent.click(save); expect(posts).toBe(1); expect(submitted).not.toContain("inspected_by"); pending.resolve(await response(inspection));
    expect(await screen.findByText("Rear tire wear")).toBeInTheDocument(); expect(screen.getAllByText("Fleet Manager").length).toBeGreaterThan(0);
  });
  test("inspection creation reports API validation errors without closing the form", async () => {
    auth.user.role = "FLEET_MANAGER"; auth.user.capabilities.push("INSPECTIONS.CREATE"); vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => String(input).includes("/inspections/") && init?.method === "POST" ? response({ result: ["Invalid result."] }, 400) : String(input).includes("/inspections/") ? response({ count: 0, previous: null, next: null, results: [] }) : response({ count: 1, next: null, previous: null, results: [vehicle] }));
    renderAt("/vehicles"); await screen.findByText("Sprint 1 Demo Vehicle"); fireEvent.click(screen.getByRole("button", { name: "More actions for Sprint 1 Demo Vehicle" })); fireEvent.click(screen.getByRole("menuitem", { name: "Add inspection" })); fireEvent.change(screen.getByLabelText("Inspection Date"), { target: { value: "2026-08-12" } }); fireEvent.change(screen.getByLabelText("Inspection Type"), { target: { value: "PRE_TRIP" } }); fireEvent.change(screen.getByLabelText("Result"), { target: { value: "FAILED" } }); fireEvent.click(screen.getByRole("button", { name: "Save Inspection" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Please correct the inspection information."); expect(screen.getByLabelText("Inspection Date")).toHaveValue("2026-08-12");
  });
  test("detail preserves live pilot label and nullable rendering", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(input => String(input).includes("latest-status")
      ? response({ vehicle: { device_id: vehicle.device_id, plate_number: vehicle.plate_number, display_name: vehicle.display_name }, latest: null })
      : response(vehicle));
    renderAt("/vehicles/LILYGO-001");
    expect(await screen.findByRole("heading", { name: "Simulated Pilot Data" })).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
    expect(await screen.findByText("Waiting for the first telemetry event…")).toBeInTheDocument();
  });
  test("failed status change is accessible and preserves the previous state", async () => {
    auth.user.role = "FLEET_ADMIN";
    vi.spyOn(globalThis, "fetch").mockImplementation(input => {
      const url = String(input);
      if (url.includes("deactivate")) return response({ detail: "internal" }, 500);
      if (url.includes("latest-status")) return response({ vehicle: { device_id: vehicle.device_id, plate_number: vehicle.plate_number, display_name: vehicle.display_name }, latest: null });
      return response(vehicle);
    });
    renderAt("/vehicles/LILYGO-001");
    fireEvent.click(await screen.findByText("Deactivate"));
    const dialog = await screen.findByRole("dialog", { name: "Deactivate vehicle" });
    fireEvent.click(within(dialog).getByText("Deactivate"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to deactivate this vehicle.");
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Deactivate")).toBeInTheDocument();
  });
  test("successful status change updates state and rapid clicks mutate once", async () => {
    auth.user.role = "FLEET_ADMIN";
    const mutation = deferred<Response>();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("deactivate")) return mutation.promise;
      if (url.includes("latest-status")) return response({ vehicle: { device_id: vehicle.device_id, plate_number: vehicle.plate_number, display_name: vehicle.display_name }, latest: null });
      return response(vehicle);
    });
    renderAt("/vehicles/LILYGO-001");
    const button = await screen.findByText("Deactivate");
    fireEvent.click(button); fireEvent.click(button);
    const dialog = await screen.findByRole("dialog", { name: "Deactivate vehicle" });
    fireEvent.click(within(dialog).getByText("Deactivate"));
    await waitFor(() => expect(fetchMock.mock.calls.filter(([input]) => String(input).includes("deactivate"))).toHaveLength(1));
    mutation.resolve(await response({ ...vehicle, is_active: false }));
    expect(await screen.findByText("Reactivate")).toBeInTheDocument();
  });
  test("backend field errors render safely on corresponding form fields", async () => {
    auth.user.role = "FLEET_ADMIN";
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ plate_number: ["Already exists."] }, 400));
    renderAt("/vehicles/new");
    fireEvent.change(screen.getByLabelText("Device ID"), { target: { value: "TEST-001" } });
    fireEvent.change(screen.getByLabelText("Plate number"), { target: { value: "TEST-001" } });
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Test" } });
    fireEvent.click(screen.getByText("Save vehicle"));
    expect(await screen.findByText("Already exists.")).toHaveAttribute("id", "plate_number-error");
    expect(screen.queryByText(/traceback|exception|internal/i)).not.toBeInTheDocument();
  });
  test("successful create navigates once and rapid submits create once", async () => {
    auth.user.role = "FLEET_ADMIN";
    const mutation = deferred<Response>();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      if (init?.method === "POST") return mutation.promise;
      return response(vehicle);
    });
    const { history } = renderWithHistory("/vehicles/new");
    fireEvent.change(screen.getByLabelText("Device ID"), { target: { value: "TEST-001" } });
    fireEvent.change(screen.getByLabelText("Plate number"), { target: { value: "TEST-001" } });
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Test" } });
    const form = screen.getByText("Save vehicle").closest("form")!;
    fireEvent.submit(form); fireEvent.submit(form);
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
    mutation.resolve(await response({ ...vehicle, device_id: "TEST-001" }));
    await waitFor(() => expect(history.location.pathname).toBe("/vehicles/TEST-001"));
  });
  test("successful edit navigates once and rapid submits patch once", async () => {
    auth.user.role = "FLEET_MANAGER";
    const mutation = deferred<Response>();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) =>
      init?.method === "PATCH" ? mutation.promise : response(vehicle));
    const { history } = renderWithHistory("/vehicles/LILYGO-001/edit");
    const form = (await screen.findByText("Save vehicle")).closest("form")!;
    fireEvent.submit(form); fireEvent.submit(form);
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(1);
    mutation.resolve(await response({ ...vehicle, display_name: "Edited" }));
    await waitFor(() => expect(history.location.pathname).toBe("/vehicles/LILYGO-001"));
  });
  test("unmount aborts an unresolved detail request", () => {
    let signal: AbortSignal | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) => {
      signal = init?.signal ?? undefined;
      return new Promise(() => undefined);
    });
    const rendered = renderAt("/vehicles/LILYGO-001");
    rendered.unmount();
    expect(signal?.aborted).toBe(true);
  });
  test("unmount aborts an unresolved vehicle form mutation", () => {
    auth.user.role = "FLEET_ADMIN";
    let signal: AbortSignal | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) => {
      signal = init?.signal ?? undefined;
      return new Promise(() => undefined);
    });
    const rendered = renderAt("/vehicles/new");
    fireEvent.change(screen.getByLabelText("Device ID"), { target: { value: "TEST-001" } });
    fireEvent.change(screen.getByLabelText("Plate number"), { target: { value: "TEST-001" } });
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Test" } });
    fireEvent.submit(screen.getByText("Save vehicle").closest("form")!);
    rendered.unmount();
    expect(signal?.aborted).toBe(true);
  });
  test("unmount aborts an unresolved status mutation", async () => {
    auth.user.role = "FLEET_ADMIN";
    let mutationSignal: AbortSignal | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      if (String(input).includes("deactivate")) {
        mutationSignal = init?.signal ?? undefined;
        return new Promise(() => undefined);
      }
      if (String(input).includes("latest-status")) {
        return response({ vehicle: { device_id: vehicle.device_id, plate_number: vehicle.plate_number, display_name: vehicle.display_name }, latest: null });
      }
      return response(vehicle);
    });
    const rendered = renderAt("/vehicles/LILYGO-001");
    fireEvent.click(await screen.findByText("Deactivate"));
    const dialog = await screen.findByRole("dialog", { name: "Deactivate vehicle" });
    fireEvent.click(within(dialog).getByText("Deactivate"));
    await waitFor(() => expect(mutationSignal).toBeDefined());
    rendered.unmount();
    expect(mutationSignal?.aborted).toBe(true);
  });
  test("logout failure is handled without an unhandled rejection", async () => {
    auth.signOut.mockRejectedValueOnce(new Error("network"));
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ count: 0, next: null, previous: null, results: [] }));
    renderAt("/vehicles");
    fireEvent.click(screen.getByText("Sign out"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to sign out. Please try again.");
    expect(screen.getByRole("button", { name: "Sign out" })).toBeEnabled();
  });
  test("rapid logout clicks invoke sign-out once and expose busy state", async () => {
    const pending = deferred<void>(); auth.signOut.mockReturnValue(pending.promise);
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ count: 0, next: null, previous: null, results: [] }));
    renderAt("/vehicles");
    const button = screen.getByText("Sign out");
    fireEvent.click(button); fireEvent.click(button);
    expect(auth.signOut).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: /signing out/i })).toBeDisabled();
  });
  test("detail route changes reset loading and ignore the old late response", async () => {
    const requests: Array<{ url: string; request: ReturnType<typeof deferred<Response>> }> = [];
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("latest-status")) return response({ vehicle: { device_id: "B", plate_number: "B", display_name: "B" }, latest: null });
      const request = deferred<Response>(); requests.push({ url, request }); return request.promise;
    });
    const { history } = renderWithHistory("/vehicles/A");
    await waitFor(() => expect(requests.filter(item => item.url.endsWith("/A/"))).toHaveLength(2));
    act(() => history.push("/vehicles/B"));
    expect(screen.getByText("Loading vehicle…")).toBeInTheDocument();
    await waitFor(() => expect(requests.filter(item => item.url.endsWith("/B/"))).toHaveLength(2));
    const old = requests.filter(item => item.url.endsWith("/A/")).at(-1)!;
    const current = requests.filter(item => item.url.endsWith("/B/")).at(-1)!;
    current.request.resolve(await response({ ...vehicle, device_id: "B", display_name: "Vehicle B" }));
    expect(await screen.findByRole("heading", { name: "Vehicle B" })).toBeInTheDocument();
    old.request.resolve(await response({ ...vehicle, device_id: "A", display_name: "Stale A" }));
    await waitFor(() => expect(screen.queryByText("Stale A")).not.toBeInTheDocument());
  });
  test("edit route changes replace uncontrolled values with the new vehicle", async () => {
    auth.user.role = "FLEET_MANAGER";
    const next: Array<ReturnType<typeof deferred<Response>>> = [];
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      if (String(input).includes("/B/")) {
        const request = deferred<Response>(); next.push(request); return request.promise;
      }
      return response({ ...vehicle, device_id: "A", plate_number: "A-PLATE", display_name: "Vehicle A" });
    });
    const { history } = renderWithHistory("/vehicles/A/edit");
    expect(await screen.findByDisplayValue("A-PLATE")).toBeInTheDocument();
    act(() => history.push("/vehicles/B/edit"));
    expect(screen.getByText("Loading vehicle…")).toBeInTheDocument();
    await waitFor(() => expect(next).toHaveLength(2));
    for (const request of next) {
      request.resolve(await response({ ...vehicle, device_id: "B", plate_number: "B-PLATE", display_name: "Vehicle B" }));
    }
    expect(await screen.findByDisplayValue("B-PLATE")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("A-PLATE")).not.toBeInTheDocument();
  });
  test("status errors clear when navigating to another vehicle", async () => {
    auth.user.role = "FLEET_ADMIN";
    const next: Array<ReturnType<typeof deferred<Response>>> = [];
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("deactivate")) return response({}, 500);
      if (url.includes("latest-status")) return response({ vehicle: { device_id: "B", plate_number: "B", display_name: "B" }, latest: null });
      if (url.includes("/B/")) {
        const request = deferred<Response>(); next.push(request); return request.promise;
      }
      return response({ ...vehicle, device_id: "A", display_name: "Vehicle A" });
    });
    const { history } = renderWithHistory("/vehicles/A");
    fireEvent.click(await screen.findByText("Deactivate"));
    const dialog = await screen.findByRole("dialog", { name: "Deactivate vehicle" });
    fireEvent.click(within(dialog).getByText("Deactivate"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to deactivate this vehicle.");
    act(() => history.push("/vehicles/B"));
    expect(screen.getByText("Loading vehicle…")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await waitFor(() => expect(next).toHaveLength(2));
    for (const request of next) {
      request.resolve(await response({ ...vehicle, device_id: "B", display_name: "Vehicle B" }));
    }
    expect(await screen.findByRole("heading", { name: "Vehicle B" })).toBeInTheDocument();
  });
});
