import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getCalendar } from "../api";
import type { CalendarResponse } from "../types";

type Mode = "daily" | "weekly";
const dateKey = (value: Date) => {
  const year = value.getFullYear(); const month = String(value.getMonth() + 1).padStart(2, "0"); const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};
const addDays = (value: Date, days: number) => { const next = new Date(value); next.setDate(next.getDate() + days); return next; };
const weekStart = (value: Date) => { const next = new Date(value); const day = next.getDay() || 7; next.setDate(next.getDate() - day + 1); next.setHours(0, 0, 0, 0); return next; };
const label = (value: string) => value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, character => character.toUpperCase());

export default function CalendarView({ refreshVersion = 0 }: { refreshVersion?: number }) {
  const [mode, setMode] = useState<Mode>("weekly"); const [anchor, setAnchor] = useState(() => new Date());
  const [data, setData] = useState<CalendarResponse | null>(null); const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const days = useMemo(() => {
    const start = mode === "daily" ? new Date(anchor) : weekStart(anchor);
    return Array.from({ length: mode === "daily" ? 1 : 7 }, (_, index) => addDays(start, index));
  }, [anchor, mode]);
  const start = dateKey(days[0]); const end = dateKey(days.at(-1)!);
  useEffect(() => { const controller = new AbortController(); getCalendar(start, end, controller.signal).then(result => { setData(result); setState("ready"); }).catch((error: unknown) => { if (!(error instanceof DOMException && error.name === "AbortError")) setState("error"); }); return () => controller.abort(); }, [start, end, refreshVersion]);
  const move = (amount: number) => { setState("loading"); setAnchor(value => addDays(value, amount * (mode === "daily" ? 1 : 7))); };
  const changeMode = (next: Mode) => { setState("loading"); setMode(next); };
  const rangeLabel = mode === "daily" ? days[0].toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" }) : `${days[0].toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${days.at(-1)!.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`;
  return <section className="schedule-calendar" aria-label="Transport request calendar"><header className="calendar-header"><div><strong>Vehicle Schedule</strong><span>{rangeLabel}</span></div><div className="calendar-actions"><div className="view-toggle" aria-label="Calendar view"><button aria-pressed={mode === "daily"} onClick={() => changeMode("daily")}>Daily</button><button aria-pressed={mode === "weekly"} onClick={() => changeMode("weekly")}>Weekly</button></div><button onClick={() => move(-1)} aria-label="Previous period">‹</button><button onClick={() => { setState("loading"); setAnchor(new Date()); }}>Today</button><button onClick={() => move(1)} aria-label="Next period">›</button></div></header>
    <div className={`calendar-scroll-region calendar-scroll-region--${mode}`} data-testid="calendar-scroll-region" role="region" aria-label="Calendar schedule grid">
    {state === "loading" && <div className="calendar-state">Loading scheduled requests…</div>}{state === "error" && <div className="calendar-state calendar-state--error" role="alert">Unable to load the calendar range.</div>}
    {state === "ready" && data?.results.length === 0 && <div className="calendar-state">No requests are scheduled in this period.</div>}
    {state === "ready" && data && data.results.length > 0 && <div className={`calendar-grid calendar-grid--${mode}`}>{days.map(day => { const items = data.results.filter(item => item.calendar_date === dateKey(day)); return <section key={dateKey(day)}><h3><span>{day.toLocaleDateString(undefined, { weekday: "short" })}</span>{day.toLocaleDateString(undefined, { month: "short", day: "numeric" })}</h3><div className="calendar-day">{items.length === 0 ? <small className="calendar-empty">No requests</small> : items.map(item => <Link className={`calendar-event calendar-event--${item.priority.toLowerCase()}`} to={`/transport-requests/${item.id}`} key={item.id}><time>{new Date(item.scheduled_pickup_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", timeZone: data.timezone })}–{new Date(item.planning_end_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", timeZone: data.timezone })}</time><strong>{item.request_number}</strong><span>{label(item.request_type)}</span><small>{item.assigned_vehicle?.display_name ?? "Unassigned"}</small><span className={`badge badge--${item.status.toLowerCase()}`}>{label(item.status)}</span>{item.vehicle_conflict && <span className="conflict-badge" title={`Conflicts with ${item.conflicting_requests.join(", ")}`}>Vehicle conflict</span>}</Link>)}</div></section>; })}</div>}
    </div>
  </section>;
}
