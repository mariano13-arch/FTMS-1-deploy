import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import RolesPermissionsPage from "./RolesPermissionsPage";
import type { PermissionMatrix } from "./permissionsApi";

const mocks = vi.hoisted(() => ({
  role: "FLEET_ADMIN",
  getRolePermissions: vi.fn(),
  replaceRolePermissions: vi.fn(),
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { role: mocks.role } }),
}));

vi.mock("./permissionsApi", () => ({
  getRolePermissions: mocks.getRolePermissions,
  replaceRolePermissions: mocks.replaceRolePermissions,
}));

const matrix: PermissionMatrix = {
  definitions: {
    DASHBOARD: ["VIEW"],
    TRANSPORT_REQUESTS: ["VIEW", "EDIT", "APPROVE", "REJECT", "REQUEST_MORE_DETAILS", "PREPARE_DISPATCH", "CANCEL"],
    DISPATCH_BOARD: ["VIEW", "GENERATE_RECOMMENDATION", "ASSIGN", "DISPATCH", "OVERRIDE"],
    LIVE_MAP: ["VIEW", "MANAGE_GEOFENCES"],
    DRIVERS: ["VIEW", "CREATE", "EDIT", "MANAGE_DOCUMENTS"],
    DRIVER_SAFETY: ["VIEW"],
    VEHICLES: ["VIEW", "CREATE", "EDIT", "CHANGE_STATUS", "MANAGE_DOCUMENTS"],
    INSPECTIONS: ["VIEW", "CREATE", "CORRECT"],
    ALERTS_SOS: ["VIEW"],
    FUEL_ANALYTICS: ["VIEW"],
    MAINTENANCE: ["VIEW", "CREATE", "SCHEDULE", "START", "COMPLETE", "CANCEL"],
    REPORTS: ["VIEW", "EXPORT"],
    DEVICES: ["VIEW", "REGISTER", "PAIR", "REPLACE", "UNPAIR"],
    SYSTEM_SETTINGS: ["VIEW", "MANAGE_NUMBER_CODING", "MANAGE_PRICES"],
    USERS_ACCESS: ["VIEW_USERS", "CREATE_USER"],
    SPECIAL_MODULE: ["DO_THING"],
  },
  roles: {
    FLEET_MANAGER: {
      TRANSPORT_REQUESTS: ["VIEW", "EDIT", "APPROVE", "CANCEL"],
      LIVE_MAP: ["VIEW", "MANAGE_GEOFENCES"],
      USERS_ACCESS: [],
      SPECIAL_MODULE: ["DO_THING"],
    },
    DISPATCHER: {
      TRANSPORT_REQUESTS: ["VIEW", "EDIT"],
      LIVE_MAP: ["VIEW"],
      USERS_ACCESS: [],
      SPECIAL_MODULE: [],
    },
    FLEET_STAFF: {
      TRANSPORT_REQUESTS: ["VIEW"],
      LIVE_MAP: ["VIEW"],
      USERS_ACCESS: [],
      SPECIAL_MODULE: [],
    },
  },
};

const cloneMatrix = () => structuredClone(matrix);
const renderPage = () => render(<MemoryRouter initialEntries={["/users/roles-permissions"]}><RolesPermissionsPage /></MemoryRouter>);
const loadPage = async () => {
  renderPage();
  expect(screen.getByRole("status")).toHaveTextContent("Loading roles and permissions");
  return screen.findByRole("table", { name: "Fleet Manager permission matrix" });
};

describe("RolesPermissionsPage", () => {
  beforeEach(() => {
    mocks.role = "FLEET_ADMIN";
    mocks.getRolePermissions.mockReset().mockResolvedValue(cloneMatrix());
    mocks.replaceRolePermissions.mockReset();
  });

  test("renders API-defined modules, actions, and only managed role choices", async () => {
    await loadPage();
    expect(screen.getByText("Special Module")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Special Module: Do Thing" })).toBeChecked();
    expect(screen.queryByRole("checkbox", { name: "Transport Requests: Create" })).not.toBeInTheDocument();
    const selector = screen.getByLabelText("Role / User Type");
    expect(within(selector).getAllByRole("option").map((option) => option.textContent)).toEqual(["Fleet Manager", "Dispatcher", "Fleet Staff"]);
    expect(screen.getByText(/Fleet Admin has full administrative access within FTMS/)).toBeInTheDocument();
    expect(mocks.replaceRolePermissions).not.toHaveBeenCalled();
  });

  test("renders every P2-A row with professional action labels", async () => {
    await loadPage();
    for (const name of ["Dashboard", "Transport Requests", "Dispatch Board", "Live Map", "Drivers", "Driver Safety", "Vehicles", "Inspections", "Alerts & SOS", "Fleet Fuel Analytics", "Maintenance & Predictions", "Reports", "Devices", "System Rules & Settings", "Users & Access"]) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
    expect(screen.getByRole("checkbox", { name: "Dispatch Board: Generate Recommendation" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Transport Requests: Request More Details" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "System Rules & Settings: Manage Fuel Prices" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Vehicles: Inspect" })).not.toBeInTheDocument();
  });

  test("loads each role's current grants and keeps role drafts isolated", async () => {
    await loadPage();
    const selector = screen.getByLabelText("Role / User Type");
    fireEvent.change(selector, { target: { value: "DISPATCHER" } });
    await screen.findByRole("table", { name: "Dispatcher permission matrix" });
    expect(screen.getByRole("checkbox", { name: "Live Map: Manage Geofences" })).not.toBeChecked();
    fireEvent.change(selector, { target: { value: "FLEET_MANAGER" } });
    expect(await screen.findByRole("checkbox", { name: "Live Map: Manage Geofences" })).toBeChecked();
  });

  test("tracks individual edits and reset restores server grants", async () => {
    await loadPage();
    const checkbox = screen.getByRole("checkbox", { name: "Users & Access: View Users" });
    fireEvent.click(checkbox);
    expect(checkbox).toBeChecked();
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Reset/ }));
    expect(checkbox).not.toBeChecked();
    expect(screen.getByText("All changes saved")).toBeInTheDocument();
  });

  test("module Master selects and clears only valid actions", async () => {
    await loadPage();
    const master = screen.getByRole("checkbox", { name: "Master permissions for Users & Access" });
    fireEvent.click(master);
    expect(master).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Users & Access: View Users" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Users & Access: Create User" })).toBeChecked();
    fireEvent.click(master);
    expect(master).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Users & Access: View Users" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Users & Access: Create User" })).not.toBeChecked();
  });

  test("confirms save and sends the complete selected permission set", async () => {
    mocks.replaceRolePermissions.mockImplementation(async (_role, permissions) => {
      const updated = cloneMatrix();
      updated.roles.FLEET_MANAGER.USERS_ACCESS = permissions.filter((item: { module: string }) => item.module === "USERS_ACCESS").map((item: { action: string }) => item.action);
      return updated;
    });
    await loadPage();
    fireEvent.click(screen.getByRole("checkbox", { name: "Users & Access: View Users" }));
    fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Save Changes" }));
    await waitFor(() => expect(mocks.replaceRolePermissions).toHaveBeenCalledOnce());
    const [role, permissions] = mocks.replaceRolePermissions.mock.calls[0];
    expect(role).toBe("FLEET_MANAGER");
    expect(permissions).toContainEqual({ module: "USERS_ACCESS", action: "VIEW_USERS" });
    expect(permissions).not.toContainEqual(expect.objectContaining({ action: "MASTER" }));
    expect(await screen.findByText("Fleet Manager permissions saved.")).toBeInTheDocument();
    expect(screen.getByText("All changes saved")).toBeInTheDocument();
  });

  test("preserves the draft and reports a failed save", async () => {
    mocks.replaceRolePermissions.mockRejectedValue(new Error("network"));
    await loadPage();
    const checkbox = screen.getByRole("checkbox", { name: "Users & Access: View Users" });
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Save Changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be saved");
    expect(checkbox).toBeChecked();
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  });

  test("requires confirmation before discarding changes on role switch", async () => {
    await loadPage();
    fireEvent.click(screen.getByRole("checkbox", { name: "Users & Access: View Users" }));
    const selector = screen.getByLabelText("Role / User Type");
    fireEvent.change(selector, { target: { value: "DISPATCHER" } });
    let dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(selector).toHaveValue("FLEET_MANAGER");
    fireEvent.change(selector, { target: { value: "DISPATCHER" } });
    dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard & Switch" }));
    await waitFor(() => expect(selector).toHaveValue("DISPATCHER"));
    expect(screen.getByRole("checkbox", { name: "Users & Access: View Users" })).not.toBeChecked();
  });

  test("shows a deterministic load error", async () => {
    mocks.getRolePermissions.mockRejectedValue(new Error("network"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be loaded");
  });

  test("denies non-Fleet Admin users without requesting policy data", () => {
    mocks.role = "FLEET_MANAGER";
    renderPage();
    expect(screen.getByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(screen.getByText("Only a Fleet Admin can manage role permissions.")).toBeInTheDocument();
    expect(mocks.getRolePermissions).not.toHaveBeenCalled();
  });
});
