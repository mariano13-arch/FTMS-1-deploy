import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import NumberCodingSettings from "./NumberCodingSettings";

const mocks = vi.hoisted(() => ({
  rules:vi.fn(), suspensions:vi.fn(), exemptions:vi.fn(), vehicles:vi.fn(),
  saveRule:vi.fn(), saveSuspension:vi.fn(), saveExemption:vi.fn(),
}));
vi.mock("../../services/numberCoding", () => ({
  getNumberCodingRules:mocks.rules, getNumberCodingSuspensions:mocks.suspensions,
  getVehicleCodingExemptions:mocks.exemptions, saveNumberCodingRule:mocks.saveRule,
  saveNumberCodingSuspension:mocks.saveSuspension,
  saveVehicleCodingExemption:mocks.saveExemption,
}));
vi.mock("../../services/vehicles", () => ({ getVehicles:mocks.vehicles }));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.rules.mockResolvedValue([{ id:1, authority:"MMDA", jurisdiction:"Metro Manila", weekday:0, weekday_label:"Monday", restricted_last_digits:[1,2], start_time:"07:00:00", end_time:"10:00:00", effective_from:"2026-09-01", effective_until:null, is_active:true, source_reference:"Official rule", notes:"", created_at:"", updated_at:"" }]);
  mocks.suspensions.mockResolvedValue([{ id:2, authority:"MMDA", jurisdiction:"Metro Manila", starts_at:"2026-09-30T00:00:00+08:00", ends_at:"2026-09-30T23:59:00+08:00", reason:"Official suspension", source_reference:"Official notice", is_active:true, created_by:1, created_by_name:"Admin", created_at:"", updated_at:"" }]);
  mocks.exemptions.mockResolvedValue([{ id:3, vehicle:7, vehicle_display_name:"Guest Van", plate_number:"ABC-123", authority:"MMDA", jurisdiction:"Metro Manila", starts_at:"2026-09-21T00:00:00+08:00", ends_at:"2026-10-01T00:00:00+08:00", reason:"Verified exemption", source_reference:"Official exemption", is_active:true, verified_by:1, verified_by_name:"Admin", created_at:"", updated_at:"" }]);
  mocks.vehicles.mockResolvedValue({ count:1, next:null, previous:null, results:[{ id:7, display_name:"Guest Van", plate_number:"ABC-123" }] });
  mocks.saveRule.mockResolvedValue({}); mocks.saveSuspension.mockResolvedValue({}); mocks.saveExemption.mockResolvedValue({});
});

test("renders configured weekly rules, suspensions, and real vehicle exemptions", async () => {
  render(<NumberCodingSettings />);
  expect(await screen.findByText("Monday")).toBeInTheDocument();
  expect(screen.getByText("1, 2")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name:"Temporary Suspensions" }));
  expect(await screen.findByText("Official suspension")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name:"Vehicle Exemptions" }));
  expect(await screen.findByText("Guest Van")).toBeInTheDocument();
  expect(screen.getByText("ABC-123")).toBeInTheDocument();
});

test("validates rule time windows before create", async () => {
  render(<NumberCodingSettings />);
  await screen.findByText("Monday");
  fireEvent.click(screen.getByRole("button", { name:"Add Rule" }));
  fireEvent.change(screen.getByLabelText("Restricted Digits"), { target:{ value:"1, 2" } });
  fireEvent.change(screen.getByLabelText("Start Time"), { target:{ value:"10:00" } });
  fireEvent.change(screen.getByLabelText("End Time"), { target:{ value:"07:00" } });
  fireEvent.change(screen.getByLabelText("Effective From"), { target:{ value:"2026-09-01" } });
  fireEvent.change(screen.getByLabelText("Authority"), { target:{ value:"MMDA" } });
  fireEvent.change(screen.getByLabelText("Jurisdiction"), { target:{ value:"Metro Manila" } });
  fireEvent.click(screen.getByRole("button", { name:"Create" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("valid time window");
  expect(mocks.saveRule).not.toHaveBeenCalled();
});

test("deactivates without deleting historical configuration", async () => {
  render(<NumberCodingSettings />);
  await screen.findByText("Monday");
  fireEvent.click(screen.getByRole("button", { name:"Deactivate" }));
  await waitFor(() => expect(mocks.saveRule).toHaveBeenCalledWith({ is_active:false }, 1));
});
