import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryHistory } from "history";
import { Router } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";
import AuditLogsPage from "./AuditLogsPage";
import UsersAccessLayout from "./UsersAccessLayout";

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { role: "FLEET_ADMIN" } }),
}));

const { auditMock } = vi.hoisted(() => ({ auditMock: vi.fn() }));

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, listAuditLogs: (...args: unknown[]) => auditMock(...args) };
});

function renderLayout(path: string) {
  const history = createMemoryHistory({ initialEntries: [path] });
  render(<Router history={history}><UsersAccessLayout><div>Selected content</div></UsersAccessLayout></Router>);
  return history;
}

describe("UsersAccessLayout", () => {
  test("marks Staff Users active on /users and navigates through route-based tabs", () => {
    const storage = vi.spyOn(Storage.prototype, "setItem");
    const history = renderLayout("/users");
    expect(screen.getByRole("link", { name: "Staff Users" })).toHaveClass("active");
    fireEvent.click(screen.getByRole("link", { name: "Roles & Permissions" }));
    expect(history.location.pathname).toBe("/users/roles-permissions");
    expect(screen.getByRole("link", { name: "Roles & Permissions" })).toHaveClass("active");
    history.goBack();
    expect(history.location.pathname).toBe("/users");
    expect(storage).not.toHaveBeenCalled();
    storage.mockRestore();
  });

  test("marks Roles & Permissions active from its route", () => {
    renderLayout("/users/roles-permissions");
    expect(screen.getByRole("link", { name: "Roles & Permissions" })).toHaveClass("active");
    expect(screen.getByRole("link", { name: "Staff Users" })).not.toHaveClass("active");
  });

  test("renders Audit Logs table, filters, and details", async () => {
    auditMock.mockResolvedValueOnce({
      count: 1,
      next: null,
      previous: null,
      results: [{
        id: 1,
        occurred_at: "2026-09-25T01:00:00Z",
        actor: 7,
        actor_display: "Fleet Admin",
        actor_type: "STAFF",
        action: "STAFF_ROLE_CHANGED",
        target_type: "User",
        target_id: "9",
        target_label: "dispatcher",
        outcome: "SUCCESS",
        source: "WEB",
        ip_address: "127.0.0.1",
        user_agent: "Vitest",
        changes: { role: { old: "FLEET_STAFF", new: "DISPATCHER" } },
        metadata: {},
      }],
    });
    const history = createMemoryHistory({ initialEntries: ["/users/audit-logs"] });
    render(<Router history={history}><AuditLogsPage /></Router>);
    expect(screen.getByRole("link", { name: "Audit Logs" })).toHaveClass("active");
    expect(screen.getByRole("status")).toHaveTextContent("Loading audit logs");
    const table = await screen.findByRole("table");
    expect(table).toBeInTheDocument();
    expect(within(table).getByText("Staff role changed")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    expect(screen.getByRole("dialog", { name: "Audit log details" })).toBeInTheDocument();
    expect(screen.getByText("FLEET_STAFF -> DISPATCHER")).toBeInTheDocument();
  });

  test("sends filters and clears them", async () => {
    auditMock.mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    const history = createMemoryHistory({ initialEntries: ["/users/audit-logs"] });
    render(<Router history={history}><AuditLogsPage /></Router>);
    await screen.findByText("No audit events recorded yet.");
    fireEvent.change(screen.getByLabelText("Action"), { target: { value: "LOGIN_SUCCESS" } });
    fireEvent.change(screen.getByLabelText("Result"), { target: { value: "SUCCESS" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(auditMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ action: "LOGIN_SUCCESS", outcome: "SUCCESS" }),
      expect.any(AbortSignal),
    ));
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    await waitFor(() => expect(auditMock).toHaveBeenLastCalledWith({}, expect.any(AbortSignal)));
  });
});
