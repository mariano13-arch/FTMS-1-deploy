import { AlertTriangle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import DashboardChartCard, { type ChartKind } from "./DashboardChartCard";
import DashboardDetailDrawer from "./DashboardDetailDrawer";
import { getDashboardSummary, type DashboardSummary, type DashboardWidget } from "./api";
import "./DashboardPage.css";

type WidgetKey = Exclude<keyof DashboardSummary, "generated_at" | "sos_activity"> | "sos_activity";
const cards: Array<{ key: Exclude<WidgetKey, "sos_activity">; title: string; kind: ChartKind; empty: string }> = [
  { key: "request_status", title: "Transport Request Status", kind: "donut", empty: "No transport requests" },
  { key: "dispatch_queue", title: "Dispatch Queue", kind: "horizontal", empty: "Dispatch queue is clear" },
  { key: "trip_status", title: "Active Trip Status", kind: "donut", empty: "No active assignments" },
  { key: "completed_trips", title: "Completed Trips", kind: "line", empty: "No completed trips in the last 7 days" },
  { key: "fleet_state", title: "Fleet State", kind: "bar", empty: "No registered vehicles" },
  { key: "driver_state", title: "Driver State", kind: "bar", empty: "No driver records" },
  { key: "inspection_results", title: "Inspection Results", kind: "donut", empty: "No inspections recorded today" },
  { key: "maintenance_activity", title: "Maintenance Activity", kind: "bar", empty: "No current maintenance activity" },
  { key: "safety_events", title: "Operational Safety Events", kind: "horizontal", empty: "No operational safety events today" },
  { key: "geofence_activity", title: "Geofence Activity", kind: "bar", empty: "No geofence activity today" },
  { key: "device_telemetry", title: "Device / Telemetry Coverage", kind: "horizontal", empty: "No registered devices" },
  { key: "fuel_evidence", title: "Fuel Evidence Coverage", kind: "donut", empty: "No eligible fuel evidence" },
];

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [selected, setSelected] = useState<WidgetKey | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async (signal?: AbortSignal) => {
    setError("");
    try { setSummary(await getDashboardSummary(signal)); }
    catch (reason) { if (!(reason instanceof DOMException && reason.name === "AbortError")) setError("Unable to load the operational dashboard."); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    const timer = window.setInterval(() => { if (document.visibilityState === "visible") void load(); }, 30_000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [load]);
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setSelected(null); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);

  const selectedTitle = selected === "sos_activity" ? "Active SOS" : cards.find(card => card.key === selected)?.title;
  const selectedWidget = summary && selected ? summary[selected] as DashboardWidget : null;
  return <main className={`dashboard-page${selectedWidget ? " drawer-open" : ""}`}>
    <header className="dashboard-toolbar"><div><h1>Dashboard</h1><span>{summary ? `Last updated ${new Date(summary.generated_at).toLocaleString()}` : "Operational fleet overview"}</span></div></header>
    {summary && summary.sos_activity.total > 0 && <button type="button" className="dashboard-sos" onClick={() => setSelected("sos_activity")}><AlertTriangle /><strong>Active SOS: {summary.sos_activity.total}</strong><span>Open emergency details</span></button>}
    <div className="dashboard-workspace">
      <div className="dashboard-main">
      {loading && !summary && <div className="dashboard-loading" aria-label="Loading dashboard">{Array.from({ length: 12 }, (_, index) => <i key={index} />)}</div>}
      {error && !summary && <section className="dashboard-error" role="alert"><strong>{error}</strong><button type="button" onClick={() => { setLoading(true); void load(); }}>Retry</button></section>}
      {summary && <section className="dashboard-chart-grid" aria-label="Operational analytics charts">{cards.map(card => <DashboardChartCard key={card.key} title={card.title} kind={card.kind} emptyMessage={card.empty} widget={summary[card.key]} selected={selected === card.key} onSelect={() => setSelected(card.key)} />)}</section>}
      </div>
      {selectedWidget && selectedTitle && <DashboardDetailDrawer title={selectedTitle} widget={selectedWidget} onClose={() => setSelected(null)} />}
    </div>
  </main>;
}
