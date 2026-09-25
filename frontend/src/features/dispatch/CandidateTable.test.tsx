import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";
import CandidateTable, {
  ExclusionsPanel,
  FuelAdvisory,
  fuelBasisLabel,
  fuelGradeLabel,
  fuelReasonLabel,
} from "./CandidateTable";
import type { CandidateComparison, RecommendationResponse } from "../../services/dispatch";

const fuelEstimate = {
  status: "UNAVAILABLE" as const,
  reason: "NO_VALID_PREFERRED_PARTNER_PRICE",
  fuel_rate_basis: "FLEET_REFERENCE_BASELINE" as const,
  fuel_rate_lph: "7.0000",
  travel_time_seconds: "600",
  estimated_fuel_liters: "1.1667",
  fuel_type: "DIESEL",
  fuel_grade: "REGULAR_DIESEL",
  price_per_liter: null,
  currency: null,
  price_provider: null,
  price_source_mode: null,
  price_effective_at: null,
  estimated_fuel_cost_php: null,
  fuel_source_timestamp: null,
  history_sample_count: 0,
  fuel_rate_provenance: "CAPSTONE_REFERENCE",
};

const candidates = (count: number): CandidateComparison[] => Array.from({ length: count }, (_, index) => ({
  driver: { id: index + 1, driver_code: `DRV-${index + 1}`, full_name: `Driver ${index + 1}`, eligibility_status: "ELIGIBLE" },
  vehicle: { id: index + 1, device_id: `V-${index + 1}`, plate_number: `P-${index + 1}`, display_name: `Vehicle ${index + 1}`, vehicle_type: "VAN", passenger_capacity: 8, is_active: true },
  travel_time_seconds: index * 60,
  distance_meters: index * 100,
  traffic_delay_seconds: 0,
  result: index === 0 ? "RECOMMENDED" : "FEASIBLE",
  fuel_estimate: fuelEstimate,
}));

test("paginates candidates by ten without re-ranking and supports both directions", () => {
  render(<CandidateTable items={candidates(12)} limited={false} />);
  const table = screen.getByRole("region", { name: "Candidate Comparison" });
  expect(within(table).getAllByRole("row")).toHaveLength(11);
  expect(within(table).getByText("Driver 1")).toBeInTheDocument();
  expect(within(table).getByText("Recommended")).toBeInTheDocument();
  expect(within(table).getByText("Showing 1–10 of 12")).toBeInTheDocument();
  expect(within(table).getByRole("button", { name: "Previous" })).toBeDisabled();
  fireEvent.click(within(table).getByRole("button", { name: "Next" }));
  expect(within(table).getByText("Driver 11")).toBeInTheDocument();
  expect(within(table).queryByText("Driver 1")).not.toBeInTheDocument();
  expect(within(table).getByRole("button", { name: "Next" })).toBeDisabled();
  fireEvent.click(within(table).getByRole("button", { name: "Previous" }));
  expect(within(table).getByText("Driver 1")).toBeInTheDocument();
});

test("resets candidate pagination when the returned dataset changes", () => {
  const { rerender } = render(<CandidateTable items={candidates(12)} limited={false} />);
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
  rerender(<CandidateTable items={candidates(11).map((item) => ({ ...item, driver: { ...item.driver, full_name: `New ${item.driver.full_name}` } }))} limited={false} />);
  expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
  expect(screen.getByText("New Driver 1")).toBeInTheDocument();
});

test("shows compact partial fuel data without changing candidate order", () => {
  render(<CandidateTable items={candidates(2)} limited={false} />);
  const rows = screen.getAllByRole("row");
  expect(within(rows[1]).getByText("Driver 1")).toBeInTheDocument();
  expect(within(rows[1]).getByText("1.1667 L")).toBeInTheDocument();
  expect(within(rows[1]).getByText("Cost unavailable")).toBeInTheDocument();
  expect(within(rows[1]).getByText("Fleet Reference")).toBeInTheDocument();
  expect(within(rows[2]).getByText("Driver 2")).toBeInTheDocument();
});

test("maps fuel bases, grades, and machine reasons to professional labels", () => {
  expect(fuelBasisLabel("CURRENT_AI")).toBe("Current AI");
  expect(fuelBasisLabel("HISTORICAL_AI_BASELINE")).toBe("Historical AI Baseline");
  expect(fuelBasisLabel("FLEET_REFERENCE_BASELINE")).toBe("Fleet Reference Baseline");
  expect(fuelBasisLabel("FLEET_REFERENCE_BASELINE")).not.toMatch(/demo|test|dummy/i);
  expect(fuelGradeLabel("UNLEADED_91")).toBe("Unleaded 91");
  expect(fuelGradeLabel("PREMIUM_95")).toBe("Premium 95");
  expect(fuelGradeLabel("PREMIUM_97")).toBe("Premium 97");
  expect(fuelGradeLabel("REGULAR_DIESEL")).toBe("Regular Diesel");
  expect(fuelGradeLabel("PREMIUM_DIESEL")).toBe("Premium Diesel");
  expect(fuelGradeLabel(null)).toBe("Not recorded");
  expect(fuelReasonLabel("FUEL_GRADE_NOT_RECORDED")).toBe("Fuel grade not recorded");
  expect(fuelReasonLabel("NO_VALID_PREFERRED_PARTNER_PRICE")).toBe("No valid Shell partner price");
  expect(fuelReasonLabel("INSUFFICIENT_ELIGIBLE_SAME_VEHICLE_HISTORY")).toBe("Insufficient vehicle fuel history");
});

test("renders partial reference data and unavailable partner pricing independently", () => {
  render(<FuelAdvisory estimate={fuelEstimate} />);
  const advisory = screen.getByRole("region", { name: "Fuel and Cost" });
  expect(within(advisory).getByText("7.0000 L/h")).toBeInTheDocument();
  expect(within(advisory).getByText("1.1667 L")).toBeInTheDocument();
  expect(within(advisory).getByText("Regular Diesel")).toBeInTheDocument();
  expect(within(advisory).getByText("Fleet Reference Baseline")).toBeInTheDocument();
  expect(within(advisory).getByText("Configured fleet reference")).toBeInTheDocument();
  expect(within(advisory).getAllByText("Unavailable")).toHaveLength(2);
  expect(within(advisory).getByText("No valid Shell partner price")).toBeInTheDocument();
  expect(advisory).not.toHaveTextContent(/null|undefined|NaN|demo|test|dummy/i);
});

test("renders factual historical samples and available Shell price and cost", () => {
  render(
    <FuelAdvisory
      estimate={{
        ...fuelEstimate,
        status: "AVAILABLE",
        reason: null,
        fuel_rate_basis: "HISTORICAL_AI_BASELINE",
        price_per_liter: "96.5000",
        currency: "PHP",
        price_provider: "ShellPH",
        price_source_mode: "MANUAL",
        estimated_fuel_cost_php: "112.58",
        history_sample_count: 5,
      }}
    />,
  );
  expect(screen.getByText("Historical AI Baseline")).toBeInTheDocument();
  expect(screen.getByText("Based on 5 vehicle predictions")).toBeInTheDocument();
  expect(screen.getByText("₱96.5000/L")).toBeInTheDocument();
  expect(screen.getByText("Shell")).toBeInTheDocument();
  expect(screen.getByText("₱112.58")).toBeInTheDocument();
});

test("groups, deduplicates, collapses, expands, and paginates exclusions", () => {
  type Exclusion = RecommendationResponse["excluded_candidates"][string][number];
  const items: Exclusion[] = [
    ...Array.from({ length: 12 }, (_, index) => ({ kind: "VEHICLE" as const, name: `Vehicle ${index + 1}`, code: `V-${index + 1}`, reason: "VEHICLE_TYPE_MISMATCH", details: ["Wrong type"] })),
    { kind: "VEHICLE", name: "Vehicle 1", code: "V-1", reason: "VEHICLE_TYPE_MISMATCH", details: ["Wrong type"] },
    { kind: "DRIVER", name: "Driver 1", code: "D-1", reason: "RESTRICTED", details: ["Restricted"] },
  ];
  render(<ExclusionsPanel items={items} />);
  expect(screen.getByText("Vehicle Type Mismatch")).toBeInTheDocument();
  expect(screen.queryByText("Vehicle 12")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Vehicle Type Mismatch/ }));
  expect(screen.getByText("Showing 1–10 of 12")).toBeInTheDocument();
  expect(screen.getAllByText("Vehicle 1")).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  expect(screen.getByText("Vehicle 12")).toBeInTheDocument();
});
