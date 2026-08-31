import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import MaintenancePage from "./MaintenancePage";

const mocks = vi.hoisted(() => ({ getVehicles: vi.fn() }));
vi.mock("../../services/vehicles", () => ({ getVehicles: mocks.getVehicles }));
const page = { count: 2, next: null, previous: null, results: [{ device_id: "FTMS-001", display_name: "Service Van", plate_number: "ABC-123", is_active: true, latest_inspection: { id: 1, inspection_date: "2026-08-29", inspection_type: "PERIODIC", result: "NEEDS_ATTENTION" } }, { device_id: "FTMS-002", display_name: "Pool Car", plate_number: "XYZ-789", is_active: false, latest_inspection: null }] };
beforeEach(() => mocks.getVehicles.mockReset());
test("shows loading state", () => { mocks.getVehicles.mockResolvedValue(page); render(<MaintenancePage />); expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument(); });
test("renders real records, disabled future tabs, and truthful review states", async () => { mocks.getVehicles.mockResolvedValue(page); render(<MaintenancePage />); expect(await screen.findByText("Service Van")).toBeInTheDocument(); expect(screen.getByText("NEEDS ATTENTION")).toBeInTheDocument(); expect(screen.getByText("Review needed")).toBeInTheDocument(); expect(screen.getByText("Not evaluated")).toBeInTheDocument(); expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true"); expect(screen.getByRole("tab", { name: "Maintenance Review" })).toBeDisabled(); expect(screen.getByRole("tab", { name: "Inspection Records" })).toBeDisabled(); expect(screen.getAllByText("Prediction unavailable").length).toBeGreaterThan(0); expect(screen.getByText("Predictions unavailable")).toBeInTheDocument(); expect(screen.queryByText("Maintenance risk")).not.toBeInTheDocument(); });
test("renders backend error state", async () => { mocks.getVehicles.mockRejectedValueOnce(new Error("offline")); render(<MaintenancePage />); await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Fleet maintenance records unavailable")); });
