import { useEffect, useMemo, useState } from "react";
import {
  getAlertGeofenceOptions,
  getAlertVehicleOptions,
  getActiveAttention,
  getGeofenceActivity,
  getSafetyIncidents,
  type AlertSummary,
  type AlertGeofenceOption,
  type AlertVehicleOption,
  type AttentionItem,
  type GeofenceActivity,
  type Page,
  type SafetyIncident,
} from "./api";

type Tab = "attention" | "safety" | "geofence";
type LoadState = "loading" | "ready" | "error";
type Selected = { kind: Tab; item: AttentionItem | SafetyIncident | GeofenceActivity } | null;

const words = (value: unknown) => value === null || value === undefined || value === "" ? "Unavailable" : String(value).toLowerCase().replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase());
const provenance = (value: unknown) => ({ GNSS: "GNSS", CELLULAR_LBS: "CELLULAR LBS", SIMULATED_TEST: "SIMULATED TEST", PHYSICAL_OBD: "PHYSICAL OBD" }[String(value)] ?? words(value));
const dateTime = (value: string | null | undefined) => value ? new Date(value).toLocaleString() : "Unavailable";
const shownRange = (page: number, count: number, length: number) => ({ start: count ? (page - 1) * 15 + 1 : 0, end: count ? (page - 1) * 15 + length : 0 });
const detail = (item: AttentionItem, key: string) => item.details[key];

function useDebouncedValue(value: string, delay = 350) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [delay, value]);
  return debounced;
}

function Pagination({ page, count, length, onPage }: { page: number; count: number; length: number; onPage: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(count / 15));
  const range = shownRange(page, count, length);
  return <footer className="alerts-pagination"><span>Showing {range.start}–{range.end} of {count}</span><div><button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button><span>Page {page} of {pages}</span><button type="button" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button></div></footer>;
}

function DetailValue({ label, value }: { label: string; value: unknown }) {
  const rendered = value === null || value === undefined || value === "" ? "Unavailable" : typeof value === "boolean" ? (value ? "Yes" : "No") : String(value);
  return <div><dt>{label}</dt><dd>{rendered}</dd></div>;
}

function AttentionDetails({ attention }: { attention: AttentionItem }) {
  const checklist = detail(attention, "checklist");
  const linkedInspection = detail(attention, "linked_inspection");
  if (attention.source === "TELEMETRY") return <section><h3>Latest Telemetry</h3>{attention.condition === "NO_TELEMETRY" && <p className="alerts-source-note">No telemetry received.</p>}<dl><DetailValue label="Latest telemetry" value={attention.condition === "NO_TELEMETRY" ? null : dateTime(detail(attention, "latest_telemetry_at") as string | null)} /><DetailValue label="Telemetry age" value={detail(attention, "telemetry_age_seconds") == null ? null : `${detail(attention, "telemetry_age_seconds")} seconds`} /><DetailValue label="Position source" value={detail(attention, "position_source") ? words(String(detail(attention, "position_source"))) : null} /><DetailValue label="Position accuracy" value={detail(attention, "position_accuracy_m") == null ? null : `${detail(attention, "position_accuracy_m")} m`} /><DetailValue label="Coordinates" value={detail(attention, "latitude") == null ? null : `${detail(attention, "latitude")}, ${detail(attention, "longitude")}`} /><DetailValue label="GNSS speed" value={detail(attention, "speed_kph") == null ? null : `${detail(attention, "speed_kph")} km/h`} /><DetailValue label="OBD source" value={detail(attention, "obd_source") ? words(String(detail(attention, "obd_source"))) : null} /></dl>{detail(attention, "position_source") === "SIMULATED_TEST" && <strong className="alerts-provenance">SIMULATED TEST POSITION DATA</strong>}</section>;
  if (attention.source === "INSPECTION") return <><section><h3>Inspection</h3><dl><DetailValue label="Inspection date" value={detail(attention, "inspection_date")} /><DetailValue label="Inspection type" value={words(String(detail(attention, "inspection_type")))} /><DetailValue label="Result" value={words(String(detail(attention, "result")))} /><DetailValue label="Odometer" value={detail(attention, "odometer_km") == null ? null : `${detail(attention, "odometer_km")} km`} /><DetailValue label="Fuel level" value={detail(attention, "fuel_level_percent") == null ? null : `${detail(attention, "fuel_level_percent")}%`} /><DetailValue label="Inspector" value={detail(attention, "inspector")} /><DetailValue label="Issues found" value={detail(attention, "issues_found")} /><DetailValue label="Notes" value={detail(attention, "notes")} /></dl></section>{typeof checklist === "object" && checklist !== null && <section><h3>Checklist</h3><dl>{Object.entries(checklist).map(([key, value]) => <DetailValue key={key} label={words(key)} value={words(String(value))} />)}</dl></section>}</>;
  return <><section><h3>Maintenance</h3><dl><DetailValue label="Title" value={detail(attention, "title")} /><DetailValue label="Status" value={words(String(detail(attention, "status")))} /><DetailValue label="Source" value={words(String(detail(attention, "maintenance_source")))} /><DetailValue label="Scheduled" value={dateTime(detail(attention, "scheduled_at") as string | null)} /><DetailValue label="Started" value={dateTime(detail(attention, "started_at") as string | null)} /><DetailValue label="Completed" value={dateTime(detail(attention, "completed_at") as string | null)} /><DetailValue label="Notes" value={detail(attention, "notes")} /></dl></section>{typeof linkedInspection === "object" && linkedInspection !== null && <section><h3>Linked Inspection</h3><dl>{Object.entries(linkedInspection).map(([key, value]) => <DetailValue key={key} label={words(key)} value={key.includes("date") ? value : words(String(value))} />)}</dl></section>}</>;
}

function DetailsDrawer({ selected, onClose }: { selected: NonNullable<Selected>; onClose: () => void }) {
  const item = selected.item;
  const title = selected.kind === "attention" ? words((item as AttentionItem).condition) : selected.kind === "safety" ? words((item as SafetyIncident).event_type) : (item as GeofenceActivity).is_restricted_entry ? "Restricted Zone Entry" : words((item as GeofenceActivity).event_type);
  const family = selected.kind === "attention" ? "Active Attention" : selected.kind === "safety" ? "Safety Incident" : "Geofence Activity";
  const vehicleName = selected.kind === "attention" ? (item as AttentionItem).vehicle.display_name : (item as SafetyIncident | GeofenceActivity).vehicle_name;
  const timestamp = selected.kind === "attention" ? (item as AttentionItem).last_updated_at : selected.kind === "safety" ? (item as SafetyIncident).recorded_at : (item as GeofenceActivity).occurred_at;
  return <div className="alerts-drawer-backdrop"><aside className="alerts-drawer" role="dialog" aria-modal="true" aria-label="Alert and incident details"><header><div><small>{family}</small><h2>{title}</h2><span>{vehicleName} · {dateTime(timestamp)}</span></div><button type="button" aria-label="Close details" onClick={onClose}>×</button></header><div className="alerts-drawer-body">
    {selected.kind === "safety" && (() => { const event = item as SafetyIncident; return <><section><h3>Safety Incident</h3><dl><DetailValue label="Type" value={words(event.event_type)} /><DetailValue label="Recorded" value={dateTime(event.recorded_at)} /></dl></section><section><h3>Vehicle / Device</h3><dl><DetailValue label="Vehicle" value={`${event.vehicle_name} · ${event.plate_number}`} /><DetailValue label="Vehicle identifier" value={event.vehicle_device_id} /><DetailValue label="Device ID" value={event.device_id} /></dl></section><section><h3>Location</h3><dl><DetailValue label="Coordinates" value={`${event.latitude}, ${event.longitude}`} /><DetailValue label="Position source" value={words(event.position_source)} /><DetailValue label="Accuracy" value={event.position_accuracy_m == null ? null : `${event.position_accuracy_m} m`} /></dl>{event.position_source === "SIMULATED_TEST" && <strong className="alerts-provenance">SIMULATED TEST POSITION DATA</strong>}</section><section><h3>Telemetry Snapshot</h3><dl><DetailValue label="GNSS speed" value={event.speed_kph == null ? null : `${event.speed_kph} km/h`} /><DetailValue label="RPM" value={event.rpm} /><DetailValue label="Coolant" value={event.coolant_c == null ? null : `${event.coolant_c} °C`} /><DetailValue label="Engine load" value={event.engine_load_pct == null ? null : `${event.engine_load_pct}%`} /><DetailValue label="OBD source" value={event.obd_source ? words(event.obd_source) : null} /></dl>{event.obd_source === "SIMULATED_TEST" && <strong className="alerts-provenance">SIMULATED TEST OBD DATA</strong>}</section><section><h3>Source</h3><dl><DetailValue label="Telemetry event ID" value={event.event_id} /><DetailValue label="Recorded at" value={dateTime(event.recorded_at)} /><DetailValue label="Received at" value={dateTime(event.received_at)} /></dl></section></>; })()}
    {selected.kind === "geofence" && (() => { const event = item as GeofenceActivity; return <><section><h3>Event</h3><dl><DetailValue label="Event" value={words(event.event_type)} /><DetailValue label="Occurred" value={dateTime(event.occurred_at)} /><DetailValue label="Created" value={dateTime(event.created_at)} /></dl></section><section><h3>Geofence</h3><dl><DetailValue label="Name" value={event.geofence_name} /><DetailValue label="Category" value={words(event.geofence_category)} /><DetailValue label="Shape" value={words(event.geofence_shape_type)} />{event.geofence_shape_type === "CIRCLE" && <DetailValue label="Radius" value={event.geofence_radius_meters == null ? null : `${event.geofence_radius_meters} m`} />}</dl></section><section><h3>Vehicle</h3><dl><DetailValue label="Vehicle" value={`${event.vehicle_name} · ${event.plate_number}`} /><DetailValue label="Vehicle identifier" value={event.vehicle_id} /><DetailValue label="Device ID" value={event.device_id} /></dl></section><section><h3>Location</h3><dl><DetailValue label="Latitude" value={event.latitude} /><DetailValue label="Longitude" value={event.longitude} /></dl></section><section><h3>Source Telemetry</h3><dl><DetailValue label="Telemetry event ID" value={event.telemetry_event_id} /><DetailValue label="Position source" value={provenance(event.telemetry_position_source)} /><DetailValue label="Recorded" value={dateTime(event.telemetry_recorded_at)} /></dl>{event.telemetry_position_source === "SIMULATED_TEST" && <strong className="alerts-provenance">SIMULATED TEST POSITION DATA</strong>}</section></>; })()}
    {selected.kind === "attention" && (() => { const attention = item as AttentionItem; return <><section><h3>{words(attention.source)}</h3><dl><DetailValue label="Condition" value={words(attention.condition)} /><DetailValue label="Current state" value={words(attention.current_state)} /><DetailValue label="Last updated" value={dateTime(attention.last_updated_at)} /></dl></section><section><h3>Vehicle / Device</h3><dl><DetailValue label="Vehicle" value={`${attention.vehicle.display_name} · ${attention.vehicle.plate_number}`} /><DetailValue label="Device ID" value={attention.vehicle.device_id} /></dl></section><AttentionDetails attention={attention} /></>; })()}
  </div></aside></div>;
}

export default function AlertsPage() {
  const [tab, setTab] = useState<Tab>("attention");
  const [pages, setPages] = useState<Record<Tab, number>>({ attention: 1, safety: 1, geofence: 1 });
  const [source, setSource] = useState(""); const [search, setSearch] = useState(""); const [safetySearch, setSafetySearch] = useState("");
  const [condition, setCondition] = useState(""); const [vehicle, setVehicle] = useState(""); const [geofenceId, setGeofenceId] = useState("");
  const [safetyType, setSafetyType] = useState(""); const [geoEvent, setGeoEvent] = useState(""); const [category, setCategory] = useState("");
  const [dateFrom, setDateFrom] = useState(""); const [dateTo, setDateTo] = useState("");
  const [attention, setAttention] = useState<Page<AttentionItem> | null>(null);
  const [safety, setSafety] = useState<Page<SafetyIncident> | null>(null);
  const [geofence, setGeofence] = useState<Page<GeofenceActivity> | null>(null);
  const [summary, setSummary] = useState<AlertSummary | null>(null);
  const [vehicleOptions, setVehicleOptions] = useState<AlertVehicleOption[]>([]); const [geofenceOptions, setGeofenceOptions] = useState<AlertGeofenceOption[]>([]);
  const [state, setState] = useState<LoadState>("loading"); const [selected, setSelected] = useState<Selected>(null); const [retryKey, setRetryKey] = useState(0); const [filtersOpen, setFiltersOpen] = useState(false);
  const page = pages[tab];
  const debouncedSearch = useDebouncedValue(search); const debouncedSafetySearch = useDebouncedValue(safetySearch);
  const filters = useMemo(() => tab === "attention" ? { page, source: source || undefined, condition: condition || undefined, vehicle: vehicle || undefined, search: debouncedSearch || undefined } : tab === "safety" ? { page, event_type: safetyType || undefined, vehicle: vehicle || undefined, search: debouncedSafetySearch || undefined, date_from: dateFrom || undefined, date_to: dateTo || undefined } : { page, event_type: geoEvent || undefined, category: category || undefined, vehicle: vehicle || undefined, geofence: geofenceId || undefined, date_from: dateFrom || undefined, date_to: dateTo || undefined }, [tab, page, source, condition, vehicle, geofenceId, debouncedSearch, debouncedSafetySearch, safetyType, geoEvent, category, dateFrom, dateTo]);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([getAlertVehicleOptions(controller.signal), getAlertGeofenceOptions(controller.signal)])
      .then(([vehicles, geofences]) => { setVehicleOptions(vehicles.vehicles); setGeofenceOptions(geofences.results); })
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController(); setState("loading");
    const request = tab === "attention" ? getActiveAttention(filters, controller.signal) : tab === "safety" ? getSafetyIncidents(filters, controller.signal) : getGeofenceActivity(filters, controller.signal);
    request.then(response => { if (tab === "attention") { setAttention(response as Awaited<ReturnType<typeof getActiveAttention>>); setSummary((response as Awaited<ReturnType<typeof getActiveAttention>>).summary); } else if (tab === "safety") setSafety(response as Page<SafetyIncident>); else setGeofence(response as Page<GeofenceActivity>); setState("ready"); }).catch(error => { if (!(error instanceof DOMException && error.name === "AbortError")) setState("error"); });
    return () => controller.abort();
  }, [tab, filters, retryKey]);

  useEffect(() => { if (summary) return; const controller = new AbortController(); getActiveAttention({ page: 1 }, controller.signal).then(response => { setSummary(response.summary); setAttention(current => current ?? response); }).catch(() => undefined); return () => controller.abort(); }, [summary]);
  useEffect(() => { if (tab !== "attention") return; const timer = window.setInterval(() => setRetryKey(value => value + 1), 30_000); return () => window.clearInterval(timer); }, [tab]);
  const resetPage = () => setPages(current => ({ ...current, [tab]: 1 }));
  const setCurrentPage = (value: number) => setPages(current => ({ ...current, [tab]: value }));
  const data = tab === "attention" ? attention : tab === "safety" ? safety : geofence;
  const activeFilterCount = tab === "attention" ? [search, source, condition, vehicle].filter(Boolean).length : tab === "safety" ? [safetySearch, safetyType, vehicle, dateFrom, dateTo].filter(Boolean).length : [geoEvent, category, vehicle, geofenceId, dateFrom, dateTo].filter(Boolean).length;
  const clearFilters = () => {
    if (tab === "attention") { setSearch(""); setSource(""); setCondition(""); setVehicle(""); }
    if (tab === "safety") { setSafetySearch(""); setSafetyType(""); setVehicle(""); setDateFrom(""); setDateTo(""); }
    if (tab === "geofence") { setGeoEvent(""); setCategory(""); setVehicle(""); setGeofenceId(""); setDateFrom(""); setDateTo(""); }
    resetPage();
  };

  return <main className="alerts-page"><header className="alerts-header"><small>Operations / Alerts &amp; Incidents</small><h1>Alerts &amp; Incidents</h1></header><section className="alerts-kpis" aria-label="Alerts and incidents summary">{[["Active Attention", summary?.active_attention], ["Safety Events Today", summary?.safety_events_today], ["Restricted Entries Today", summary?.restricted_entries_today], ["Vehicle / Device Attention", summary?.vehicle_device_attention]].map(([label, count]) => <article key={String(label)}><strong>{count ?? "—"}</strong><span>{label}</span></article>)}</section><section className="alerts-workspace"><nav className="alerts-tabs" role="tablist">{([['attention', 'Active Attention'], ['safety', 'Safety Incidents'], ['geofence', 'Geofence Activity']] as const).map(([value, label]) => <button key={value} type="button" role="tab" aria-selected={tab === value} className={tab === value ? "active" : ""} onClick={() => { setTab(value); setSelected(null); setFiltersOpen(false); }}>{label}</button>)}</nav><div className="alerts-toolbar">
    {tab === "attention" && <input aria-label="Search attention" placeholder="Search vehicle or device" value={search} onChange={event => { setSearch(event.target.value); resetPage(); }} />}
    {tab === "safety" && <input aria-label="Search safety incidents" placeholder="Search vehicle or device" value={safetySearch} onChange={event => { setSafetySearch(event.target.value); resetPage(); }} />}
    <div className="advanced-filter-root queue-filter-root"><button type="button" className="filter-toggle btn-filter" aria-expanded={filtersOpen} aria-controls="alerts-filter-panel" onClick={() => setFiltersOpen(value => !value)}>Filters{activeFilterCount > 0 && <span className="active-filter-count" aria-label={`${activeFilterCount} active filters`}>{activeFilterCount}</span>}</button>
  {filtersOpen && <div id="alerts-filter-panel" className="advanced-filter-panel alerts-filter-panel">
    {tab === "attention" && <><select aria-label="Attention source" value={source} onChange={event => { setSource(event.target.value); resetPage(); }}><option value="">All Sources</option><option value="TELEMETRY">Telemetry</option><option value="INSPECTION">Inspection</option><option value="MAINTENANCE">Maintenance</option></select><select aria-label="Attention condition" value={condition} onChange={event => { setCondition(event.target.value); resetPage(); }}><option value="">All Conditions</option><option value="STALE_TELEMETRY">Stale Telemetry</option><option value="NO_TELEMETRY">No Telemetry</option><option value="FAILED_INSPECTION">Failed Inspection</option><option value="INSPECTION_NEEDS_ATTENTION">Inspection Needs Attention</option><option value="MAINTENANCE_OPEN">Maintenance Open</option><option value="MAINTENANCE_SCHEDULED">Maintenance Scheduled</option><option value="MAINTENANCE_IN_PROGRESS">Maintenance In Progress</option></select></>}
    {tab === "safety" && <select aria-label="Safety event type" value={safetyType} onChange={event => { setSafetyType(event.target.value); resetPage(); }}><option value="">All Safety Events</option><option value="HARSH_BRAKING">Harsh Braking</option><option value="HARSH_ACCELERATION">Harsh Acceleration</option><option value="SHARP_TURN">Sharp Turn</option></select>}
    {tab === "geofence" && <><select aria-label="Geofence event" value={geoEvent} onChange={event => { setGeoEvent(event.target.value); resetPage(); }}><option value="">All Events</option><option value="ENTER">Enter</option><option value="EXIT">Exit</option></select><select aria-label="Geofence category" value={category} onChange={event => { setCategory(event.target.value); resetPage(); }}><option value="">All Categories</option>{["RESTRICTED", "DEPOT", "CUSTOMER", "HOTEL", "CUSTOM"].map(value => <option key={value} value={value}>{words(value)}</option>)}</select></>}
    <select aria-label="Vehicle filter" value={vehicle} onChange={event => { setVehicle(event.target.value); resetPage(); }}><option value="">All Vehicles</option>{vehicleOptions.map(item => <option key={item.vehicle_id} value={item.vehicle_id}>{item.display_name} · {item.plate_number}</option>)}</select>
    {tab === "geofence" && <select aria-label="Geofence filter" value={geofenceId} onChange={event => { setGeofenceId(event.target.value); resetPage(); }}><option value="">All Geofences</option>{geofenceOptions.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>}
    {tab !== "attention" && <><label>From<input aria-label="Date from" type="date" value={dateFrom} onChange={event => { setDateFrom(event.target.value); resetPage(); }} /></label><label>To<input aria-label="Date to" type="date" value={dateTo} onChange={event => { setDateTo(event.target.value); resetPage(); }} /></label></>}
    {activeFilterCount > 0 && <button type="button" className="reset-filter-button" onClick={clearFilters}>Clear Filters</button>}
  </div>}</div></div><div className="alerts-table-wrap">{state === "loading" ? <p role="status" className="alerts-state">Loading {tab === "attention" ? "active attention" : tab === "safety" ? "safety incidents" : "geofence activity"}…</p> : state === "error" ? <div className="alerts-state"><p role="alert">Unable to load {tab === "attention" ? "active attention" : tab === "safety" ? "safety incidents" : "geofence activity"}.</p><button type="button" onClick={() => setRetryKey(value => value + 1)}>Retry</button></div> : <table><thead>{tab === "attention" ? <tr><th>Condition</th><th>Source</th><th>Vehicle / Device</th><th>Current State</th><th>Since / Last Updated</th><th>View</th></tr> : tab === "safety" ? <tr><th>Time</th><th>Type</th><th>Vehicle</th><th>Device</th><th>Position Source</th><th>Location</th><th>View</th></tr> : <tr><th>Time</th><th>Event</th><th>Geofence</th><th>Category</th><th>Vehicle</th><th>Location</th><th>View</th></tr>}</thead><tbody>
    {tab === "attention" && attention?.results.map(item => <tr key={item.id} tabIndex={0} className={selected?.item === item ? "selected" : ""} onClick={() => setSelected({ kind: tab, item })} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelected({ kind: tab, item }); } }}><td><span className="alerts-chip">{words(item.condition)}</span></td><td>{words(item.source)}</td><td><strong>{item.vehicle.display_name}</strong><small>{item.vehicle.plate_number} · {item.vehicle.device_id}</small></td><td>{words(item.current_state)}</td><td>{dateTime(item.last_updated_at)}</td><td><button type="button" onClick={event => { event.stopPropagation(); setSelected({ kind: tab, item }); }}>View</button></td></tr>)}
    {tab === "safety" && safety?.results.map(item => <tr key={item.event_id} tabIndex={0} className={selected?.item === item ? "selected" : ""} onClick={() => setSelected({ kind: tab, item })} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelected({ kind: tab, item }); } }}><td>{dateTime(item.recorded_at)}</td><td><span className="alerts-chip">{words(item.event_type)}</span></td><td><strong>{item.vehicle_name}</strong><small>{item.plate_number}</small></td><td>{item.device_id}</td><td>{words(item.position_source)}{item.position_source === "SIMULATED_TEST" && <small className="alerts-provenance">Simulated test data</small>}</td><td>{item.latitude.toFixed(4)}, {item.longitude.toFixed(4)}</td><td><button type="button" onClick={event => { event.stopPropagation(); setSelected({ kind: tab, item }); }}>View</button></td></tr>)}
    {tab === "geofence" && geofence?.results.map(item => <tr key={item.id} tabIndex={0} className={selected?.item === item ? "selected" : ""} onClick={() => setSelected({ kind: tab, item })} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelected({ kind: tab, item }); } }}><td>{dateTime(item.occurred_at)}</td><td><span className="alerts-chip">{item.is_restricted_entry ? "Restricted Zone Entry" : words(item.event_type)}</span></td><td>{item.geofence_name}</td><td>{words(item.geofence_category)}</td><td><strong>{item.vehicle_name}</strong><small>{item.plate_number}</small></td><td>{item.latitude.toFixed(4)}, {item.longitude.toFixed(4)}</td><td><button type="button" onClick={event => { event.stopPropagation(); setSelected({ kind: tab, item }); }}>View</button></td></tr>)}
    {!data?.results.length && <tr><td colSpan={7} className="alerts-empty">{tab === "attention" ? "No active attention conditions." : tab === "safety" ? "No safety incidents match the current filters." : "No geofence activity matches the current filters."}</td></tr>}
  </tbody></table>}</div>{state === "ready" && data && data.count > 0 && <Pagination page={page} count={data.count} length={data.results.length} onPage={setCurrentPage} />}</section>{selected && <DetailsDrawer selected={selected} onClose={() => setSelected(null)} />}</main>;
}
