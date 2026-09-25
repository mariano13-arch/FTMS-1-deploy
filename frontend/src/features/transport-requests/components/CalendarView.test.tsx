import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { getCalendar } from "../api";
import type { CalendarRequest, CalendarResponse } from "../types";
import CalendarView from "./CalendarView";

vi.mock("../api", () => ({ getCalendar: vi.fn() }));

const calendarRequest = (overrides: Partial<CalendarRequest> = {}) =>
  ({
    id: "request-1",
    request_number: "TR-20261005-TEST01",
    request_type: "GUEST_TRANSFER",
    request_category: "PASSENGER_TRANSPORT",
    priority: "NORMAL",
    status: "READY_FOR_DISPATCH",
    pickup_name: "Oxford Suites",
    destination_name: "SM Aura",
    scheduled_pickup_at: "2026-10-05T10:00:00Z",
    calendar_date: "2026-10-05",
    planning_end_at: "2026-10-05T11:00:00Z",
    vehicle_conflict: false,
    conflicting_requests: [],
    assigned_vehicle: null,
    ...overrides,
  }) as CalendarRequest;

const response = (start: string, end: string, results: CalendarRequest[]): CalendarResponse => ({
  start,
  end,
  timezone: "Asia/Manila",
  results: results.filter((item) => item.calendar_date >= start && item.calendar_date <= end),
});

describe("Transport Requests Calendar", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2026-09-21T04:00:00Z"));
    vi.mocked(getCalendar).mockImplementation(async (start, end) => response(start, end, []));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  test("always renders monthly, weekly, and daily temporal structures for empty periods", async () => {
    render(<CalendarView />);
    expect(await screen.findByText("No scheduled requests this month.")).toBeInTheDocument();
    expect(document.querySelector(".calendar-grid--monthly")).not.toBeNull();
    expect(document.querySelectorAll(".calendar-cell").length).toBeGreaterThanOrEqual(35);

    fireEvent.click(screen.getByRole("button", { name: "Weekly" }));
    expect(await screen.findByText("No scheduled requests this week.")).toBeInTheDocument();
    expect(document.querySelectorAll(".calendar-week-col")).toHaveLength(7);

    fireEvent.click(screen.getByRole("button", { name: "Daily" }));
    expect(await screen.findByText("No scheduled requests today.")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Daily schedule timeline" })).toBeInTheDocument();
    expect(document.querySelectorAll(".calendar-hour-row")).toHaveLength(24);
  });

  test("navigates by month, week, and day and Today restores the Manila current period", async () => {
    render(<CalendarView />);
    await screen.findByText("September 2026");
    fireEvent.click(screen.getByRole("button", { name: "Next period" }));
    expect(await screen.findByText("October 2026")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Previous period" }));
    expect(await screen.findByText("September 2026")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Weekly" }));
    const initialWeek = screen.getByText(/Sep 21/).textContent;
    fireEvent.click(screen.getByRole("button", { name: "Next period" }));
    await waitFor(() => expect(screen.queryByText(initialWeek ?? "")).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Previous period" }));
    expect(await screen.findByText(initialWeek ?? "")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Daily" }));
    expect(await screen.findByText(/Monday, September 21, 2026/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next period" }));
    expect(await screen.findByText(/Tuesday, September 22, 2026/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Today" }));
    expect(await screen.findByText(/Monday, September 21, 2026/)).toBeInTheDocument();
  });

  test("places real Manila-scheduled requests, limits month chips, shows status, and opens details", async () => {
    const onViewRequest = vi.fn();
    const items = [0, 1, 2, 3].map((index) =>
      calendarRequest({
        id: `request-${index + 1}`,
        request_number: `TR-20261005-TEST0${index + 1}`,
        scheduled_pickup_at: `2026-10-05T${String(8 + index).padStart(2, "0")}:00:00Z`,
      }),
    );
    vi.mocked(getCalendar).mockImplementation(async (start, end) => response(start, end, items));
    render(<CalendarView onViewRequest={onViewRequest} />);
    await screen.findByText("September 2026");
    fireEvent.click(screen.getByRole("button", { name: "Next period" }));
    await screen.findByText("October 2026");

    const day = document.querySelector('[data-date="2026-10-05"]');
    expect(day).not.toBeNull();
    expect(within(day as HTMLElement).getAllByText(/TR-20261005-TEST0/)).toHaveLength(3);
    expect(within(day as HTMLElement).getByText("+1 more")).toBeInTheDocument();
    expect(within(day as HTMLElement).getAllByText("Ready For Dispatch")).toHaveLength(3);
    fireEvent.click(within(day as HTMLElement).getByText("TR-20261005-TEST01"));
    expect(onViewRequest).toHaveBeenCalledWith("request-1");
  });

  test("uses the authoritative Manila calendar date and ignores an invalid scheduled pickup", async () => {
    const valid = calendarRequest({
      id: "manila-midnight",
      request_number: "TR-MANILA-MIDNIGHT",
      scheduled_pickup_at: "2026-09-30T16:30:00Z",
      calendar_date: "2026-10-01",
    });
    const invalid = calendarRequest({
      id: "missing-schedule",
      request_number: "TR-NO-SCHEDULE",
      scheduled_pickup_at: "",
      calendar_date: "2026-10-01",
    });
    vi.mocked(getCalendar).mockImplementation(async (start, end) => response(start, end, [valid, invalid]));
    render(<CalendarView />);
    await screen.findByText("September 2026");
    fireEvent.click(screen.getByRole("button", { name: "Next period" }));
    await waitFor(() =>
      expect(document.querySelector('[data-date="2026-10-01"]')).not.toBeNull(),
    );
    const day = document.querySelector('[data-date="2026-10-01"]');
    expect(within(day as HTMLElement).getByText("TR-MANILA-MIDNIGHT")).toBeInTheDocument();
    expect(within(day as HTMLElement).getByText("12:30 AM")).toBeInTheDocument();
    expect(screen.queryByText("TR-NO-SCHEDULE")).not.toBeInTheDocument();
  });
});
