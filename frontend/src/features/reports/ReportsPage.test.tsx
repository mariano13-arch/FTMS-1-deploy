import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import ReportsPage from "./ReportsPage";
import TransportRequestReportPage from "./TransportRequestReportPage";

const mocks = vi.hoisted(() => ({
  fetchReport: vi.fn(),
  downloadCsv: vi.fn(),
  downloadPdf: vi.fn(),
  downloadXlsx: vi.fn(),
}));
vi.mock("./api", () => ({
  fetchTransportReport: mocks.fetchReport,
  downloadTransportReportCsv: mocks.downloadCsv,
  downloadTransportReportPdf: mocks.downloadPdf,
  downloadTransportReportXlsx: mocks.downloadXlsx,
}));

const response = {
  meta: { title: "Transport Request Summary", generated_at: "2026-09-21T04:00:00Z", generated_by: "Fleet Manager", timezone: "Asia/Manila", date_basis: "TransportRequest.created_at", date_from: "2026-08-23", date_to: "2026-09-21" },
  summary: { requests_created: 12, approved: 4, rejected: 2, cancelled: 1, currently_dispatch_ready: 3 },
  trend: [{ date: "2026-09-20", count: 5 }, { date: "2026-09-21", count: 7 }],
  breakdowns: { by_source: [{ value: "HMS", label: "Hotel Management System", count: 12 }], by_status: [{ value: "APPROVED", label: "Approved", count: 12 }] },
  choices: { sources: [{ value: "HMS", label: "Hotel Management System" }], request_types: [{ value: "GUEST_TRANSFER", label: "Guest Transfer" }], statuses: [{ value: "APPROVED", label: "Approved" }], priorities: [{ value: "HIGH", label: "High" }] },
  details: { count: 16, page: 1, page_size: 15, total_pages: 2, results: [{ id: "request-id", request_number: "TR-001", source_label: "Hotel Management System", request_type_label: "Guest Transfer", request_category_label: "Passenger Transport", priority_label: "High", status_label: "Approved", scheduled_pickup_at: "2026-09-21T06:00:00Z", created_at: "2026-09-20T06:00:00Z" }] },
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.fetchReport.mockResolvedValue(response);
  mocks.downloadCsv.mockResolvedValue(undefined);
  mocks.downloadPdf.mockResolvedValue(undefined);
  mocks.downloadXlsx.mockResolvedValue(undefined);
});

describe("Reports", () => {
  test("shows all seven current report categories enabled", () => {
    render(<MemoryRouter><ReportsPage /></MemoryRouter>);
    expect(screen.getAllByRole("article")).toHaveLength(7);
    expect(screen.getAllByRole("link", { name: "Open report" })).toHaveLength(7);
    expect(screen.getByText("Fuel Predictions & Reference Data")).toBeInTheDocument();
    expect(screen.queryByText("Coming later")).not.toBeInTheDocument();
  });

  test("renders truthful summary, breakdowns, private detail columns, and pagination", async () => {
    render(<MemoryRouter><TransportRequestReportPage /></MemoryRouter>);
    expect(await screen.findByText("TR-001")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Report summary")).getByText("12")).toBeInTheDocument();
    expect(screen.queryByText("Daily request volume")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View" })).toHaveAttribute("href", "/transport-requests/request-id");
    expect(screen.queryByText(/contact/i)).not.toBeInTheDocument();
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
  });

  test("sends exact filters and server pagination and exports the current filters", async () => {
    render(<MemoryRouter><TransportRequestReportPage /></MemoryRouter>);
    await screen.findByText("TR-001");
    const filters = screen.getByRole("region", { name: "Report filters" });
    fireEvent.change(within(filters).getByLabelText("source"), { target: { value: "HMS" } });
    await waitFor(() => expect(mocks.fetchReport).toHaveBeenLastCalledWith(expect.objectContaining({ source: "HMS", page: 1 })));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(mocks.fetchReport).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })));
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    fireEvent.click(screen.getByRole("button", { name: "Export Excel" }));
    fireEvent.click(screen.getByRole("button", { name: "Export PDF" }));
    expect(mocks.downloadCsv).toHaveBeenCalledWith(expect.objectContaining({ source: "HMS" }));
    expect(mocks.downloadXlsx).toHaveBeenCalledWith(expect.objectContaining({ source: "HMS" }));
    expect(mocks.downloadPdf).toHaveBeenCalledWith(expect.objectContaining({ source: "HMS" }));
  });

  test("shows an honest error and retries without fake KPIs", async () => {
    mocks.fetchReport.mockRejectedValueOnce(new Error("network")).mockResolvedValueOnce(response);
    render(<MemoryRouter><TransportRequestReportPage /></MemoryRouter>);
    expect(await screen.findByText("Unable to load this report.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Report summary")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("TR-001")).toBeInTheDocument();
  });
});
