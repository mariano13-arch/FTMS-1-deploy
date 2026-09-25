import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "../../App";
import DevicesPage from "./DevicesPage";

const mocks = vi.hoisted(() => ({
  getDevices: vi.fn(),
  getDevice: vi.fn(),
  pairDevice: vi.fn(),
  unpairDevice: vi.fn(),
  getVehicles: vi.fn(),
}));
const auth = vi.hoisted(() => ({
  capabilities: ["DASHBOARD.VIEW", "DEVICES.VIEW", "DEVICES.PAIR", "DEVICES.REPLACE", "DEVICES.UNPAIR"],
}));

vi.mock("./api", () => ({
  getDevices: mocks.getDevices,
  getDevice: mocks.getDevice,
  pairDevice: mocks.pairDevice,
  unpairDevice: mocks.unpairDevice,
}));
vi.mock("../../services/vehicles", () => ({ getVehicles: mocks.getVehicles }));
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: 1, username: "manager", display_name: "Fleet Manager", role: "FLEET_MANAGER", capabilities: auth.capabilities },
    loading: false,
    signOut: vi.fn(),
  }),
}));
vi.mock("../../services/sidebarService", () => ({ fetchSidebarCounts: async () => ({}) }));

const unpaired = {
  device_id: "QR-NEW-001",
  registration_status: "REGISTERED" as const,
  created_at: "2026-09-21T01:00:00Z",
  is_paired: false,
  current_vehicle: null,
  current_binding: null,
  latest_telemetry: null,
};
const paired = {
  ...unpaired,
  device_id: "LILYGO-002",
  is_paired: true,
  current_vehicle: {
    vehicle_id: 7,
    plate_number: "DEMO-001",
    display_name: "Sprint 1 Demo Vehicle",
    compatibility_device_id: "LILYGO-001",
  },
  current_binding: { id: 9, paired_at: "2026-09-20T01:00:00Z", paired_by: "Fleet Manager" },
  latest_telemetry: {
    recorded_at: new Date().toISOString(),
    position_source: "GNSS" as const,
    obd_source: "PHYSICAL_OBD" as const,
    latitude: 14.5,
    longitude: 121,
  },
};

const page = (canManage = true) => ({
  count: 16,
  next: null,
  previous: null,
  results: [unpaired, paired],
  summary: { total_registered: 16, paired: 5, unpaired: 11, recently_seen: 4 },
  can_manage: canManage,
});

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getDevices.mockResolvedValue(page());
  mocks.getVehicles.mockResolvedValue({ count: 1, next: null, previous: null, results: [{ id: 7, display_name: "Sprint 1 Demo Vehicle", plate_number: "DEMO-001" }] });
  mocks.pairDevice.mockResolvedValue(unpaired);
  mocks.unpairDevice.mockResolvedValue(unpaired);
  vi.spyOn(window, "confirm").mockReturnValue(true);
  auth.capabilities = ["DASHBOARD.VIEW", "DEVICES.VIEW", "DEVICES.PAIR", "DEVICES.REPLACE", "DEVICES.UNPAIR"];
});

describe("Devices registry", () => {
  test("renders from the implemented Devices route", async () => {
    render(<MemoryRouter initialEntries={["/devices"]}><App /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Devices" })).toBeInTheDocument();
  });

  test("renders API KPIs and honest paired, unpaired, and telemetry states", async () => {
    render(<DevicesPage />);

    expect(await screen.findByRole("heading", { name: "Devices" })).toBeInTheDocument();
    const summary = screen.getByLabelText("Device registry summary");
    expect(within(summary).getByText("16")).toBeInTheDocument();
    expect(screen.getByText("QR-NEW-001")).toBeInTheDocument();
    expect(screen.getByText("Sprint 1 Demo Vehicle · DEMO-001")).toBeInTheDocument();
    expect(screen.getByText("No telemetry received")).toBeInTheDocument();
    expect(screen.getByText("Recently seen")).toBeInTheDocument();
  });

  test("sends search and filter through the registry query without pagination controls", async () => {
    render(<DevicesPage />);
    await screen.findByText("QR-NEW-001");

    fireEvent.change(screen.getByLabelText("Search devices"), { target: { value: "LILYGO" } });
    fireEvent.click(screen.getByRole("button", { name: "Paired" }));

    await waitFor(() => expect(mocks.getDevices).toHaveBeenLastCalledWith(
      expect.stringContaining("page_size=100"),
      expect.any(AbortSignal),
    ));
    expect(mocks.getDevices.mock.calls.at(-1)?.[0]).toContain("search=LILYGO");
    expect(mocks.getDevices.mock.calls.at(-1)?.[0]).toContain("binding=paired");
    expect(screen.queryByRole("button", { name: "Previous" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Next" })).not.toBeInTheDocument();
  });

  test("automatically appends backend pages into the scrollable list", async () => {
    mocks.getDevices
      .mockResolvedValueOnce({ ...page(), next: "http://localhost/api/v1/telemetry-devices/?page=2&page_size=100", results: [unpaired] })
      .mockResolvedValueOnce({ ...page(), previous: "http://localhost/api/v1/telemetry-devices/?page_size=100", results: [paired] });

    render(<DevicesPage />);

    expect(await screen.findByText("QR-NEW-001")).toBeInTheDocument();
    expect(await screen.findByText("LILYGO-002")).toBeInTheDocument();
    expect(mocks.getDevices).toHaveBeenNthCalledWith(
      2,
      "page=2&page_size=100",
      expect.any(AbortSignal),
    );
  });

  test("opens history and preserves confirmations for pair and unpair", async () => {
    mocks.getDevice
      .mockResolvedValueOnce({ ...unpaired, can_manage: true, binding_history: [{ id: 3, vehicle_id: 2, vehicle_name: "Previous Van", plate_number: "OLD-001", paired_at: "2026-01-01T00:00:00Z", unpaired_at: "2026-02-01T00:00:00Z", paired_by: "Manager", unpaired_by: "Manager" }] })
      .mockResolvedValue({ ...paired, can_manage: true, binding_history: [] });
    render(<DevicesPage />);
    const rows = await screen.findAllByRole("row");
    fireEvent.click(within(rows[1]).getByRole("button", { name: "View" }));

    expect(await screen.findByText("Previous Van · OLD-001")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Vehicle for device pairing"), { target: { value: "7" } });
    fireEvent.click(screen.getByRole("button", { name: "Pair to Vehicle" }));
    await waitFor(() => expect(mocks.pairDevice).toHaveBeenCalledWith("QR-NEW-001", 7, false));
    fireEvent.click(await screen.findByRole("button", { name: "Unpair" }));
    await waitFor(() => expect(mocks.unpairDevice).toHaveBeenCalledWith("LILYGO-002"));
    expect(window.confirm).toHaveBeenCalled();
  });

  test("hides mutation actions for read-only users", async () => {
    auth.capabilities = ["DEVICES.VIEW"];
    mocks.getDevices.mockResolvedValue(page(false));
    mocks.getDevice.mockResolvedValue({ ...unpaired, can_manage: false, binding_history: [] });
    render(<DevicesPage />);
    const rows = await screen.findAllByRole("row");
    fireEvent.click(within(rows[1]).getByRole("button", { name: "View" }));

    expect(await screen.findByLabelText("QR-NEW-001 device details")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Actions" })).not.toBeInTheDocument();
    expect(mocks.getVehicles).not.toHaveBeenCalled();
  });
});
