import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getCalendar } from "../api";
import type { CalendarRequest, CalendarResponse } from "../types";
import { PriorityChip, WorkflowStatusBadge } from "./RequestIndicators";
import { humanize as label } from "../../../utils/text";
import LoadingIndicator from "../../../components/common/LoadingIndicator";
import { X } from "lucide-react";

type Mode = "daily" | "weekly" | "monthly";
const MANILA_TIME_ZONE = "Asia/Manila";
const manilaDateKey = (value: Date) => {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: MANILA_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(value);
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
};
const dateKey = (value: Date) => {
  const y = value.getFullYear();
  const m = String(value.getMonth() + 1).padStart(2, "0");
  const d = String(value.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
};
const addDays = (value: Date, days: number) => {
  const next = new Date(value);
  next.setDate(next.getDate() + days);
  return next;
};
const weekStart = (value: Date) => {
  const next = new Date(value);
  const day = next.getDay() || 7;
  next.setDate(next.getDate() - day + 1);
  next.setHours(0, 0, 0, 0);
  return next;
};
const monthGrid = (anchor: Date): Date[] => {
  const firstOfMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  const lastOfMonth = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
  const dayOfWeek = firstOfMonth.getDay() || 7;
  const gridStart = addDays(firstOfMonth, -(dayOfWeek - 1));
  const rowCount = Math.ceil((dayOfWeek - 1 + lastOfMonth.getDate()) / 7);
  return Array.from({ length: rowCount * 7 }, (_, i) => addDays(gridStart, i));
};
const monthFetchRange = (anchor: Date): { start: string; end: string } => {
  const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  const last = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
  return { start: dateKey(first), end: dateKey(last) };
};
const todayKey = manilaDateKey(new Date());
const isWeekend = (d: Date) => d.getDay() === 0 || d.getDay() === 6;
const priorityDot: Record<string, string> = {
  low: "#8b9a7b",
  normal: "#788ba1",
  high: "#c99a3e",
  urgent: "#a8312c",
};

export default function CalendarView({
  onViewRequest,
}: {
  onViewRequest?: (requestId: string) => void;
}) {
  const [mode, setMode] = useState<Mode>("monthly");
  const [anchor, setAnchor] = useState(() => new Date());
  const [data, setData] = useState<CalendarResponse | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [panelKey, setPanelKey] = useState(0);
  const fetchIdRef = useRef(0);
  const [lastFetchedRange, setLastFetchedRange] = useState({
    start: "",
    end: "",
  });
  const dismissPanel = () => setSelectedDay(null);

  const days = useMemo(() => {
    if (mode === "monthly") return monthGrid(anchor);
    const start = mode === "daily" ? new Date(anchor) : weekStart(anchor);
    return Array.from({ length: mode === "daily" ? 1 : 7 }, (_, i) =>
      addDays(start, i),
    );
  }, [anchor, mode]);

  const fetchRange = useMemo(() => {
    if (mode === "monthly") return monthFetchRange(anchor);
    return { start: dateKey(days[0]), end: dateKey(days.at(-1)!) };
  }, [anchor, mode, days]);

  const { start, end } = fetchRange;

  const state: "loading" | "ready" | "error" = loadError
    ? "error"
    : data === null ||
        lastFetchedRange.start !== start ||
        lastFetchedRange.end !== end
      ? "loading"
      : "ready";

  useEffect(() => {
    const id = ++fetchIdRef.current;
    const controller = new AbortController();
    getCalendar(start, end, controller.signal)
      .then((result) => {
        if (id !== fetchIdRef.current) return;
        setData(result);
        setLoadError(false);
        setLastFetchedRange({ start, end });
      })
      .catch((error: unknown) => {
        if (id !== fetchIdRef.current) return;
        if (!(error instanceof DOMException && error.name === "AbortError"))
          setLoadError(true);
      });
    return () => controller.abort();
  }, [start, end]);

  const navigateTo = useCallback(
    (target: Date) => {
      const nextKey = dateKey(target);
      const curKey = dateKey(anchor);
      setAnchor(target);
      if (nextKey !== curKey) {
        setSelectedDay(null);
      }
    },
    [anchor],
  );

  const move = (amount: number) => {
    const step = mode === "daily" ? 1 : mode === "monthly" ? 0 : 7;
    navigateTo(
      addDays(
        anchor,
        amount * step ||
          (mode === "monthly" ? (amount > 0 ? 1 : -1) * 32 : amount),
      ),
    );
  };

  const moveMonth = (amount: number) => {
    const next = new Date(anchor);
    const focusedDay = next.getDate();
    next.setDate(1);
    next.setMonth(next.getMonth() + amount);
    const lastDay = new Date(next.getFullYear(), next.getMonth() + 1, 0).getDate();
    next.setDate(Math.min(focusedDay, lastDay));
    navigateTo(next);
  };

  const changeMode = (next: Mode) => {
    setMode(next);
    setSelectedDay(null);
  };

  const selectDay = (key: string) => {
    setSelectedDay((prev) => (prev === key ? null : key));
    setPanelKey((k) => k + 1);
  };

  const rangeLabel = useMemo(() => {
    if (mode === "daily")
      return days[0].toLocaleDateString(undefined, {
        timeZone: MANILA_TIME_ZONE,
        weekday: "long",
        month: "long",
        day: "numeric",
        year: "numeric",
      });
    if (mode === "monthly")
      return anchor.toLocaleDateString(undefined, {
        timeZone: MANILA_TIME_ZONE,
        month: "long",
        year: "numeric",
      });
    return `${days[0].toLocaleDateString(undefined, { timeZone: MANILA_TIME_ZONE, month: "short", day: "numeric" })} – ${days.at(-1)!.toLocaleDateString(undefined, { timeZone: MANILA_TIME_ZONE, month: "short", day: "numeric", year: "numeric" })}`;
  }, [mode, days, anchor]);

  const dayItems = useCallback(
    (key: string) =>
      data?.results
        .filter(
          (request) =>
            request.calendar_date === key &&
            Number.isFinite(Date.parse(request.scheduled_pickup_at)),
        )
        .sort(
          (left, right) =>
            Date.parse(left.scheduled_pickup_at) -
            Date.parse(right.scheduled_pickup_at),
        ) ?? [],
    [data],
  );

  const dailyAutoSelect = mode === "daily" && days[0] ? dateKey(days[0]) : null;
  const showPanel = mode === "daily" ? dailyAutoSelect : selectedDay;
  const panelItems = showPanel ? dayItems(showPanel) : [];
  const currentMonth = anchor.getMonth();
  const isOutsideMonth = (d: Date) => d.getMonth() !== currentMonth;

  return (
    <section
      className="schedule-calendar"
      aria-label="Transport request calendar"
    >
      <header className="calendar-header d-flex align-items-center justify-content-between flex-wrap">
        <div>
          <strong>Vehicle Schedule</strong>
          <span>{rangeLabel}</span>
        </div>
        <div className="calendar-actions d-flex align-items-center gap-2">
          <div className="view-toggle btn-group" aria-label="Calendar view">
            {(["daily", "weekly", "monthly"] as const).map((m) => (
              <button
                className={`btn btn-sm ${mode === m ? " is-selected" : ""}`}
                aria-pressed={mode === m}
                onClick={() => changeMode(m)}
                key={m}
              >
                {m === "daily"
                  ? "Daily"
                  : m === "weekly"
                    ? "Weekly"
                    : "Monthly"}
              </button>
            ))}
          </div>
          <div className="calendar-nav-group d-flex align-items-center gap-1">
            <button
              className="btn-filter"
              onClick={() => (mode === "monthly" ? moveMonth(-1) : move(-1))}
              aria-label="Previous period"
            >
              ‹
            </button>
            <button
              className="btn-filter"
              onClick={() => {
                navigateTo(new Date());
                setSelectedDay(null);
              }}
            >
              Today
            </button>
            <button
              className="btn-filter"
              onClick={() => (mode === "monthly" ? moveMonth(1) : move(1))}
              aria-label="Next period"
            >
              ›
            </button>
          </div>
        </div>
      </header>

      {mode !== "daily" && (
        <div
          className={`calendar-scroll-region calendar-scroll-region--${mode}`}
          data-testid="calendar-scroll-region"
          role="region"
          aria-label="Calendar schedule grid"
        >
          {state === "loading" && (
            <div className="calendar-state">
              <LoadingIndicator
                variant="card"
                message="Loading scheduled requests…"
              />
            </div>
          )}
          {state === "error" && (
            <div className="calendar-state calendar-state--error" role="alert">
              Unable to load the calendar range.
            </div>
          )}
          {state === "ready" && data?.results.length === 0 && (
            <p className="calendar-period-empty">
              No scheduled requests this {mode === "monthly" ? "month" : "week"}.
            </p>
          )}
          {mode === "weekly" &&
            state === "ready" &&
            data && (
              <div className="calendar-week-cols">
                {days.map((day) => {
                  const key = dateKey(day);
                  const items = dayItems(key);
                  const today = key === todayKey;
                  const cls = ["calendar-week-col"];
                  if (today) cls.push("calendar-week-col--today");
                  return (
                    <div className={cls.join(" ")} key={key}>
                      <div className="calendar-week-col-scroll">
                        <div className="calendar-week-col-header">
                          <span className="calendar-week-col-dayname">
                            {day
                              .toLocaleDateString(undefined, {
                                timeZone: MANILA_TIME_ZONE,
                                weekday: "long",
                              })
                              .toUpperCase()}
                          </span>
                          <span className="calendar-week-col-date">
                            {day.getDate()}
                          </span>
                        </div>
                        <div className="calendar-week-col-body">
                          {items.length === 0 ? (
                            <p className="calendar-week-col-empty">
                              No requests
                            </p>
                          ) : (
                            items.map((item) => (
                              <ScheduleRowCompact
                                item={item}
                                timeZone={data.timezone}
                                onViewRequest={onViewRequest}
                                key={item.id}
                              />
                            ))
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          {mode === "monthly" &&
            state === "ready" &&
            data && (
              <div className={`calendar-grid calendar-grid--${mode}`}>
                {mode === "monthly" && (
                  <div className="calendar-grid-weekdays" role="row">
                    {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map(
                      (d) => (
                        <span className="calendar-weekday-label" key={d}>
                          {d}
                        </span>
                      ),
                    )}
                  </div>
                )}
                {days.map((day) => {
                  const key = dateKey(day);
                  const items = dayItems(key);
                  const today = key === todayKey;
                  const weekend = isWeekend(day);
                  const selected = key === showPanel;
                  const outside = mode === "monthly" && isOutsideMonth(day);
                  const cls = ["calendar-cell"];
                  if (today) cls.push("calendar-cell--today");
                  if (weekend) cls.push("calendar-cell--weekend");
                  if (selected) cls.push("calendar-cell--selected");
                  if (outside) cls.push("calendar-cell--outside");
                  const priorities = [
                    ...new Set(items.map((i) => i.priority.toLowerCase())),
                  ];
                  return (
                    <div
                      className={cls.join(" ")}
                      key={key}
                      data-date={key}
                    >
                      <button
                        type="button"
                        className="calendar-cell-date-button"
                        onClick={() => selectDay(key)}
                        aria-pressed={selected}
                        aria-label={`View ${key}`}
                      >
                        <span className="calendar-cell-date">{day.getDate()}</span>
                        {items.length > 0 && (
                          <span className="calendar-cell-dots" aria-hidden="true">
                            {priorities.map((p) => (
                              <span
                                className="calendar-cell-dot"
                                style={{ background: priorityDot[p] ?? "#999" }}
                                key={p}
                              />
                            ))}
                          </span>
                        )}
                      </button>
                      <div className="calendar-cell-events">
                        {items.slice(0, 3).map((item) => (
                          <ScheduleRowCompact
                            item={item}
                            timeZone={data.timezone}
                            onViewRequest={onViewRequest}
                            key={item.id}
                          />
                        ))}
                        {items.length > 3 && (
                          <button
                            type="button"
                            className="calendar-cell-more"
                            onClick={() => selectDay(key)}
                          >
                            +{items.length - 3} more
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
        </div>
      )}

      {mode === "daily" && state === "ready" && data && (
        <div className="calendar-day-view" role="region" aria-label="Daily schedule timeline">
          <div className="calendar-schedule-header">
            <h3>
              {days[0].toLocaleDateString(undefined, {
                timeZone: MANILA_TIME_ZONE,
                weekday: "long",
                month: "long",
                day: "numeric",
                year: "numeric",
              })}
            </h3>
            <span className="calendar-schedule-count">
              {panelItems.length} request{panelItems.length !== 1 ? "s" : ""}
            </span>
          </div>
          {panelItems.length === 0 && (
            <p className="calendar-period-empty">No scheduled requests today.</p>
          )}
          <div className="calendar-day-timeline">
            {Array.from({ length: 24 }, (_, hour) => {
              const hourItems = panelItems.filter(
                (item) => Number(new Intl.DateTimeFormat("en-US", {
                  timeZone: data.timezone,
                  hour: "2-digit",
                  hourCycle: "h23",
                }).format(new Date(item.scheduled_pickup_at))) === hour,
              );
              return (
                <div className="calendar-hour-row" key={hour}>
                  <time>{String(hour).padStart(2, "0")}:00</time>
                  <div>
                    {hourItems.map((item) => (
                      <ScheduleRow
                        item={item}
                        timeZone={data.timezone}
                        onViewRequest={onViewRequest}
                        key={item.id}
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {mode === "monthly" && showPanel && state === "ready" && data && (
        <div
          className="calendar-schedule-panel calendar-schedule-panel--fade"
          key={`${panelKey}-${showPanel}`}
        >
          <div className="calendar-schedule-header">
            <h3>
              {(() => {
                const d = new Date(showPanel + "T12:00:00");
                return d.toLocaleDateString(undefined, {
                  timeZone: MANILA_TIME_ZONE,
                  weekday: "long",
                  month: "long",
                  day: "numeric",
                  year: "numeric",
                });
              })()}
            </h3>
            <span className="calendar-schedule-count">
              {panelItems.length} request{panelItems.length !== 1 ? "s" : ""}
            </span>
            <button
              className="calendar-schedule-close"
              onClick={dismissPanel}
              aria-label="Close schedule panel"
            >
              <X size={14} />
            </button>
          </div>
          <div className="calendar-schedule-list">
            {panelItems.length === 0 ? (
              <p className="calendar-schedule-empty">
                No requests scheduled for this day.
              </p>
            ) : (
              panelItems.map((item) => (
                <ScheduleRow
                  item={item}
                  timeZone={data.timezone}
                  onViewRequest={onViewRequest}
                  key={item.id}
                />
              ))
            )}
          </div>
        </div>
      )}

      {mode === "monthly" &&
        !showPanel &&
        state === "ready" &&
        data &&
        data.results.length > 0 && (
          <div className="calendar-schedule-panel calendar-schedule-panel--empty">
            <p className="calendar-schedule-empty">
              Select a day to view its schedule.
            </p>
          </div>
        )}
    </section>
  );
}

function ScheduleRow({
  item,
  timeZone,
  onViewRequest,
}: {
  item: CalendarRequest;
  timeZone: string;
  onViewRequest?: (requestId: string) => void;
}) {
  return (
    <button className="schedule-row" type="button" onClick={() => onViewRequest?.(item.id)}>
      <span className="schedule-row-time">
        {new Date(item.scheduled_pickup_at).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
          timeZone,
        })}
        –
        {new Date(item.planning_end_at).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
          timeZone,
        })}
      </span>
      <span className="schedule-row-details">
        <strong>{item.request_number}</strong>
        <span className="schedule-row-type">{label(item.request_type)}</span>
        <span className="schedule-row-vehicle">
          {item.assigned_vehicle?.display_name ?? "Unassigned"}
        </span>
      </span>
      <span className="schedule-row-badges">
        <PriorityChip value={item.priority} />
        <WorkflowStatusBadge value={item.status} />
        {item.vehicle_conflict && (
          <span
            className="conflict-badge"
            title={`Conflicts with ${item.conflicting_requests.join(", ")}`}
          >
            Conflict
          </span>
        )}
      </span>
    </button>
  );
}

function ScheduleRowCompact({
  item,
  timeZone,
  onViewRequest,
}: {
  item: CalendarRequest;
  timeZone: string;
  onViewRequest?: (requestId: string) => void;
}) {
  return (
    <button
      className="schedule-row-compact"
      type="button"
      onClick={() => onViewRequest?.(item.id)}
    >
      <span className="schedule-row-compact-time">
        {new Date(item.scheduled_pickup_at).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
          timeZone,
        })}
      </span>
      <div className="schedule-row-compact-top">
        <span className="schedule-row-compact-number">
          {item.request_number}
        </span>
      </div>
      <span className="schedule-row-compact-route">
        {item.pickup_name} → {item.destination_name}
      </span>
      <span className="schedule-row-compact-status">{label(item.status)}</span>
    </button>
  );
}
