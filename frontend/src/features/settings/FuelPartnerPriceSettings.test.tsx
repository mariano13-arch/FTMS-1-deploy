import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import FuelPartnerPriceSettings from "./FuelPartnerPriceSettings";

const mocks = vi.hoisted(() => ({ get:vi.fn(), record:vi.fn(), role:"FLEET_MANAGER" }));
vi.mock("../../services/fuelPartnerPrices", () => ({
  getPartnerFuelPrices:mocks.get,
  recordPartnerFuelPrice:mocks.record,
}));
vi.mock("../../contexts/AuthContext", () => ({ useAuth:() => ({ user:{ role:mocks.role } }) }));

const products = [
  ["UNLEADED_91", "Unleaded 91", "GASOLINE", 50],
  ["PREMIUM_95", "Premium 95", "GASOLINE", 0],
  ["PREMIUM_97", "Premium 97", "GASOLINE", 0],
  ["REGULAR_DIESEL", "Regular Diesel", "DIESEL", 150],
  ["PREMIUM_DIESEL", "Premium Diesel", "DIESEL", 0],
].map(([fuel_grade,label,fuel_type,vehicle_count], index) => ({
  fuel_grade,label,fuel_type,vehicle_count,
  current_price:index === 0 ? {
    id:1,fuel_type:"GASOLINE",fuel_grade:"UNLEADED_91",price_per_liter:"71.2500",
    currency:"PHP",provider:"ShellPH",source_mode:"MANUAL",
    effective_at:"2026-09-20T00:00:00+08:00",recorded_at:"2026-09-20T00:01:00+08:00",
    is_active:true,
  } : null,
  history:[],
}));

beforeEach(() => {
  vi.clearAllMocks(); mocks.role = "FLEET_MANAGER";
  mocks.get.mockResolvedValue({ provider:"ShellPH", provider_label:"Shell", products });
  mocks.record.mockResolvedValue({});
});

test("shows all exact grades, factual current price, and unconfigured states", async () => {
  render(<FuelPartnerPriceSettings />);
  expect(await screen.findByText("₱71.2500/L")).toBeInTheDocument();
  for (const label of [
    "Unleaded 91", "Premium 95", "Premium 97", "Regular Diesel", "Premium Diesel",
  ]) expect(screen.getAllByText(label).length).toBeGreaterThan(0);
  expect(screen.getAllByText("Not configured")).toHaveLength(4);
  expect(screen.getByText(/Used for estimated dispatch fuel cost/i)).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent(/GasWatch|GlobalPetrolPrices/);
});

test("records only operator-entered grade price and effective timestamp", async () => {
  render(<FuelPartnerPriceSettings />);
  await screen.findByText("₱71.2500/L");
  fireEvent.change(screen.getByLabelText("Fuel Grade"), { target:{ value:"REGULAR_DIESEL" } });
  fireEvent.change(screen.getByLabelText("Price per Liter (PHP)"), { target:{ value:"73.5000" } });
  fireEvent.change(screen.getByLabelText("Effective Date / Time"), { target:{ value:"2026-09-20T10:30" } });
  fireEvent.click(screen.getByRole("button", { name:"Record Price" }));
  await waitFor(() => expect(mocks.record).toHaveBeenCalledTimes(1));
  expect(mocks.record.mock.calls[0][0]).toMatchObject({
    fuel_grade:"REGULAR_DIESEL", price_per_liter:"73.5000",
  });
  expect(mocks.record.mock.calls[0][0]).not.toHaveProperty("provider");
  expect(mocks.record.mock.calls[0][0]).not.toHaveProperty("currency");
});

test("dispatcher has read-only settings without a price-entry form", async () => {
  mocks.role = "DISPATCHER";
  render(<FuelPartnerPriceSettings />);
  expect(await screen.findByText("₱71.2500/L")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name:"Record Price" })).not.toBeInTheDocument();
});
