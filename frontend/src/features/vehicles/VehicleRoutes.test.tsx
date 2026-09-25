import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import { VehicleDrawer, VehicleForm } from "./VehicleRoutes";
import type { Vehicle } from "../../services/vehicles";
import { ApiError } from "../../services/api";

const mocks = vi.hoisted(() => ({ editVehicle: vi.fn() }));
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { role: "FLEET_MANAGER" } }),
}));
vi.mock("../../services/vehicles", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../services/vehicles")>()),
  editVehicle: mocks.editVehicle,
}));

const vehicle = {
  device_id: "PHOTO-001", plate_number: "PIC-001", display_name: "Photo Vehicle",
  vehicle_type: "VAN", manufacturer: "", model: "", model_year: null,
  passenger_capacity: null, payload_capacity_kg: null, gvwr_kg: null, vin: "",
  engine_number: "", chassis_number: "", color: "", fuel_type: "", fuel_grade: "",
  transmission_type: "", ownership_type: "", supplier_name: "",
  purchase_order_number: "", acquisition_date: null, purchase_price: null,
  purchase_currency: "", warranty_expiry_date: null, registration_expiry_date: null,
  insurance_expiry_date: null, photo_url: "/api/v1/vehicles/PHOTO-001/photo/",
  is_active: true, created_at: "", updated_at: "", latest_inspection: null,
  document_count: 0, document_health: "INCOMPLETE",
} satisfies Vehicle;

beforeEach(() => {
  mocks.editVehicle.mockResolvedValue(vehicle);
  vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:preview"), revokeObjectURL: vi.fn() });
});

test("authorized edit flow previews and uploads an optional vehicle photo", async () => {
  render(<MemoryRouter><VehicleForm editing embedded initialVehicle={vehicle} targetDeviceId="PHOTO-001" /></MemoryRouter>);
  expect(screen.getByLabelText(/Vehicle photo/)).toHaveAttribute("accept", "image/jpeg,image/png,image/webp");
  expect(screen.getByAltText("Photo Vehicle preview")).toHaveAttribute(
    "src", "http://localhost:8000/api/v1/vehicles/PHOTO-001/photo/",
  );
  const photo = new File(["photo"], "vehicle.webp", { type: "image/webp" });
  fireEvent.change(screen.getByLabelText(/Vehicle photo/), { target: { files: [photo] } });
  expect(screen.getByAltText("Photo Vehicle preview")).toHaveAttribute("src", "blob:preview");
  fireEvent.click(screen.getByRole("button", { name: "Save vehicle" }));
  await waitFor(() => expect(mocks.editVehicle).toHaveBeenCalled());
  const body = mocks.editVehicle.mock.calls[0][1] as FormData;
  expect(body).toBeInstanceOf(FormData);
});

test("shows exact validation reasons in their vehicle section", async () => {
  mocks.editVehicle.mockRejectedValueOnce(new ApiError(400, {
    photo: ["Only JPG, JPEG, PNG, and WebP files are allowed."],
    model_year: ["Must be between 1980 and next year."],
  }));
  render(<MemoryRouter><VehicleForm editing embedded initialVehicle={vehicle} targetDeviceId="PHOTO-001" /></MemoryRouter>);
  fireEvent.click(screen.getByRole("button", { name: "Save vehicle" }));
  expect(await screen.findByText("Vehicle Specifications", { selector: ".vehicle-form-section-error strong" })).toBeInTheDocument();
  expect(screen.queryByText("Identity", { selector: ".vehicle-form-section-error strong" })).not.toBeInTheDocument();
  expect(screen.getAllByText(/Only JPG, JPEG, PNG, and WebP/)).toHaveLength(1);
  expect(screen.getByText(/Must be between 1980 and next year/)).toBeInTheDocument();
  expect(screen.queryByText("Please correct the vehicle information.")).not.toBeInTheDocument();
});

test("fuel type and dependent fuel grade choices use only the backend domain", () => {
  render(<MemoryRouter><VehicleForm editing embedded initialVehicle={vehicle} targetDeviceId="PHOTO-001" /></MemoryRouter>);
  const fuelType = screen.getByRole("combobox", { name: "Fuel Type" });
  expect(Array.from((fuelType as HTMLSelectElement).options).map(option => option.text)).toEqual([
    "Not recorded", "Gasoline", "Diesel",
  ]);
  const fuelGrade = screen.getByRole("combobox", { name: "Fuel Grade" });
  expect(fuelGrade).toBeDisabled();
  expect(fuelGrade).toHaveValue("");
  fireEvent.change(fuelType, { target: { value: "GASOLINE" } });
  expect(Array.from((fuelGrade as HTMLSelectElement).options).map(option => option.text)).toEqual([
    "Not recorded", "Unleaded 91", "Premium 95", "Premium 97",
  ]);
  fireEvent.change(fuelGrade, { target: { value: "PREMIUM_95" } });
  fireEvent.change(fuelType, { target: { value: "DIESEL" } });
  expect(fuelGrade).toHaveValue("");
  expect(Array.from((fuelGrade as HTMLSelectElement).options).map(option => option.text)).toEqual([
    "Not recorded", "Regular Diesel", "Premium Diesel",
  ]);
});

test("switching diesel to gasoline clears the grade without selecting a replacement", () => {
  const diesel = { ...vehicle, fuel_type: "DIESEL", fuel_grade: "PREMIUM_DIESEL" } satisfies Vehicle;
  render(<MemoryRouter><VehicleForm editing embedded initialVehicle={diesel} targetDeviceId="PHOTO-001" /></MemoryRouter>);
  const fuelType = screen.getByRole("combobox", { name: "Fuel Type" });
  const fuelGrade = screen.getByRole("combobox", { name: "Fuel Grade" });
  expect(fuelGrade).toHaveValue("PREMIUM_DIESEL");
  fireEvent.change(fuelType, { target: { value: "GASOLINE" } });
  expect(fuelGrade).toHaveValue("");
});

test("vehicle payload includes the factual fuel grade and preserves blank by default", async () => {
  render(<MemoryRouter><VehicleForm editing embedded initialVehicle={vehicle} targetDeviceId="PHOTO-001" /></MemoryRouter>);
  fireEvent.click(screen.getByRole("button", { name: "Save vehicle" }));
  await waitFor(() => expect(mocks.editVehicle).toHaveBeenCalled());
  const body = mocks.editVehicle.mock.calls[0][1] as FormData;
  expect(body.get("fuel_type")).toBe("");
  expect(body.get("fuel_grade")).toBe("");
});

test("read-only vehicle details show a human-readable fuel grade", () => {
  const graded = { ...vehicle, fuel_type: "GASOLINE", fuel_grade: "UNLEADED_91" } satisfies Vehicle;
  render(<MemoryRouter><VehicleDrawer vehicle={graded} role="FLEET_MANAGER" busy={false} initialMode="overview" onEdit={vi.fn()} onInspectionCreated={vi.fn()} onClose={vi.fn()} onToggle={vi.fn()} /></MemoryRouter>);
  expect(screen.getByText("Fuel Grade")).toBeInTheDocument();
  expect(screen.getByText("Unleaded 91")).toBeInTheDocument();
});

test("read-only vehicle details show Not recorded for an existing blank grade", () => {
  render(<MemoryRouter><VehicleDrawer vehicle={vehicle} role="FLEET_MANAGER" busy={false} initialMode="overview" onEdit={vi.fn()} onInspectionCreated={vi.fn()} onClose={vi.fn()} onToggle={vi.fn()} /></MemoryRouter>);
  const label = screen.getByText("Fuel Grade");
  expect(within(label.parentElement!).getByText("Not recorded")).toBeInTheDocument();
});
