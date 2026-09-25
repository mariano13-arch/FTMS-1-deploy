import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import UsersPage from "./UsersPage";

const mocks = vi.hoisted(() => ({
  role: "FLEET_ADMIN",
  listStaff: vi.fn(),
  createStaff: vi.fn(),
  updateStaffRole: vi.fn(),
  updateStaffStatus: vi.fn(),
  resendStaffInvitation: vi.fn(),
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { role: mocks.role } }),
}));
vi.mock("./api", () => ({
  listStaff: mocks.listStaff,
  createStaff: mocks.createStaff,
  updateStaffRole: mocks.updateStaffRole,
  updateStaffStatus: mocks.updateStaffStatus,
  resendStaffInvitation: mocks.resendStaffInvitation,
}));

const pendingUser = {
  id: 1, username: "fleet.manager", email: "fleet@example.com", first_name: "Fleet", last_name: "Manager",
  role: "FLEET_MANAGER", is_active: true, setup_status: "pending", date_joined: "2026-08-20T00:00:00Z", last_login: null,
};
const readyUser = {
  ...pendingUser, id: 2, username: "dispatcher", email: "dispatch@example.com", first_name: "Dispatch", last_name: "User",
  role: "DISPATCHER", is_active: false, setup_status: "complete", last_login: "2026-08-29T08:00:00Z",
};

function openActions(username: string) {
  fireEvent.click(screen.getByRole("button", { name: `Actions for ${username}` }));
}
const renderUsers = () => render(<MemoryRouter initialEntries={["/users"]}><UsersPage /></MemoryRouter>);

beforeEach(() => {
  mocks.role = "FLEET_ADMIN";
  mocks.listStaff.mockReset().mockResolvedValue([pendingUser, readyUser]);
  mocks.createStaff.mockReset();
  mocks.updateStaffRole.mockReset();
  mocks.updateStaffStatus.mockReset();
  mocks.resendStaffInvitation.mockReset();
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("staff users page", () => {
  test("shows loading, then real summary and pending/ready account states", async () => {
    renderUsers();
    expect(screen.getByText("Loading staff users…")).toBeInTheDocument();
    expect(await screen.findByText("fleet.manager")).toBeInTheDocument();
    expect(screen.getAllByText("Pending Setup")).toHaveLength(2);
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("Never")).toBeInTheDocument();
    expect(screen.getByLabelText("Staff account summary")).toHaveTextContent("2Active1Inactive1Pending Setup1");
  });

  test("add-user form has no password field and reports a sent invitation", async () => {
    mocks.createStaff.mockResolvedValue({ ...pendingUser, invitation_delivery: "SENT" });
    renderUsers();
    await screen.findByText("fleet.manager");
    fireEvent.click(screen.getByRole("button", { name: "Add User" }));
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("First Name"), { target: { value: "New" } });
    fireEvent.change(screen.getByLabelText("Last Name"), { target: { value: "Staff" } });
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "new.staff" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Create & Send Invitation" }));
    expect(await screen.findByText("Account created and setup invitation sent.")).toBeInTheDocument();
    expect(mocks.createStaff).toHaveBeenCalledWith({ first_name: "New", last_name: "Staff", username: "new.staff", email: "new@example.com", role: "FLEET_MANAGER" });
    expect(mocks.listStaff).toHaveBeenCalledTimes(2);
  });

  test("reports invitation delivery failure without exposing a setup link", async () => {
    mocks.createStaff.mockResolvedValue({ ...pendingUser, invitation_delivery: "NOT_SENT_ERROR" });
    renderUsers();
    await screen.findByText("fleet.manager");
    fireEvent.click(screen.getByRole("button", { name: "Add User" }));
    for (const [label, value] of [["First Name", "New"], ["Last Name", "Staff"], ["Username", "new.staff"], ["Email", "new@example.com"]]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    }
    fireEvent.click(screen.getByRole("button", { name: "Create & Send Invitation" }));
    expect(await screen.findByText(/Account created, but invitation delivery failed/)).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("setup-staff-password?uid=");
  });

  test("renders a three-dot menu with only state-valid actions", async () => {
    renderUsers();
    await screen.findByText("fleet.manager");
    expect(screen.getByRole("button", { name: "Actions for fleet.manager" })).toBeInTheDocument();
    openActions("fleet.manager");
    expect(screen.getByRole("menuitem", { name: "View Details" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Change Role" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Resend Invitation" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Deactivate" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Activate" })).not.toBeInTheDocument();
    openActions("dispatcher");
    expect(screen.getByRole("menuitem", { name: "Activate" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Deactivate" })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Resend Invitation" })).not.toBeInTheDocument();
  });

  test("shows real ready-account details without exposing password material", async () => {
    renderUsers();
    await screen.findByText("dispatcher");
    openActions("dispatcher");
    fireEvent.click(screen.getByRole("menuitem", { name: "View Details" }));
    const dialog = screen.getByRole("dialog", { name: "User Details" });
    expect(dialog).toHaveTextContent("Dispatch User");
    expect(dialog).toHaveTextContent("dispatch@example.com");
    expect(dialog).toHaveTextContent("Dispatcher");
    expect(dialog).toHaveTextContent("Inactive");
    expect(dialog).toHaveTextContent("Ready");
    expect(dialog).toHaveTextContent("Password configured");
    expect(dialog).toHaveTextContent("Passwords are securely stored and cannot be viewed.");
    expect(dialog).toHaveTextContent("Password reset is not yet available from Staff Management.");
    expect(dialog).not.toHaveTextContent(/hash|safe-token|setup-staff-password\?uid=/i);
  });

  test("shows the secure pending-account password and invitation state", async () => {
    renderUsers();
    await screen.findByText("fleet.manager");
    openActions("fleet.manager");
    fireEvent.click(screen.getByRole("menuitem", { name: "View Details" }));
    const dialog = screen.getByRole("dialog", { name: "User Details" });
    expect(dialog).toHaveTextContent("Password not set yet");
    expect(dialog).toHaveTextContent("complete the secure account setup invitation");
  });

  test("changes between managed roles only and requires explicit save", async () => {
    mocks.updateStaffRole.mockResolvedValue({ ...pendingUser, role: "DISPATCHER" });
    renderUsers();
    await screen.findByText("fleet.manager");
    openActions("fleet.manager");
    fireEvent.click(screen.getByRole("menuitem", { name: "Change Role" }));
    const role = screen.getByLabelText("New role for fleet.manager");
    expect(within(role).getAllByRole("option").map((option) => option.textContent)).toEqual(["Fleet Manager", "Dispatcher", "Fleet Staff"]);
    fireEvent.change(role, { target: { value: "DISPATCHER" } });
    expect(mocks.updateStaffRole).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Save Role" }));
    await waitFor(() => expect(mocks.updateStaffRole).toHaveBeenCalledWith(1, "DISPATCHER"));
  });

  test("automatically dismisses action feedback after ten seconds", async () => {
    mocks.resendStaffInvitation.mockResolvedValue({ invitation_delivery: "SENT" });
    renderUsers();
    await screen.findByText("fleet.manager");
    vi.useFakeTimers();
    openActions("fleet.manager");
    fireEvent.click(screen.getByRole("menuitem", { name: "Resend Invitation" }));
    await act(async () => Promise.resolve());
    expect(screen.getByRole("status")).toHaveTextContent("Setup invitation sent.");
    act(() => vi.advanceTimersByTime(9_999));
    expect(screen.getByRole("status")).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(1));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    vi.useRealTimers();
  });

  test("deactivates after confirmation, activates directly, and resends pending invitations", async () => {
    mocks.updateStaffStatus
      .mockResolvedValueOnce({ ...pendingUser, is_active: false })
      .mockResolvedValueOnce({ ...readyUser, is_active: true });
    mocks.resendStaffInvitation.mockResolvedValue({ invitation_delivery: "SENT" });
    renderUsers();
    await screen.findByText("fleet.manager");
    openActions("fleet.manager");
    fireEvent.click(screen.getByRole("menuitem", { name: "Resend Invitation" }));
    await waitFor(() => expect(mocks.resendStaffInvitation).toHaveBeenCalledWith(1));
    expect(screen.getByRole("status")).toHaveTextContent("Setup invitation sent.");
    openActions("fleet.manager");
    fireEvent.click(screen.getByRole("menuitem", { name: "Deactivate" }));
    expect(screen.getByText(/Already-issued sessions/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    await waitFor(() => expect(mocks.updateStaffStatus).toHaveBeenCalledWith(1, false));
    expect(screen.getByLabelText("Staff account summary")).toHaveTextContent("Active0Inactive2");
    openActions("dispatcher");
    fireEvent.click(screen.getByRole("menuitem", { name: "Activate" }));
    await waitFor(() => expect(mocks.updateStaffStatus).toHaveBeenCalledWith(2, true));
    expect(screen.getByLabelText("Staff account summary")).toHaveTextContent("Active1Inactive1");
  });

  test("denies non-Fleet-Admins without loading management data", () => {
    mocks.role = "FLEET_MANAGER";
    renderUsers();
    expect(screen.getByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add User" })).not.toBeInTheDocument();
    expect(mocks.listStaff).not.toHaveBeenCalled();
  });

  test("shows a controlled API error and retry action", async () => {
    mocks.listStaff.mockRejectedValue(new Error("network details"));
    renderUsers();
    expect(await screen.findByRole("alert")).toHaveTextContent("The request could not be completed");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
