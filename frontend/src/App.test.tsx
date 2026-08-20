import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryHistory } from "history";
import { MemoryRouter, Router } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import type { Role } from "./services/auth";

const auth = vi.hoisted(() => ({
  user: { id: 1, username: "staff", display_name: "Staff User", role: "DISPATCHER" as Role },
  loading: false, signIn: vi.fn(), signOut: vi.fn(), expire: vi.fn(),
}));
vi.mock("./AuthContext", () => ({ useAuth: () => auth }));
vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="map">{children}</div>,
  TileLayer: () => <span>© OpenStreetMap contributors</span>,
  CircleMarker: ({ center }: { center: [number, number] }) => <span data-testid="marker">{center.join(",")}</span>,
  useMap: () => ({ setView: vi.fn() }),
}));

const vehicle = {
  device_id: "LILYGO-001", plate_number: "DEMO-001", display_name: "Sprint 1 Demo Vehicle",
  vehicle_type: "OTHER", manufacturer: "", model: "", model_year: null,
  passenger_capacity: null, is_active: true,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
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

beforeEach(() => {
  auth.user = { id: 1, username: "staff", display_name: "Staff User", role: "DISPATCHER" };
  auth.loading = false; auth.signIn.mockReset(); auth.signOut.mockReset();
  vi.stubGlobal("WebSocket", FakeWebSocket);
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

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
  test("successful login follows a safe internal redirect under StrictMode", async () => {
    auth.user = null as unknown as typeof auth.user;
    auth.signIn.mockImplementationOnce(async () => { auth.user = { id: 1, username: "staff", display_name: "Staff User", role: "DISPATCHER" }; });
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response(vehicle));
    const { history } = renderWithHistory("/login", { from: "/vehicles/LILYGO-001" });
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "staff" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret" } });
    fireEvent.submit(screen.getByRole("button", { name: "Sign in" }).closest("form")!);
    await waitFor(() => expect(history.location.pathname).toBe("/vehicles/LILYGO-001"));
  });
  test("rapid login submissions invoke sign-in once", async () => {
    auth.user = null as unknown as typeof auth.user;
    const pending = deferred<void>(); auth.signIn.mockReturnValue(pending.promise);
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
    expect(await screen.findByText("Sprint 1 Demo Vehicle")).toBeInTheDocument();
    expect(screen.queryByText("Create vehicle")).not.toBeInTheDocument();
    expect(screen.queryByText("Edit")).not.toBeInTheDocument();
  });
  test("fleet manager can edit but cannot create or change status", async () => {
    auth.user.role = "FLEET_MANAGER";
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response(vehicle));
    renderAt("/vehicles/LILYGO-001");
    expect(await screen.findByText("Edit")).toBeInTheDocument();
    expect(screen.queryByText("Deactivate")).not.toBeInTheDocument();
  });
  test("super admin receives create and status controls", async () => {
    auth.user.role = "SUPER_ADMIN";
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ count: 0, next: null, previous: null, results: [] }));
    renderAt("/vehicles");
    expect(await screen.findByRole("button", { name: "+ Add Vehicle" })).toBeInTheDocument();
    expect(screen.getByText("No vehicles match these filters.")).toBeInTheDocument();
  });
  test("list exposes loading, filtering, and error states", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ count: 0, next: null, previous: null, results: [] }));
    renderAt("/vehicles"); expect(screen.getByText("Loading vehicles…")).toBeInTheDocument();
    await screen.findByText("No vehicles match these filters.");
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply Filters" }));
    await waitFor(() => expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain("search=demo"));
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
    auth.user.role = "SUPER_ADMIN";
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(globalThis, "fetch").mockImplementation(input => {
      const url = String(input);
      if (url.includes("deactivate")) return response({ detail: "internal" }, 500);
      if (url.includes("latest-status")) return response({ vehicle: { device_id: vehicle.device_id, plate_number: vehicle.plate_number, display_name: vehicle.display_name }, latest: null });
      return response(vehicle);
    });
    renderAt("/vehicles/LILYGO-001");
    fireEvent.click(await screen.findByText("Deactivate"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to deactivate this vehicle.");
    expect(screen.getByText("true")).toBeInTheDocument();
    expect(screen.getByText("Deactivate")).toBeInTheDocument();
  });
  test("successful status change updates state and rapid clicks mutate once", async () => {
    auth.user.role = "SUPER_ADMIN";
    vi.spyOn(window, "confirm").mockReturnValue(true);
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
    expect(fetchMock.mock.calls.filter(([input]) => String(input).includes("deactivate"))).toHaveLength(1);
    mutation.resolve(await response({ ...vehicle, is_active: false }));
    expect(await screen.findByText("Reactivate")).toBeInTheDocument();
    expect(screen.getByText("false")).toBeInTheDocument();
  });
  test("backend field errors render safely on corresponding form fields", async () => {
    auth.user.role = "SUPER_ADMIN";
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
    auth.user.role = "SUPER_ADMIN";
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
    auth.user.role = "SUPER_ADMIN";
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
    auth.user.role = "SUPER_ADMIN";
    vi.spyOn(window, "confirm").mockReturnValue(true);
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
    rendered.unmount();
    expect(mutationSignal?.aborted).toBe(true);
  });
  test("logout failure is handled without an unhandled rejection", async () => {
    auth.signOut.mockRejectedValueOnce(new Error("network"));
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ count: 0, next: null, previous: null, results: [] }));
    renderAt("/vehicles");
    fireEvent.click(screen.getByText("Sign out"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to sign out. Please try again.");
  });
  test("rapid logout clicks invoke sign-out once and expose busy state", async () => {
    const pending = deferred<void>(); auth.signOut.mockReturnValue(pending.promise);
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ count: 0, next: null, previous: null, results: [] }));
    renderAt("/vehicles");
    const button = screen.getByText("Sign out");
    fireEvent.click(button); fireEvent.click(button);
    expect(auth.signOut).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Signing out…")).toBeDisabled();
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
    auth.user.role = "SUPER_ADMIN";
    vi.spyOn(window, "confirm").mockReturnValue(true);
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
