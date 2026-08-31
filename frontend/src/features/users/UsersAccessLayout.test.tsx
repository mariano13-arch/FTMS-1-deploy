import { fireEvent, render, screen } from "@testing-library/react";
import { createMemoryHistory } from "history";
import { Router } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";
import AuditLogsPage from "./AuditLogsPage";
import UsersAccessLayout from "./UsersAccessLayout";

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { role: "SUPER_ADMIN" } }),
}));

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

  test("renders a truthful Audit Logs placeholder without fabricated activity", () => {
    const history = createMemoryHistory({ initialEntries: ["/users/audit-logs"] });
    render(<Router history={history}><AuditLogsPage /></Router>);
    expect(screen.getByRole("link", { name: "Audit Logs" })).toHaveClass("active");
    expect(screen.getByRole("heading", { name: "Audit Logs" })).toBeInTheDocument();
    expect(screen.getByText("Centralized administrative audit logging is not available yet.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
