import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import MaintenancePage from "./MaintenancePage";

const mocks = vi.hoisted(() => ({
  getVehicles: vi.fn(), getMaintenanceRecords: vi.fn(),
  createMaintenanceRecord: vi.fn(), transitionMaintenanceRecord: vi.fn(),
}));
vi.mock("../../services/vehicles", () => ({ getVehicles: mocks.getVehicles }));
vi.mock("./api", () => ({
  getMaintenanceRecords: mocks.getMaintenanceRecords,
  createMaintenanceRecord: mocks.createMaintenanceRecord,
  transitionMaintenanceRecord: mocks.transitionMaintenanceRecord,
}));

const vehicles = { count: 1, next: null, previous: null, results: [{ device_id: "FTMS-001", display_name: "Service Van", plate_number: "ABC-123", is_active: true, latest_inspection: { id: 7, inspection_date: "2026-09-05", inspection_type: "PERIODIC", result: "PASSED" } }] };
const record = { id: 3, vehicle: { id: 1, device_id: "FTMS-001", display_name: "Service Van", plate_number: "ABC-123" }, inspection: null, source: "MANUAL", status: "OPEN", title: "Cooling system review", notes: "Check hose", scheduled_at: null, started_at: null, completed_at: null, created_by: 1, created_by_name: "Fleet Manager", allowed_transitions: ["SCHEDULED", "IN_PROGRESS", "CANCELLED"], created_at: "2026-09-05T08:00:00Z", updated_at: "2026-09-05T08:00:00Z" };
const records = { count: 1, next: null, previous: null, can_manage: true, results: [record] };

beforeEach(() => {
  Object.values(mocks).forEach(mock => mock.mockReset());
  mocks.getVehicles.mockResolvedValue(vehicles);
  mocks.getMaintenanceRecords.mockResolvedValue(records);
  mocks.createMaintenanceRecord.mockResolvedValue(record);
  mocks.transitionMaintenanceRecord.mockResolvedValue({ ...record, status: "IN_PROGRESS" });
});

test("renders real maintenance records and valid lifecycle actions", async () => {
  render(<MaintenancePage />);
  expect(await screen.findByText("Service Van")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Maintenance Review" }));
  expect(screen.getByText("Cooling system review")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "IN PROGRESS" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "COMPLETED" })).not.toBeInTheDocument();
});

test("creates an authoritative open maintenance record", async () => {
  render(<MaintenancePage />);
  await screen.findByText("Service Van");
  fireEvent.click(screen.getByRole("tab", { name: "Maintenance Review" }));
  fireEvent.change(screen.getByLabelText("Summary"), { target: { value: "Inspect brakes" } });
  fireEvent.click(screen.getByRole("button", { name: "Create Open Record" }));
  await waitFor(() => expect(mocks.createMaintenanceRecord).toHaveBeenCalledWith(expect.objectContaining({ vehicle_device_id: "FTMS-001", title: "Inspect brakes" })));
});

test("does not update locally when a lifecycle API call fails", async () => {
  mocks.transitionMaintenanceRecord.mockRejectedValueOnce(new Error("offline"));
  render(<MaintenancePage />);
  await screen.findByText("Service Van");
  fireEvent.click(screen.getByRole("tab", { name: "Maintenance Review" }));
  fireEvent.click(screen.getByRole("button", { name: "IN PROGRESS" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("could not be updated");
  expect(screen.getByText("OPEN")).toBeInTheDocument();
});

test("hides management controls for read-only staff", async () => {
  mocks.getMaintenanceRecords.mockResolvedValueOnce({ ...records, can_manage: false });
  render(<MaintenancePage />);
  await screen.findByText("Service Van");
  fireEvent.click(screen.getByRole("tab", { name: "Maintenance Review" }));
  expect(screen.queryByText("Create Maintenance Record")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "IN PROGRESS" })).not.toBeInTheDocument();
});
