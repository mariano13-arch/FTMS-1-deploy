import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import InspectionMaintenanceReportPage from "./InspectionMaintenanceReportPage";

const mocks = vi.hoisted(() => ({
  fetchReport: vi.fn(),
  downloadCsv: vi.fn(),
}));
vi.mock("./api", () => ({
  fetchInspectionMaintenanceReport: mocks.fetchReport,
  downloadInspectionMaintenanceCsv: mocks.downloadCsv,
}));

const inspection = {
  id: 1,
  inspection_date: "2026-09-20",
  inspection_type_label: "Pre-trip",
  result_label: "Needs attention",
  vehicle: { name: "Inspection Van", identifier: "INSPECT-1" },
  inspector: "Fleet Manager",
  odometer_km: 1200,
  fuel_level_percent: 75,
  exception_count: 1,
  issues_found: "Brake wear",
  notes: "Schedule service",
  checklist: {
    brakes: { value: "NEEDS_ATTENTION", label: "Needs attention" },
    lights: { value: "OK", label: "OK" },
  },
  related_maintenance: [
    { id: 2, title: "Brake service", status_label: "Open" },
  ],
};
const maintenance = {
  id: 2,
  created_at: "2026-09-20T04:00:00Z",
  vehicle: { name: "Inspection Van", identifier: "INSPECT-1" },
  title: "Brake service",
  source_label: "Inspection",
  status_label: "Open",
  scheduled_at: null,
  started_at: null,
  completed_at: null,
  notes: "Parts requested",
  creator: "Fleet Manager",
  linked_inspection: {
    inspection_date: "2026-09-20",
    type_label: "Pre-trip",
    result_label: "Needs attention",
  },
};
const response = {
  meta: {
    title: "Inspection & Maintenance",
    generated_at: "2026-09-21T00:00:00Z",
    generated_by: "Fleet Manager",
    timezone: "Asia/Manila",
    date_basis: "",
    date_from: "2026-08-23",
    date_to: "2026-09-21",
  },
  summary: {
    inspections: 3,
    passed: 1,
    needs_attention: 1,
    failed: 1,
    active_maintenance: 2,
    completed_maintenance: 1,
  },
  trend: [{ date: "2026-09-20", count: 3 }],
  breakdowns: {
    inspection_results: [{ value: "PASSED", label: "Passed", count: 1 }],
    checklist_attention: [
      { value: "brakes_condition", label: "Brakes", count: 1 },
    ],
    maintenance_status: [{ value: "OPEN", label: "Open", count: 2 }],
    maintenance_source: [
      { value: "INSPECTION", label: "Inspection", count: 1 },
    ],
  },
  choices: {
    vehicles: [{ value: 1, label: "Inspection Van · INSPECT-1" }],
    inspection_types: [{ value: "PRE_TRIP", label: "Pre-trip" }],
    inspection_results: [
      { value: "NEEDS_ATTENTION", label: "Needs attention" },
    ],
    maintenance_statuses: [{ value: "OPEN", label: "Open" }],
    maintenance_sources: [{ value: "INSPECTION", label: "Inspection" }],
  },
  inspections: {
    count: 16,
    page: 1,
    page_size: 15,
    total_pages: 2,
    results: [inspection],
  },
  maintenance: {
    count: 1,
    page: 1,
    page_size: 15,
    total_pages: 1,
    results: [maintenance],
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.fetchReport.mockResolvedValue(response);
  mocks.downloadCsv.mockResolvedValue(undefined);
});

describe("Inspection & Maintenance report", () => {
  test("renders KPIs, breakdowns, and inspection details", async () => {
    render(
      <MemoryRouter>
        <InspectionMaintenanceReportPage />
      </MemoryRouter>,
    );
    await screen.findByText("INSPECT-1");
    expect(screen.getByText("Checklist Attention Areas")).toBeInTheDocument();
    expect(screen.queryByText("Inspections Over Time")).not.toBeInTheDocument();
    expect(
      screen.getByText("Active Maintenance · Current"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View" }));
    const drawer = screen.getByLabelText("Inspection details");
    expect(within(drawer).getByText("Brake wear")).toBeInTheDocument();
    expect(
      within(drawer).getByText("Brake service · Open"),
    ).toBeInTheDocument();
    expect(
      within(drawer).queryByRole("button", { name: /edit|complete|cancel/i }),
    ).not.toBeInTheDocument();
  });

  test("filters and paginates inspections, then exports the active tab", async () => {
    render(
      <MemoryRouter>
        <InspectionMaintenanceReportPage />
      </MemoryRouter>,
    );
    await screen.findByText("INSPECT-1");
    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "INSPECT" },
    });
    await waitFor(() =>
      expect(mocks.fetchReport).toHaveBeenLastCalledWith(
        expect.objectContaining({
          inspection_search: "INSPECT",
          inspection_page: 1,
        }),
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(mocks.fetchReport).toHaveBeenLastCalledWith(
        expect.objectContaining({ inspection_page: 2 }),
      ),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Export Inspections CSV" }),
    );
    expect(mocks.downloadCsv).toHaveBeenCalledWith(
      "inspections",
      expect.any(Object),
    );
  });

  test("switches to maintenance, filters, opens its drawer, and exports", async () => {
    render(
      <MemoryRouter>
        <InspectionMaintenanceReportPage />
      </MemoryRouter>,
    );
    await screen.findByText("INSPECT-1");
    fireEvent.click(screen.getByRole("button", { name: "Maintenance" }));
    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "OPEN" },
    });
    await waitFor(() =>
      expect(mocks.fetchReport).toHaveBeenLastCalledWith(
        expect.objectContaining({
          maintenance_status: "OPEN",
          maintenance_page: 1,
        }),
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "View" }));
    expect(screen.getByLabelText("Maintenance details")).toBeInTheDocument();
    expect(screen.getByText("Parts requested")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Export Maintenance CSV" }),
    );
    expect(mocks.downloadCsv).toHaveBeenCalledWith(
      "maintenance",
      expect.any(Object),
    );
  });

  test("distinguishes an empty result from an API failure", async () => {
    mocks.fetchReport.mockResolvedValueOnce({
      ...response,
      inspections: {
        ...response.inspections,
        count: 0,
        total_pages: 0,
        results: [],
      },
    });
    const { unmount } = render(
      <MemoryRouter>
        <InspectionMaintenanceReportPage />
      </MemoryRouter>,
    );
    expect(
      await screen.findByText("No inspections match the selected filters."),
    ).toBeInTheDocument();
    unmount();
    mocks.fetchReport.mockRejectedValueOnce(new Error("offline"));
    render(
      <MemoryRouter>
        <InspectionMaintenanceReportPage />
      </MemoryRouter>,
    );
    expect(
      await screen.findByText("Unable to load this report."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Active Maintenance · Current"),
    ).not.toBeInTheDocument();
  });
});
