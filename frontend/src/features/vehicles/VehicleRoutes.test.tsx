import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import { VehicleForm } from "./VehicleRoutes";
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
  engine_number: "", chassis_number: "", color: "", fuel_type: "",
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
