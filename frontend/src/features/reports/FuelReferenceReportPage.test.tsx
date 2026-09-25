import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import FuelReferenceReportPage from "./FuelReferenceReportPage";

const mocks = vi.hoisted(() => ({ fetchReport: vi.fn(), downloadCsv: vi.fn() }));
vi.mock("./api", () => ({ fetchFuelReferenceReport: mocks.fetchReport, downloadFuelReferenceCsv: mocks.downloadCsv }));
const page = <T,>(results: T[]) => ({ count: results.length, page: 1, page_size: 15, total_pages: results.length ? 1 : 0, results });
const response = {
  meta: { title: "Fuel Predictions & Reference Data", generated_at: "2026-09-21T00:00:00Z", generated_by: "Fleet Manager", timezone: "Asia/Manila", date_from: "2026-08-23", date_to: "2026-09-21", prediction_date_basis: "FuelPrediction.input_timestamp", price_date_basis: "FuelPriceRecord.effective_at" },
  summary: { eligible_predictions: 1, vehicles_with_reference_baselines: 1, fuel_grades_with_current_reference_price: 1, latest_eligible_prediction_at: "2026-09-20T04:00:00Z" },
  choices: { vehicles: [{ value: 1, label: "Fuel Van · VEH-1" }], prediction_sources: [{ value: "validated_vehicle_telemetry", label: "validated_vehicle_telemetry" }], fuel_types: [{ value: "GASOLINE", label: "Gasoline" }], fuel_grades: [{ value: "UNLEADED_91", label: "Unleaded 91" }], price_sources: [{ value: "MANUAL", label: "Manual" }], providers: [{ value: "ShellPH", label: "ShellPH" }] },
  predictions: page([{ id: 1, vehicle: { id: 1, name: "Fuel Van", identifier: "VEH-1" }, estimated_fuel_lph: "8.3000", input_timestamp: "2026-09-20T04:00:00Z", predicted_at: "2026-09-20T04:00:01Z", model_name: "Fuel Model", model_version: "v1", source_mode: "validated_vehicle_telemetry", provenance_label: "Predicted · Operational telemetry", operational_source: true }]),
  baselines: page([{ id: 2, vehicle: { id: 1, name: "Fuel Van", identifier: "VEH-1" }, fuel_type_label: "Gasoline", fuel_grade_label: "Unleaded 91", reference_fuel_rate_lph: "8.0000", provenance: "CAPSTONE_REFERENCE", provenance_label: "Fleet Reference Baseline · Capstone Reference", basis_version: "fleet-v1", is_active: true }]),
  prices: page([{ id: 3, provider: "ShellPH", fuel_type_label: "Gasoline", fuel_grade_label: "Unleaded 91", price_per_liter: "61.2500", currency: "PHP", source_mode: "MANUAL", source_mode_label: "Manual", effective_at: "2026-09-20T04:00:00Z", retrieved_at: "2026-09-20T04:00:01Z", is_active: true, provenance_label: "Reference price" }]),
};

beforeEach(() => { vi.clearAllMocks(); mocks.fetchReport.mockResolvedValue(response); mocks.downloadCsv.mockResolvedValue(undefined); });

describe("Fuel Predictions & Reference Data", () => {
  test("keeps predicted, baseline, and price provenance distinct", async () => {
    render(<MemoryRouter><FuelReferenceReportPage /></MemoryRouter>);
    expect(await screen.findByText("8.3000")).toBeInTheDocument();
    expect(screen.getByText("Predicted · Operational telemetry")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Fleet Reference Baselines" }));
    expect(screen.getByText("Fleet Reference Baseline · Capstone Reference")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Fuel Reference Prices" }));
    expect(screen.getAllByText("ShellPH").length).toBeGreaterThan(0);
    expect(screen.queryByText(/Actual fuel|Actual expense|Savings|Accuracy/)).not.toBeInTheDocument();
  });

  test("filters and exports the selected data category", async () => {
    render(<MemoryRouter><FuelReferenceReportPage /></MemoryRouter>);
    await screen.findByText("8.3000");
    fireEvent.change(screen.getByLabelText("Prediction source"), { target: { value: "validated_vehicle_telemetry" } });
    await waitFor(() => expect(mocks.fetchReport).toHaveBeenLastCalledWith(expect.objectContaining({ prediction_source: "validated_vehicle_telemetry" })));
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    expect(mocks.downloadCsv).toHaveBeenCalledWith("predictions", expect.any(Object));
  });

  test("shows empty and error states", async () => {
    mocks.fetchReport.mockResolvedValueOnce({ ...response, predictions: page([]) });
    const rendered = render(<MemoryRouter><FuelReferenceReportPage /></MemoryRouter>);
    expect(await screen.findByText("No predictions match the current filters.")).toBeInTheDocument();
    rendered.unmount();
    mocks.fetchReport.mockRejectedValueOnce(new Error("offline"));
    render(<MemoryRouter><FuelReferenceReportPage /></MemoryRouter>);
    expect(await screen.findByText("Unable to load this report.")).toBeInTheDocument();
  });
});
