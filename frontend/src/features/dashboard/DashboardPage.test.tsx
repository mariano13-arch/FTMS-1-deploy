import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import DashboardPage from "./DashboardPage";

const mocks = vi.hoisted(() => ({ getSummary: vi.fn() }));
vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, getDashboardSummary: mocks.getSummary };
});

const widget = (values: Array<[string, string, number]>, extra = {}) => ({
  scope: "Current",
  classification: "Operational",
  provenance: "Persisted source",
  description: "Factual operational values.",
  module_url: "/transport-requests",
  total: values.reduce((sum, item) => sum + item[2], 0),
  values: values.map(([value, label, count]) => ({ value, label, count })),
  ...extra,
});

const response = {
  generated_at: "2026-09-24T00:00:00Z",
  request_status: widget([["READY_FOR_DISPATCH", "Ready for dispatch", 4]]),
  dispatch_queue: widget([["AWAITING", "Awaiting assignment", 2]], { module_url: "/dispatch-board" }),
  trip_status: widget([["IN_TRANSIT", "In transit", 1]]),
  completed_trips: widget([["2026-09-24", "Sep 24", 0]], { scope: "Last 7 days" }),
  fleet_state: widget([["ACTIVE", "Active", 8]], { module_url: "/vehicles" }),
  driver_state: widget([["ACTIVE", "Active", 6]], { module_url: "/drivers" }),
  inspection_results: widget([["PASSED", "Passed", 0]], { scope: "Today" }),
  maintenance_activity: widget([["OPEN", "Open", 1]], { module_url: "/maintenance" }),
  safety_events: widget([["HARSH_BRAKING", "Harsh braking", 0]], { scope: "Today", module_url: "/alerts" }),
  geofence_activity: widget([["ENTER", "Entries", 0]], { scope: "Today", module_url: "/live-map" }),
  device_telemetry: widget([["GENUINE_RECENT", "Genuine recent telemetry", 3]], { module_url: "/devices" }),
  fuel_evidence: widget([["CURRENT_AI", "Current AI", 1], ["FLEET_REFERENCE_BASELINE", "Fleet reference baseline", 2]], { classification: "Predicted / Reference", module_url: "/fuel-analytics" }),
  sos_activity: widget([["ACTIVE", "Active SOS", 0]], { module_url: "/alerts" }),
};

describe("DashboardPage", () => {
  beforeEach(() => mocks.getSummary.mockReset().mockResolvedValue(response));

  test("renders twelve factual chart cards and no unsupported metrics", async () => {
    const { container } = render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    expect(await screen.findByText("Transport Request Status")).toBeInTheDocument();
    expect(container.querySelectorAll(".dashboard-chart-card")).toHaveLength(12);
    expect(container.querySelector(".dashboard-chart-grid")).toBeInTheDocument();
    expect(screen.getByText("Current AI")).toBeInTheDocument();
    expect(screen.getAllByText("0").length).toBeGreaterThan(0);
    expect(screen.queryByText(/Fleet Utilization|System Health|Actual Fuel Used|Actual Fuel Cost/)).not.toBeInTheDocument();
    expect(screen.queryByText("Planned module")).not.toBeInTheDocument();
    expect(screen.getByText("No completed trips in the last 7 days")).toBeInTheDocument();
    expect(screen.getByText("No operational safety events today")).toBeInTheDocument();
    expect(screen.getByText("No geofence activity today")).toBeInTheDocument();
    expect(screen.getByText("No inspections recorded today")).toBeInTheDocument();
    expect(container.querySelector(".dashboard-chart-grid")).toHaveClass("dashboard-chart-grid");
  });

  test("renders normal charts for non-zero data and a real trend instead of an empty state", async () => {
    mocks.getSummary.mockResolvedValueOnce({
      ...response,
      completed_trips: widget([
        ["2026-09-23", "Sep 23", 1],
        ["2026-09-24", "Sep 24", 3],
      ], { scope: "Last 7 days" }),
      safety_events: widget([["HARSH_BRAKING", "Harsh braking", 2]], { scope: "Today" }),
      geofence_activity: widget([["ENTER", "Entries", 4]], { scope: "Today" }),
      inspection_results: widget([["PASSED", "Passed", 5]], { scope: "Today" }),
    });
    const { container } = render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    await screen.findByText("Transport Request Status");
    expect(container.querySelector(".dashboard-line svg")).toBeInTheDocument();
    expect(container.querySelectorAll(".dashboard-hbars i").length).toBeGreaterThan(0);
    expect(container.querySelectorAll(".dashboard-donut").length).toBeGreaterThan(0);
    expect(screen.queryByText("No completed trips in the last 7 days")).not.toBeInTheDocument();
  });

  test("empty chart cards remain clickable and open their factual drawer", async () => {
    render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Completed Trips/ }));
    expect(screen.getByLabelText("Completed Trips details")).toBeInTheDocument();
    expect(screen.getByText("No completed trips in the last 7 days")).toBeInTheDocument();
  });

  test("push drawer updates, links, closes with button and Escape", async () => {
    const { container } = render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Transport Request Status/ }));
    expect(container.querySelector(".dashboard-page.drawer-open")).toBeInTheDocument();
    const workspace = container.querySelector(".dashboard-workspace");
    expect(workspace?.firstElementChild).toHaveClass("dashboard-main");
    expect(workspace?.lastElementChild).toHaveClass("dashboard-detail");
    expect(screen.getByLabelText("Transport Request Status details")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open full module/ })).toHaveAttribute("href", "/transport-requests");
    fireEvent.click(screen.getByRole("button", { name: /Dispatch Queue/ }));
    expect(screen.queryByLabelText("Transport Request Status details")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Dispatch Queue details")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByLabelText("Dispatch Queue details")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Fleet State/ }));
    fireEvent.click(screen.getByRole("button", { name: "Close dashboard details" }));
    expect(container.querySelector(".dashboard-page.drawer-open")).not.toBeInTheDocument();
  });

  test("shows SOS strip only for factual active SOS", async () => {
    const rendered = render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    await screen.findByText("Transport Request Status");
    expect(screen.queryByText(/Active SOS:/)).not.toBeInTheDocument();
    rendered.unmount();
    mocks.getSummary.mockResolvedValueOnce({ ...response, sos_activity: widget([["ACTIVE", "Active SOS", 2]], { module_url: "/alerts" }) });
    render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Active SOS: 2/ }));
    expect(screen.getByLabelText("Active SOS details")).toBeInTheDocument();
  });

  test("renders initial loading, endpoint error, and retry", async () => {
    mocks.getSummary.mockReturnValueOnce(new Promise(() => undefined));
    const first = render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    expect(screen.getByLabelText("Loading dashboard")).toBeInTheDocument();
    first.unmount();
    mocks.getSummary.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(response);
    render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Transport Request Status")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Refresh/ })).not.toBeInTheDocument();
    expect(mocks.getSummary).toHaveBeenCalledTimes(3);
  });

  test("automatically re-fetches every thirty seconds and preserves stale data on failure", async () => {
    let intervalCallback: (() => void) | undefined;
    let dashboardInterval: number | undefined;
    const realSetInterval = window.setInterval;
    const setIntervalMock = vi.fn((callback: TimerHandler, delay?: number, ...args: unknown[]) => {
      if (delay === 30_000) {
        intervalCallback = callback as () => void;
        dashboardInterval = delay;
        return realSetInterval(() => undefined, delay, ...args);
      }
      return realSetInterval(callback, delay, ...args);
    });
    window.setInterval = setIntervalMock as unknown as typeof window.setInterval;
    mocks.getSummary
      .mockResolvedValueOnce(response)
      .mockResolvedValueOnce({
        ...response,
        generated_at: "2026-09-24T00:00:30Z",
        request_status: widget([["READY_FOR_DISPATCH", "Ready for dispatch", 7]]),
      })
      .mockRejectedValueOnce(new Error("offline"));
    render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    expect(await screen.findByText("Transport Request Status")).toBeInTheDocument();
    expect(dashboardInterval).toBe(30_000);
    intervalCallback?.();
    await waitFor(() => expect(screen.getAllByText("7").length).toBeGreaterThan(0));
    intervalCallback?.();
    await waitFor(() => expect(mocks.getSummary).toHaveBeenCalledTimes(3));
    expect(screen.getAllByText("7").length).toBeGreaterThan(0);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    window.setInterval = realSetInterval;
  });
});
