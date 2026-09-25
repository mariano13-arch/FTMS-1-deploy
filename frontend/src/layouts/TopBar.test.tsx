import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryHistory } from "history";
import { Router } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import TopBar from "./TopBar";

const mocks = vi.hoisted(() => ({
  role: "FLEET_ADMIN" as "FLEET_ADMIN" | "FLEET_MANAGER" | "DISPATCHER",
  signOut: vi.fn(),
  getNotifications: vi.fn(),
  getUnreadNotificationCount: vi.fn(),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
}));

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: 1, username: "root", display_name: "Aljohn Mariano", role: mocks.role },
    signOut: mocks.signOut,
  }),
}));
vi.mock("../services/notifications", () => ({
  getNotifications: mocks.getNotifications,
  getUnreadNotificationCount: mocks.getUnreadNotificationCount,
  markNotificationRead: mocks.markNotificationRead,
  markAllNotificationsRead: mocks.markAllNotificationsRead,
}));

const notification = {
  id: 7,
  notification_type: "SOS_ACTIVE",
  title: "Emergency SOS Active",
  message: "An emergency SOS was activated for Guest Van.",
  target_url: "/alerts",
  is_read: false,
  read_at: null,
  created_at: new Date().toISOString(),
};

function renderTopBar() {
  const history = createMemoryHistory({ initialEntries: ["/dashboard"] });
  return {
    history,
    ...render(<Router history={history}><TopBar sidebarOpen={false} toggleSidebar={vi.fn()} /></Router>),
  };
}

beforeEach(() => {
  mocks.role = "FLEET_ADMIN";
  mocks.signOut.mockReset();
  mocks.getNotifications.mockReset();
  mocks.getUnreadNotificationCount.mockReset();
  mocks.markNotificationRead.mockReset();
  mocks.markAllNotificationsRead.mockReset();
  mocks.getNotifications.mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
  mocks.getUnreadNotificationCount.mockResolvedValue({ unread_count: 0 });
  mocks.markNotificationRead.mockResolvedValue({ ...notification, is_read: true });
  mocks.markAllNotificationsRead.mockResolvedValue({ updated: 1 });
});

test("shows the Fleet Admin display label for a FLEET_ADMIN session", () => {
  renderTopBar();
  expect(screen.getByText(/ · \d{1,2}:\d{2}/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Refresh" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Help" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "User profile" }));
  expect(screen.getByText("Fleet Admin")).toBeInTheDocument();
  expect(screen.queryByText(mocks.role)).not.toBeInTheDocument();
});

test.each([
  ["FLEET_MANAGER", "Fleet Manager"],
  ["DISPATCHER", "Dispatcher"],
] as const)("keeps the %s display label as %s", (role, label) => {
  mocks.role = role;
  renderTopBar();
  fireEvent.click(screen.getByRole("button", { name: "User profile" }));
  expect(screen.getByText(label)).toBeInTheDocument();
});

test("renders the bell and hides a zero unread badge", async () => {
  renderTopBar();
  expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
  await waitFor(() => expect(mocks.getUnreadNotificationCount).toHaveBeenCalled());
  expect(screen.queryByLabelText(/unread notifications/)).not.toBeInTheDocument();
});

test("opens the notification center with unread styling and badge", async () => {
  mocks.getNotifications.mockResolvedValue({ count: 1, next: null, previous: null, results: [notification] });
  mocks.getUnreadNotificationCount.mockResolvedValue({ unread_count: 1 });
  renderTopBar();
  fireEvent.click(screen.getByRole("button", { name: "Notifications" }));
  expect(await screen.findByText("Emergency SOS Active")).toBeInTheDocument();
  expect(screen.getByLabelText("1 unread notifications")).toBeInTheDocument();
  expect(screen.getByText("Emergency SOS Active").closest("button")).toHaveClass("notification-item--unread");
});

test("marks one notification read and navigates to its guarded route", async () => {
  mocks.getNotifications.mockResolvedValue({ count: 1, next: null, previous: null, results: [notification] });
  mocks.getUnreadNotificationCount.mockResolvedValue({ unread_count: 1 });
  const { history } = renderTopBar();
  fireEvent.click(screen.getByRole("button", { name: "Notifications" }));
  fireEvent.click(await screen.findByText("Emergency SOS Active"));
  await waitFor(() => expect(mocks.markNotificationRead).toHaveBeenCalledWith(7));
  expect(history.location.pathname).toBe("/alerts");
});

test("marks all notifications read and refreshes the center", async () => {
  mocks.getNotifications.mockResolvedValue({ count: 1, next: null, previous: null, results: [notification] });
  mocks.getUnreadNotificationCount.mockResolvedValue({ unread_count: 1 });
  renderTopBar();
  fireEvent.click(screen.getByRole("button", { name: "Notifications" }));
  fireEvent.click(await screen.findByRole("button", { name: "Mark all as read" }));
  await waitFor(() => expect(mocks.markAllNotificationsRead).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(mocks.getNotifications.mock.calls.length).toBeGreaterThan(1));
});

test("shows the empty notification state", async () => {
  renderTopBar();
  fireEvent.click(screen.getByRole("button", { name: "Notifications" }));
  expect(await screen.findByText("No notifications yet.")).toBeInTheDocument();
});

test("creates one 30-second notification poll and cleans it up", () => {
  const interval = vi.spyOn(window, "setInterval");
  const clearInterval = vi.spyOn(window, "clearInterval");
  const { unmount } = renderTopBar();
  const pollCalls = interval.mock.calls
    .map((call, index) => ({ call, result: interval.mock.results[index]?.value }))
    .filter(({ call }) => call[1] === 30_000);
  expect(pollCalls).toHaveLength(1);
  unmount();
  expect(clearInterval).toHaveBeenCalledWith(pollCalls[0].result);
});
