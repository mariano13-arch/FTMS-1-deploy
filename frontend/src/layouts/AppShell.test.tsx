import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import AppShell from "./AppShell";

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { display_name: "Staff User", role: "DISPATCHER" },
    signOut: vi.fn(),
  }),
}));

const renderShell = () =>
  render(
    <MemoryRouter initialEntries={["/transport-requests"]}>
      <AppShell>
        <div>Route content</div>
      </AppShell>
    </MemoryRouter>,
  );

describe("application sidebar shell", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  test("starts expanded and exposes accessible module routes", () => {
    renderShell();
    const shell = screen.getByText("Route content").closest(".app-layout");
    expect(shell).toHaveAttribute("data-sidebar-collapsed", "false");
    expect(
      screen.getByRole("button", { name: "Collapse sidebar" }),
    ).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByRole("link", { name: "Transport Requests" }),
    ).toHaveAttribute("href", "/transport-requests");
    expect(
      screen.queryByRole("link", { name: "Active Trips" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Dispatch Board" }),
    ).toHaveAttribute("href", "/dispatch-board");
    expect(
      screen.queryByRole("link", { name: "Geofences" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Route History & Replay" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Vehicles & Inspections" })).toHaveAttribute(
      "href",
      "/vehicles",
    );
    expect(screen.getByText("Route content")).toBeInTheDocument();
  });

  test("switches to icon-only mini mode and persists the preference", () => {
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    const shell = screen.getByText("Route content").closest(".app-layout");
    expect(shell).toHaveAttribute("data-sidebar-collapsed", "true");
    expect(
      screen.getByRole("button", { name: "Expand sidebar" }),
    ).toHaveAttribute("aria-expanded", "false");
    const link = screen.getByRole("link", { name: "Transport Requests" });
    expect(link.querySelector(".sidebar-icon")).not.toBeNull();
    expect(link.querySelector(".sidebar-label")).toBeNull();
    expect(window.localStorage.getItem("ftms.sidebar.collapsed")).toBe("true");
    expect(screen.getByText("Route content")).toBeInTheDocument();
  });

  test("restores a stored mini-sidebar preference", () => {
    window.localStorage.setItem("ftms.sidebar.collapsed", "true");
    renderShell();
    expect(
      screen.getByText("Route content").closest(".app-layout"),
    ).toHaveAttribute("data-sidebar-collapsed", "true");
    expect(
      screen.getByRole("button", { name: "Expand sidebar" }),
    ).toBeInTheDocument();
  });

  test("defaults safely when local storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("unavailable");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("unavailable");
    });
    expect(() => renderShell()).not.toThrow();
    expect(
      screen.getByText("Route content").closest(".app-layout"),
    ).toHaveAttribute("data-sidebar-collapsed", "false");
  });

  test("notifies responsive maps after the desktop shell transition", () => {
    vi.useFakeTimers();
    const dispatch = vi.spyOn(window, "dispatchEvent");
    renderShell();
    act(() => vi.runOnlyPendingTimers());
    dispatch.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    act(() => vi.advanceTimersByTime(220));
    expect(dispatch.mock.calls.some(([event]) => event.type === "resize")).toBe(
      true,
    );
  });
});
