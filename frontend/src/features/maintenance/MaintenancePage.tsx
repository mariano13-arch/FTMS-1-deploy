import { useCallback, useEffect, useState, type FormEvent } from "react";
import LoadingIndicator from "../../components/common/LoadingIndicator";
import { useAuth } from "../../contexts/AuthContext";
import { hasCapability } from "../../services/auth";
import { getVehicles, type Vehicle, type VehiclePage } from "../../services/vehicles";
import { createMaintenanceRecord, getMaintenanceRecords, transitionMaintenanceRecord, type MaintenancePage as RecordsPage, type MaintenanceRecord, type MaintenanceStatus } from "./api";
import "./MaintenancePage.css";

const label = (value: string) => value.replaceAll("_", " ");
const active = new Set<MaintenanceStatus>(["OPEN", "SCHEDULED", "IN_PROGRESS"]);

export default function MaintenancePage() {
  const [vehiclesPage, setVehiclesPage] = useState<VehiclePage | null>(null);
  const [recordsPage, setRecordsPage] = useState<RecordsPage | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [tab, setTab] = useState<"overview" | "review">("overview");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const [vehicleId, setVehicleId] = useState("");
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [inspectionId, setInspectionId] = useState("");
  const [schedules, setSchedules] = useState<Record<number, string>>({});
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const query = search.trim() ? `search=${encodeURIComponent(search.trim())}` : "";
      const [vehicles, records] = await Promise.all([getVehicles(query, signal), getMaintenanceRecords(filter, signal)]);
      setVehiclesPage(vehicles); setRecordsPage(records);
      setVehicleId(current => current || vehicles.results[0]?.device_id || "");
      setState("ready");
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      setState("error");
    }
  }, [filter, search]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => void load(controller.signal), 0);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [load]);
  const vehicles = vehiclesPage?.results ?? [];
  const records = recordsPage?.results ?? [];
  const selectedVehicle = vehicles.find(vehicle => vehicle.device_id === vehicleId);

  async function create(event: FormEvent) {
    event.preventDefault(); if (pending) return;
    setPending(true); setMessage("");
    try {
      await createMaintenanceRecord({ vehicle_device_id: vehicleId, title, notes, ...(inspectionId ? { inspection_id: Number(inspectionId) } : {}) });
      setTitle(""); setNotes(""); setInspectionId(""); await load(); setTab("review");
    } catch { setMessage("Maintenance record could not be created."); }
    finally { setPending(false); }
  }

  async function transition(record: MaintenanceRecord, status: MaintenanceStatus) {
    if (pending) return;
    const scheduledAt = schedules[record.id];
    if (status === "SCHEDULED" && !scheduledAt) { setMessage("Choose a scheduled date and time first."); return; }
    setPending(true); setMessage("");
    try {
      await transitionMaintenanceRecord(record.id, { status, ...(status === "SCHEDULED" ? { scheduled_at: new Date(scheduledAt).toISOString() } : {}) });
      await load(); setTab("review");
    } catch { setMessage("Maintenance status could not be updated."); }
    finally { setPending(false); }
  }

  if (state === "loading") return <main className="maintenance-page"><div className="maintenance-card maintenance-state"><LoadingIndicator variant="inline" message="Loading fleet maintenance records…" /></div></main>;
  if (state === "error") return <main className="maintenance-page"><div className="maintenance-card maintenance-state" role="alert"><strong>Fleet maintenance records unavailable</strong><p>Vehicle and maintenance data could not be loaded.</p></div></main>;
  return <main className="maintenance-page">
    <header className="maintenance-header"><div><p className="breadcrumb">Operations / Maintenance &amp; Predictions</p><h1>Maintenance &amp; Predictions</h1></div><span className="maintenance-badge">Human-managed maintenance</span></header>
    <nav className="maintenance-tabs" role="tablist" aria-label="Maintenance views"><button type="button" role="tab" className={tab === "overview" ? "active" : ""} aria-selected={tab === "overview"} onClick={() => setTab("overview")}>Overview</button><button type="button" role="tab" className={tab === "review" ? "active" : ""} aria-selected={tab === "review"} onClick={() => setTab("review")}>Maintenance Review</button><button type="button" role="tab" aria-selected="false" disabled>Predictions</button></nav>
    {message && <div className="maintenance-card maintenance-message" role="alert">{message}</div>}
    {tab === "overview" ? <Overview vehicles={vehicles} vehiclesPage={vehiclesPage} records={records} recordsPage={recordsPage} search={search} setSearch={setSearch} /> : <Review vehicles={vehicles} records={records} recordsPage={recordsPage} filter={filter} setFilter={setFilter} vehicleId={vehicleId} setVehicleId={setVehicleId} selectedVehicle={selectedVehicle} title={title} setTitle={setTitle} notes={notes} setNotes={setNotes} inspectionId={inspectionId} setInspectionId={setInspectionId} schedules={schedules} setSchedules={setSchedules} pending={pending} create={create} transition={transition} />}
  </main>;
}

function Overview({ vehicles, vehiclesPage, records, recordsPage, search, setSearch }: { vehicles: Vehicle[]; vehiclesPage: VehiclePage | null; records: MaintenanceRecord[]; recordsPage: RecordsPage | null; search: string; setSearch: (value: string) => void }) {
  return <><section className="maintenance-grid" aria-label="Maintenance summary"><article className="maintenance-card"><small>Fleet vehicles</small><strong>{vehiclesPage?.count ?? 0}</strong><span>Registered records</span></article><article className="maintenance-card"><small>Active maintenance</small><strong>{records.filter(record => active.has(record.status)).length}</strong><span>Blocks new assignments</span></article><article className="maintenance-card"><small>Maintenance records</small><strong>{recordsPage?.count ?? 0}</strong><span>Authoritative records</span></article><article className="maintenance-card"><small>Maintenance predictions</small><strong>Unavailable</strong><span>Research model not operational</span></article></section><section className="maintenance-card maintenance-table-card"><header className="maintenance-section-header"><h2>Fleet Maintenance Overview</h2><label aria-label="Search vehicles"><input type="search" placeholder="Search vehicles" value={search} onChange={event => setSearch(event.target.value)} /></label></header><div className="maintenance-table-wrap"><table><thead><tr><th>Vehicle</th><th>Plate</th><th>Status</th><th>Latest Inspection</th></tr></thead><tbody>{vehicles.map(vehicle => <tr key={vehicle.device_id}><td><strong>{vehicle.display_name}</strong><small>{vehicle.device_id}</small></td><td>{vehicle.plate_number || "Not recorded"}</td><td>{vehicle.is_active ? "Active" : "Inactive"}</td><td>{vehicle.latest_inspection ? label(vehicle.latest_inspection.result) : "No inspection record"}</td></tr>)}</tbody></table></div></section><section className="maintenance-card maintenance-notice"><h2>Prediction availability</h2><p>The XGBoost model remains a research candidate. Maintenance records are human-created and are not presented as ML predictions.</p></section></>;
}

type ReviewProps = { vehicles: Vehicle[]; records: MaintenanceRecord[]; recordsPage: RecordsPage | null; filter: string; setFilter: (value: string) => void; vehicleId: string; setVehicleId: (value: string) => void; selectedVehicle?: Vehicle; title: string; setTitle: (value: string) => void; notes: string; setNotes: (value: string) => void; inspectionId: string; setInspectionId: (value: string) => void; schedules: Record<number, string>; setSchedules: React.Dispatch<React.SetStateAction<Record<number, string>>>; pending: boolean; create: (event: FormEvent) => void; transition: (record: MaintenanceRecord, status: MaintenanceStatus) => void };
function Review(props: ReviewProps) {
  const { user } = useAuth();
  const allowed = (status: MaintenanceStatus) => hasCapability(user, "MAINTENANCE", ({ SCHEDULED:"SCHEDULE", IN_PROGRESS:"START", COMPLETED:"COMPLETE", CANCELLED:"CANCEL", OPEN:"CREATE" } as const)[status]);
  return <>{hasCapability(user, "MAINTENANCE", "CREATE") && <form className="maintenance-card maintenance-form" onSubmit={props.create}><h2>Create Maintenance Record</h2><label>Vehicle<select value={props.vehicleId} onChange={event => { props.setVehicleId(event.target.value); props.setInspectionId(""); }} required>{props.vehicles.map(vehicle => <option key={vehicle.device_id} value={vehicle.device_id}>{vehicle.display_name} · {vehicle.plate_number}</option>)}</select></label><label>Summary<input value={props.title} onChange={event => props.setTitle(event.target.value)} maxLength={160} required /></label><label>Notes<textarea value={props.notes} onChange={event => props.setNotes(event.target.value)} /></label>{props.selectedVehicle?.latest_inspection && <label>Inspection origin<select value={props.inspectionId} onChange={event => props.setInspectionId(event.target.value)}><option value="">Manual</option><option value={props.selectedVehicle.latest_inspection.id}>#{props.selectedVehicle.latest_inspection.id} · {label(props.selectedVehicle.latest_inspection.result)}</option></select></label>}<button type="submit" disabled={props.pending || !props.vehicleId}>{props.pending ? "Creating…" : "Create Open Record"}</button></form>}<section className="maintenance-card maintenance-table-card"><header className="maintenance-section-header"><h2>Maintenance Records</h2><label>Vehicle filter<select value={props.filter} onChange={event => props.setFilter(event.target.value)}><option value="">All vehicles</option>{props.vehicles.map(vehicle => <option key={vehicle.device_id} value={vehicle.device_id}>{vehicle.display_name}</option>)}</select></label></header>{props.records.length === 0 ? <div className="maintenance-empty"><strong>No maintenance records found</strong></div> : <div className="maintenance-records">{props.records.map(record => { const transitions = record.allowed_transitions.filter(allowed); return <article className="maintenance-record" key={record.id}><header><div><strong>{record.title}</strong><small>{record.vehicle.display_name} · {record.vehicle.plate_number}</small></div><span className="maintenance-status">{label(record.status)}</span></header><p>{record.notes || "No details recorded."}</p><small>Created {new Date(record.created_at).toLocaleString()} by {record.created_by_name}</small>{record.scheduled_at && <small>Scheduled {new Date(record.scheduled_at).toLocaleString()}</small>}{record.inspection && <small>Inspection #{record.inspection.id} · {label(record.inspection.result)}</small>}{transitions.length > 0 && <div className="maintenance-actions">{transitions.includes("SCHEDULED") && <input aria-label={`Schedule ${record.title}`} type="datetime-local" value={props.schedules[record.id] ?? ""} onChange={event => props.setSchedules(current => ({ ...current, [record.id]: event.target.value }))} />}{transitions.map(status => <button type="button" disabled={props.pending} key={status} onClick={() => void props.transition(record, status)}>{label(status)}</button>)}</div>}</article>; })}</div>}</section></>;
}
