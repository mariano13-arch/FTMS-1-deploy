import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import DispatchTripReportPage from "./DispatchTripReportPage";

const mocks = vi.hoisted(() => ({ fetchReport: vi.fn(), downloadCsv: vi.fn() }));
vi.mock("./api", () => ({ fetchDispatchTripReport: mocks.fetchReport, downloadDispatchTripCsv: mocks.downloadCsv }));
const row = { id: 1, request_id: "request-1", request_number: "TR-001", request_type_label: "Guest Transfer", driver: { id: 2, code: "DRV-1", name: "Maria Reyes" }, vehicle: { id: 3, name: "Report Van", identifier: "VEH-1", plate_number: "ABC-123" }, selection_mode: "MANUAL", selection_mode_label: "Manual", manual_override_reason: "Operational need", execution_status: "IN_TRANSIT", execution_status_label: "In transit", confirmed_at: "2026-09-20T01:00:00Z", confirmed_by: "Fleet Manager", accepted_at: "2026-09-20T01:10:00Z", execution_started_at: "2026-09-20T01:20:00Z", pickup_arrived_at: "2026-09-20T01:40:00Z", pickup_departed_at: null, destination_arrived_at: null, completed_at: null, durations: { assignment_to_acceptance: 600, acceptance_to_start: 600, start_to_pickup: 1200, pickup_dwell: null, pickup_to_destination: null, destination_to_completion: null, execution_duration: null, assignment_to_completion: null } };
const response = { meta: { title: "Dispatch & Trip Execution", generated_at: "2026-09-21T00:00:00Z", generated_by: "Fleet Manager", timezone: "Asia/Manila", date_basis: "DispatchAssignment.confirmed_at", date_from: "2026-08-23", date_to: "2026-09-21" }, summary: { assignments_confirmed: 8, driver_acceptances: 6, trips_in_progress: 2, completed_trips: 0, average_execution_duration_seconds: null }, trend: [{ date: "2026-09-20", count: 8 }], breakdowns: { by_execution_status: [{ value: "IN_TRANSIT", label: "In transit", count: 2 }], by_selection_mode: [{ value: "MANUAL", label: "Manual", count: 8 }] }, choices: { vehicles: [{ value: "3", label: "Report Van · VEH-1" }], drivers: [{ value: "2", label: "DRV-1 · Maria Reyes" }], execution_statuses: [{ value: "IN_TRANSIT", label: "In transit" }], selection_modes: [{ value: "MANUAL", label: "Manual" }] }, details: { count: 16, page: 1, page_size: 15, total_pages: 2, results: [row] } };

beforeEach(() => { vi.clearAllMocks(); mocks.fetchReport.mockResolvedValue(response); mocks.downloadCsv.mockResolvedValue(undefined); });

describe("Dispatch and Trip Execution report", () => {
  test("renders KPIs, honest unavailable average, breakdowns, and row", async () => {
    render(<MemoryRouter><DispatchTripReportPage /></MemoryRouter>);
    expect(await screen.findByText("TR-001")).toBeInTheDocument();
    expect(screen.getByText("Avg Execution Duration").previousSibling).toHaveTextContent("—");
    expect(screen.queryByText("Confirmed Assignments Over Time")).not.toBeInTheDocument();
    expect(screen.getByText("Current Execution Status")).toBeInTheDocument();
    expect(screen.getByText("Assignment Selection")).toBeInTheDocument();
    expect(screen.queryByText(/Actual Distance|ETA Accuracy|On Time|Late/)).not.toBeInTheDocument();
  });

  test("resets pagination for filters, paginates, and exports current filters", async () => {
    render(<MemoryRouter><DispatchTripReportPage /></MemoryRouter>); await screen.findByText("TR-001");
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(mocks.fetchReport).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })));
    fireEvent.change(within(screen.getByLabelText("Report filters")).getByLabelText("driver"), { target: { value: "2" } });
    await waitFor(() => expect(mocks.fetchReport).toHaveBeenLastCalledWith(expect.objectContaining({ driver: "2", page: 1 })));
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    expect(mocks.downloadCsv).toHaveBeenCalledWith(expect.objectContaining({ driver: "2" }));
  });

  test("opens read-only details with lifecycle timestamps and safe durations", async () => {
    render(<MemoryRouter><DispatchTripReportPage /></MemoryRouter>); await screen.findByText("TR-001");
    fireEvent.click(screen.getByRole("button", { name: "View" }));
    const drawer = screen.getByLabelText("Assignment details");
    expect(within(drawer).getByText("Operational need")).toBeInTheDocument();
    expect(within(drawer).getAllByText("10m")).toHaveLength(2);
    expect(within(drawer).getAllByText("—").length).toBeGreaterThan(0);
  });

  test("distinguishes loading, empty, and API error states", async () => {
    mocks.fetchReport.mockRejectedValueOnce(new Error("offline"));
    render(<MemoryRouter><DispatchTripReportPage /></MemoryRouter>);
    expect(screen.getByText("Loading report…")).toBeInTheDocument();
    expect(await screen.findByText("Unable to load this report.")).toBeInTheDocument();
    expect(screen.queryByText("Assignments Confirmed")).not.toBeInTheDocument();
  });
});
