import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getDrivers, type Driver } from "../../services/drivers";
import RequestMap, { type FleetPopupInfo } from "../transport-requests/components/RequestMap";
import { getRequestRoute } from "../transport-requests/api";
import type { TransportRoute } from "../transport-requests/types";
import GeofenceWorkspace from "./GeofenceWorkspace";
import {
  getFleetLiveVehicles,
  getFleetSafetyEvents,
  getFleetVehicleTrail,
  createGeofence as createGeofenceRecord,
  getGeofence,
  getGeofences,
  updateGeofence,
  type FleetLiveResponse,
  type FleetSafetyEvent,
  type FleetTrailPoint,
  type Geofence,
  type GeofenceCoordinate,
  type GeofenceWrite,
  type TelemetryState,
} from "./api";

type FleetFilter = "all" | "assigned" | "live" | "attention";
type NavigatorView = "vehicles" | "drivers" | "groups" | "assets";
type AsyncState = "idle" | "loading" | "ready" | "error";
const pollIntervalMs = 15_000;
const words = (value: string) => value.toLowerCase().replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase());
const stateLabel: Record<TelemetryState, string> = { live: "Live", stale: "Stale", offline: "Offline", no_telemetry: "No telemetry" };
const navigatorLabel: Record<NavigatorView, string> = { vehicles: "Vehicles", drivers: "Drivers", groups: "Groups", assets: "Assets" };
type GeofenceDraft = GeofenceWrite & { id?: string };

function circleVertices(center: GeofenceCoordinate, radiusMeters: number) {
  return Array.from({ length: 40 }, (_, index) => {
    const angle = index / 40 * Math.PI * 2;
    const latitude = center.latitude + radiusMeters * Math.cos(angle) / 111_320;
    const longitudeScale = 111_320 * Math.max(Math.abs(Math.cos(center.latitude * Math.PI / 180)), 0.2);
    return { latitude, longitude: center.longitude + radiusMeters * Math.sin(angle) / longitudeScale };
  });
}

function geofenceDraftFromPoint(point: GeofenceCoordinate): GeofenceDraft {
  const radiusMeters = 150;
  return { name: "", description: "", category: "CUSTOM", shape_type: "CIRCLE", center: point, radius_meters: radiusMeters, vertices: circleVertices(point, radiusMeters), color: "#008F8C", show_on_map: true, is_active: true };
}

function NavigatorIcon({ kind }: { kind: "fleet" | "driver" }) {
  return kind === "fleet" ? <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="2" width="6" height="5" rx="1"/><rect x="2" y="17" width="6" height="5" rx="1"/><rect x="16" y="17" width="6" height="5" rx="1"/><path d="M12 7v5M5 17v-5h14v5"/></svg> : <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="7" r="4"/><path d="M2.5 21v-3.5A5.5 5.5 0 0 1 8 12h2a5.5 5.5 0 0 1 5.5 5.5V21M17 9h5M19.5 6.5v5"/></svg>;
}

export default function LiveFleetOperationsPage() {
  const [data, setData] = useState<FleetLiveResponse | null>(null);
  const dataRef = useRef<FleetLiveResponse | null>(null);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [refreshError, setRefreshError] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [filter, setFilter] = useState<FleetFilter>("all");
  const [search, setSearch] = useState("");
  const [route, setRoute] = useState<TransportRoute | null>(null);
  const [routeState, setRouteState] = useState<AsyncState>("idle");
  const [trail, setTrail] = useState<FleetTrailPoint[]>([]);
  const [safetyEvents, setSafetyEvents] = useState<FleetSafetyEvent[]>([]);
  const [eventsState, setEventsState] = useState<AsyncState>("loading");
  const [popupVehicleId, setPopupVehicleId] = useState("");
  const [vehiclePanelOpen, setVehiclePanelOpen] = useState(true);
  const [overviewPanelOpen, setOverviewPanelOpen] = useState(true);
  const [navigatorView, setNavigatorView] = useState<NavigatorView>("vehicles");
  const [navigatorMenuOpen, setNavigatorMenuOpen] = useState(false);
  const [hiddenVehicleIds, setHiddenVehicleIds] = useState<Set<string>>(() => new Set());
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [driversState, setDriversState] = useState<AsyncState>("loading");
  const [geofences, setGeofences] = useState<Geofence[]>([]);
  const [geofenceState, setGeofenceState] = useState<AsyncState>("loading");
  const [geofencePanelOpen, setGeofencePanelOpen] = useState(false);
  const [selectedGeofenceId, setSelectedGeofenceId] = useState("");
  const [selectedGeofence, setSelectedGeofence] = useState<Geofence | null>(null);
  const [geofenceDraft, setGeofenceDraft] = useState<GeofenceDraft | null>(null);
  const [geofenceDrawing, setGeofenceDrawing] = useState(false);
  const [geofencePlacement, setGeofencePlacement] = useState(false);
  const [geofenceSaveState, setGeofenceSaveState] = useState<AsyncState>("idle");

  useEffect(() => { dataRef.current = data; }, [data]);
  useEffect(() => {
    const controller = new AbortController();
    getDrivers("page_size=100", controller.signal)
      .then(response => { setDrivers(response.results); setDriversState("ready"); })
      .catch(reason => { if (!(reason instanceof DOMException && reason.name === "AbortError")) setDriversState("error"); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    getGeofences(controller.signal)
      .then(response => { setGeofences(response.results); setGeofenceState("ready"); })
      .catch(reason => { if (!(reason instanceof DOMException && reason.name === "AbortError")) setGeofenceState("error"); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!selectedGeofenceId) return;
    const controller = new AbortController();
    Promise.resolve(getGeofence(selectedGeofenceId, controller.signal))
      .then(result => { if (result) setSelectedGeofence(result); })
      .catch(reason => { if (!(reason instanceof DOMException && reason.name === "AbortError")) setSelectedGeofence(null); });
    return () => controller.abort();
  }, [selectedGeofenceId]);
  useEffect(() => {
    let active = true;
    let controller: AbortController | null = null;
    let timer = 0;
    const load = async () => {
      controller = new AbortController();
      try {
        const response = await getFleetLiveVehicles(controller.signal);
        if (!active) return;
        setData(response);
        setLoadState("ready");
        setRefreshError(false);
        setSelectedId(current => current && response.vehicles.some(vehicle => vehicle.device_id === current) ? current : response.vehicles[0]?.device_id ?? "");
      } catch (reason) {
        if (!active || reason instanceof DOMException && reason.name === "AbortError") return;
        if (dataRef.current) setRefreshError(true); else setLoadState("error");
      } finally {
        if (active) timer = window.setTimeout(load, pollIntervalMs);
      }
    };
    timer = window.setTimeout(load, 0);
    return () => { active = false; window.clearTimeout(timer); controller?.abort(); };
  }, []);

  useEffect(() => {
    if (loadState !== "ready" || !data?.capabilities.safety_events) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setEventsState("loading");
      getFleetSafetyEvents(controller.signal)
        .then(response => { setSafetyEvents(response.events); setEventsState("ready"); })
        .catch(reason => { if (!(reason instanceof DOMException && reason.name === "AbortError")) setEventsState("error"); });
    }, 0);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [data?.capabilities.safety_events, loadState]);

  const selected = data?.vehicles.find(vehicle => vehicle.device_id === selectedId) ?? null;
  const selectedRequestId = selected?.active_assignment?.request_id ?? "";
  const selectedVehicleId = selected?.vehicle_id ?? 0;

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setRoute(null);
      if (!selectedRequestId) { setRouteState("idle"); return; }
      setRouteState("loading");
      getRequestRoute(selectedRequestId, controller.signal)
        .then(result => { setRoute(result); setRouteState("ready"); })
        .catch(reason => { if (!(reason instanceof DOMException && reason.name === "AbortError")) setRouteState("error"); });
    }, 0);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [selectedRequestId]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setTrail([]);
      if (!selectedVehicleId || !data?.capabilities.telemetry_trail) return;
      getFleetVehicleTrail(selectedVehicleId, controller.signal)
        .then(response => { setTrail(response.points); })
        .catch(reason => { if (!(reason instanceof DOMException && reason.name === "AbortError")) setTrail([]); });
    }, 0);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [data?.capabilities.telemetry_trail, selectedVehicleId]);

  const selectVehicle = useCallback((deviceId: string) => { setSelectedId(deviceId); setPopupVehicleId(""); }, []);
  const openVehiclePopup = useCallback((deviceId: string) => { setTrail([]); setSelectedId(deviceId); setPopupVehicleId(deviceId); }, []);
  const selectSafetyEvent = useCallback((eventId: string) => {
    const event = safetyEvents.find(item => item.event_id === eventId);
    if (event) { setSelectedId(event.device_id); setPopupVehicleId(event.device_id); }
  }, [safetyEvents]);
  const fleetLocations = useMemo(() => (data?.vehicles ?? []).flatMap(vehicle => !vehicle.telemetry || hiddenVehicleIds.has(vehicle.device_id) ? [] : [{
    deviceId: vehicle.device_id,
    latitude: vehicle.telemetry.latitude,
    longitude: vehicle.telemetry.longitude,
    label: vehicle.display_name,
    telemetryState: vehicle.telemetry_state,
    selected: vehicle.device_id === selectedId,
  }]), [data?.vehicles, hiddenVehicleIds, selectedId]);
  const popupVehicle = data?.vehicles.find(vehicle => vehicle.device_id === popupVehicleId) ?? null;
  const fleetPopup: FleetPopupInfo | null = popupVehicle?.telemetry ? {
    deviceId: popupVehicle.device_id,
    label: popupVehicle.display_name,
    plateNumber: popupVehicle.plate_number,
    telemetryState: popupVehicle.telemetry_state,
    latitude: popupVehicle.telemetry.latitude,
    longitude: popupVehicle.telemetry.longitude,
    speedKph: popupVehicle.telemetry.speed_kph,
    recordedAt: popupVehicle.telemetry.recorded_at,
    ageSeconds: popupVehicle.telemetry.age_seconds,
    driverName: popupVehicle.active_assignment?.driver_name,
    assignmentStatus: popupVehicle.active_assignment ? words(popupVehicle.active_assignment.execution_status) : undefined,
    telemetrySource: popupVehicle.telemetry.telemetry_source,
  } : null;
  const mapRequest = selected?.active_assignment ? {
    pickup_name: selected.active_assignment.pickup_name,
    pickup_latitude: selected.active_assignment.pickup_latitude,
    pickup_longitude: selected.active_assignment.pickup_longitude,
    destination_name: selected.active_assignment.destination_name,
    destination_latitude: selected.active_assignment.destination_latitude,
    destination_longitude: selected.active_assignment.destination_longitude,
  } : null;
  const visibleVehicles = (data?.vehicles ?? []).filter(vehicle => {
    const matchesSearch = `${vehicle.display_name} ${vehicle.device_id} ${vehicle.plate_number} ${vehicle.active_assignment?.driver_name ?? ""}`.toLowerCase().includes(search.trim().toLowerCase());
    const matchesFilter = filter === "all" || filter === "assigned" && Boolean(vehicle.active_assignment) || filter === "live" && vehicle.telemetry_state === "live" || filter === "attention" && ["stale", "offline", "no_telemetry"].includes(vehicle.telemetry_state);
    return matchesSearch && matchesFilter;
  });
  const visibleDrivers = drivers.filter(driver => `${driver.full_name} ${driver.driver_code}`.toLowerCase().includes(search.trim().toLowerCase()));
  const navigatorCount = navigatorView === "vehicles" ? visibleVehicles.length : navigatorView === "drivers" ? visibleDrivers.length : 0;
  const toggleVehicleVisibility = (deviceId: string) => setHiddenVehicleIds(current => {
    const next = new Set(current);
    if (next.has(deviceId)) next.delete(deviceId); else next.add(deviceId);
    return next;
  });
  const selectDriver = (driver: Driver) => {
    const assignedVehicle = data?.vehicles.find(vehicle => vehicle.active_assignment?.driver_id === driver.id);
    if (assignedVehicle) selectVehicle(assignedVehicle.device_id);
  };
  const noFleetTelemetry = Boolean(data?.vehicles.length) && data?.vehicles.every(vehicle => !vehicle.telemetry);
  const fleetCounts = {
    total: data?.vehicles.length ?? 0,
    live: data?.vehicles.filter(vehicle => vehicle.telemetry_state === "live").length ?? 0,
    attention: data?.vehicles.filter(vehicle => ["stale", "offline"].includes(vehicle.telemetry_state)).length ?? 0,
    assigned: data?.vehicles.filter(vehicle => Boolean(vehicle.active_assignment)).length ?? 0,
    noTelemetry: data?.vehicles.filter(vehicle => vehicle.telemetry_state === "no_telemetry").length ?? 0,
  };
  const startGeofenceDraft = (point: GeofenceCoordinate) => {
    setGeofenceDraft(geofenceDraftFromPoint(point));
    setSelectedGeofenceId("");
    setSelectedGeofence(null);
    setGeofenceDrawing(false);
    setGeofencePlacement(false);
    setGeofencePanelOpen(true);
    setOverviewPanelOpen(false);
    setGeofenceSaveState("idle");
  };
  const selectGeofence = (id: string) => {
    setSelectedGeofenceId(id);
    setSelectedGeofence(geofences.find(item => item.id === id) ?? null);
    setGeofenceDraft(null);
    setGeofenceDrawing(false);
    setGeofencePlacement(false);
    setGeofencePanelOpen(true);
    setOverviewPanelOpen(false);
  };
  const changeGeofenceRadius = (radiusMeters: number) => setGeofenceDraft(current => current ? {
    ...current,
    radius_meters: radiusMeters,
    vertices: circleVertices(current.center, radiusMeters),
  } : current);
  const changeGeofenceShape = (shape: GeofenceWrite["shape_type"]) => setGeofenceDraft(current => {
    if (!current) return current;
    if (shape === "CIRCLE") {
      const radiusMeters = current.radius_meters ?? 150;
      setGeofenceDrawing(false);
      return { ...current, shape_type: shape, radius_meters: radiusMeters, vertices: circleVertices(current.center, radiusMeters) };
    }
    setGeofenceDrawing(true);
    return { ...current, shape_type: shape, radius_meters: null, vertices: [] };
  });
  const addGeofenceVertex = (point: GeofenceCoordinate) => setGeofenceDraft(current => {
    if (!current || current.shape_type !== "POLYGON") return current;
    const vertices = [...current.vertices, point];
    const center = vertices.reduce((result, vertex) => ({ latitude: result.latitude + vertex.latitude / vertices.length, longitude: result.longitude + vertex.longitude / vertices.length }), { latitude: 0, longitude: 0 });
    return { ...current, vertices, center };
  });
  const editSelectedGeofence = () => {
    if (!selectedGeofence) return;
    setGeofenceDraft({ id: selectedGeofence.id, name: selectedGeofence.name, description: selectedGeofence.description, category: selectedGeofence.category, shape_type: selectedGeofence.shape_type, vertices: selectedGeofence.vertices, center: selectedGeofence.center, radius_meters: selectedGeofence.radius_meters, color: selectedGeofence.color, show_on_map: selectedGeofence.show_on_map, is_active: selectedGeofence.is_active });
    setGeofenceSaveState("idle");
  };
  const saveGeofence = async () => {
    if (!geofenceDraft || !geofenceDraft.name.trim() || geofenceDraft.vertices.length < 3) return;
    setGeofenceSaveState("loading");
    const { id, ...body } = geofenceDraft;
    try {
      const saved = id ? await updateGeofence(id, body) : await createGeofenceRecord(body);
      const response = await getGeofences();
      setGeofences(response.results);
      setSelectedGeofence(saved);
      setSelectedGeofenceId(saved.id);
      setGeofenceDraft(null);
      setGeofenceDrawing(false);
      setGeofenceSaveState("ready");
    } catch {
      setGeofenceSaveState("error");
    }
  };

  return <section className="transport-page transport-page--workspace live-fleet-page">
    {loadState === "loading" && <div className="live-fleet-page-state" role="status">Loading fleet operations…</div>}
    {loadState === "error" && <div className="live-fleet-page-state live-fleet-page-state--error" role="alert"><strong>Unable to load fleet operations</strong><span>Please retry when the fleet service is available.</span></div>}
    {refreshError && <p role="alert" className="message message--error live-fleet-refresh-error">Latest refresh failed. Showing the last successful fleet snapshot.</p>}
    {loadState === "ready" && data && <div className="live-fleet-workspace">
      <div className="live-fleet-map">
        {noFleetTelemetry && <div className="live-fleet-map-notice">Vehicles are registered, but no telemetry has been received yet.</div>}
        <RequestMap request={mapRequest} route={route} routeState={routeState} fleetLocations={fleetLocations} fleetTrail={trail} fleetPopup={fleetPopup} safetyEvents={safetyEvents} onVehicleSelect={openVehiclePopup} onVehiclePopupClose={() => setPopupVehicleId("")} onSafetyEventSelect={selectSafetyEvent} geofences={geofences.map(item => ({ id: item.id, name: item.name, color: item.color, vertices: item.vertices, center: item.center, showOnMap: item.show_on_map, selected: item.id === selectedGeofenceId }))} geofenceDraft={geofenceDraft ? { color: geofenceDraft.color, vertices: geofenceDraft.vertices } : null} geofenceDrawing={geofenceDrawing || geofencePlacement} onGeofenceSelect={selectGeofence} onGeofenceCreateAt={startGeofenceDraft} onGeofenceDraftMapClick={point => geofencePlacement ? startGeofenceDraft(point) : addGeofenceVertex(point)} />
      </div>
      {(geofenceDrawing || geofencePlacement) && <div className="live-fleet-map-mode" role="status"><strong>{geofencePlacement ? "Choose the geofence center" : `Draw custom boundary · ${geofenceDraft?.vertices.length ?? 0} points`}</strong><span>{geofencePlacement ? "Click anywhere on the map." : "Click around the perimeter, then finish drawing."}</span><button type="button" onClick={() => { setGeofenceDrawing(false); setGeofencePlacement(false); }}>Cancel</button></div>}
      {data.demo_telemetry.enabled && <div className={`live-fleet-demo-banner ${data.demo_telemetry.active ? "" : "live-fleet-demo-banner--warning"}`} role="status">{data.demo_telemetry.active ? `Demo telemetry mode active — ${data.demo_telemetry.simulated_vehicle_count} simulated location${data.demo_telemetry.simulated_vehicle_count === 1 ? "" : "s"} for capstone defense only.` : data.demo_telemetry.configuration_error ?? "Demo telemetry mode is enabled but unavailable."}</div>}
      <div className="live-fleet-panel-controls" aria-label="Map panels">
        {!vehiclePanelOpen && <button type="button" aria-expanded="false" aria-controls="live-fleet-vehicle-panel" onClick={() => setVehiclePanelOpen(true)}>Show fleet <span aria-hidden="true">▾</span></button>}
        <button type="button" aria-expanded={geofencePanelOpen} aria-controls="live-fleet-geofence-panel" onClick={() => setGeofencePanelOpen(open => { if (!open) setOverviewPanelOpen(false); return !open; })}>Geofences <span aria-hidden="true">⬡</span></button>
        <button type="button" aria-expanded={overviewPanelOpen} aria-controls="live-fleet-overview-panel" onClick={() => setOverviewPanelOpen(open => !open)}>{overviewPanelOpen ? "Hide" : "Show"} overview <span aria-hidden="true">{overviewPanelOpen ? "▴" : "▾"}</span></button>
      </div>
      {overviewPanelOpen && <section id="live-fleet-overview-panel" className="live-fleet-overview" aria-label="Fleet operations overview">
        <header><div><h1>Live Fleet Operations Map</h1><p>Authoritative vehicle telemetry with confirmed dispatch and transport-request context.</p></div><time dateTime={data.generated_at}>Updated {new Date(data.generated_at).toLocaleTimeString()}</time></header>
        <div className="live-fleet-kpis"><article><strong>{fleetCounts.total}</strong><span>Total vehicles</span></article><article><strong>{fleetCounts.live}</strong><span>Live telemetry</span></article><article><strong>{fleetCounts.attention}</strong><span>Stale / offline</span></article><article><strong>{fleetCounts.assigned}</strong><span>Active assignments</span></article><article><strong>{fleetCounts.noTelemetry}</strong><span>No telemetry</span></article></div>
      </section>}
      {vehiclePanelOpen && <aside id="live-fleet-vehicle-panel" className="live-fleet-list live-fleet-navigator" aria-label="Fleet navigator">
        <nav className="live-fleet-navigator-tabs" aria-label="Fleet navigator shortcuts">
          <button type="button" className={navigatorView === "vehicles" ? "selected" : ""} aria-label="Show vehicles" onClick={() => { setNavigatorView("vehicles"); setSearch(""); }}><NavigatorIcon kind="fleet" /></button>
          <button type="button" className={navigatorView === "drivers" ? "selected" : ""} aria-label="Show drivers" onClick={() => { setNavigatorView("drivers"); setSearch(""); }}><NavigatorIcon kind="driver" /></button>
          <button type="button" aria-label="Collapse fleet navigator" onClick={() => setVehiclePanelOpen(false)}><span aria-hidden="true">−</span></button>
        </nav>
        <div className="live-fleet-navigator-select">
          <button type="button" aria-expanded={navigatorMenuOpen} aria-haspopup="menu" onClick={() => setNavigatorMenuOpen(open => !open)}><span>{navigatorLabel[navigatorView]}</span><small>{navigatorCount}</small><b aria-hidden="true">⌄</b></button>
          {navigatorMenuOpen && <div className="live-fleet-navigator-menu" role="menu">{(["vehicles", "drivers", "groups", "assets"] as NavigatorView[]).map(value => <button type="button" role="menuitem" className={navigatorView === value ? "selected" : ""} key={value} onClick={() => { setNavigatorView(value); setNavigatorMenuOpen(false); setSearch(""); }}>{navigatorLabel[value]}{value === "groups" || value === "assets" ? <small>Not configured</small> : null}</button>)}</div>}
        </div>
        <label className="live-fleet-navigator-search"><span aria-hidden="true">⌕</span><input aria-label={navigatorView === "vehicles" ? "Search fleet vehicles" : `Search ${navigatorLabel[navigatorView].toLowerCase()}`} placeholder={navigatorView === "drivers" ? "Search driver or code" : `Search ${navigatorLabel[navigatorView].toLowerCase()}`} value={search} onChange={event => setSearch(event.target.value)} /></label>
        {navigatorView === "vehicles" && <div className="live-fleet-filters" role="group" aria-label="Fleet filters">{(["all", "assigned", "live", "attention"] as FleetFilter[]).map(value => <button type="button" className={filter === value ? "selected" : ""} key={value} onClick={() => setFilter(value)}>{words(value)}</button>)}</div>}
        <div className="live-fleet-rows">
          {navigatorView === "vehicles" && (data.vehicles.length === 0 ? <p>No vehicles are registered for fleet operations.</p> : visibleVehicles.length === 0 ? <p>No vehicles match this view.</p> : visibleVehicles.map(vehicle => <div className={`live-fleet-asset-row ${vehicle.device_id === selectedId ? "selected" : ""}`} key={vehicle.device_id}>
            <label className="live-fleet-marker-toggle" title={`${hiddenVehicleIds.has(vehicle.device_id) ? "Show" : "Hide"} ${vehicle.display_name} on map`}><input type="checkbox" checked={!hiddenVehicleIds.has(vehicle.device_id)} onChange={() => toggleVehicleVisibility(vehicle.device_id)} aria-label={`Show ${vehicle.display_name} on map`} /><span /></label>
            <button type="button" onClick={() => selectVehicle(vehicle.device_id)}><span className="live-fleet-asset-icon" aria-hidden="true">▰</span><span><strong>{vehicle.display_name}</strong><small>{vehicle.plate_number} · {words(vehicle.vehicle_type)}</small>{vehicle.active_assignment ? <small>{vehicle.active_assignment.driver_name} · {vehicle.active_assignment.driver_code}</small> : <small>No assigned driver</small>}</span><span className={`live-fleet-row-state live-fleet-row-state--${vehicle.telemetry_state}`} title={stateLabel[vehicle.telemetry_state]} /></button>
          </div>))}
          {navigatorView === "drivers" && (driversState === "loading" ? <p>Loading drivers…</p> : driversState === "error" ? <p role="alert">Unable to load drivers.</p> : visibleDrivers.length === 0 ? <p>No drivers match this view.</p> : visibleDrivers.map(driver => {
            const assignedVehicle = data.vehicles.find(vehicle => vehicle.active_assignment?.driver_id === driver.id);
            return <button type="button" className="live-fleet-driver-row" key={driver.id} onClick={() => selectDriver(driver)} disabled={!assignedVehicle}><span className="live-fleet-driver-avatar">{driver.first_name[0]}{driver.last_name[0]}</span><span><strong>{driver.full_name}</strong><small>{driver.driver_code} · {words(driver.employment_status)}</small><small>{assignedVehicle ? `Assigned to ${assignedVehicle.display_name}` : "No active vehicle assignment"}</small></span><b>{words(driver.eligibility_status)}</b></button>;
          }))}
          {navigatorView === "groups" && <p className="live-fleet-navigator-empty"><strong>No groups configured</strong><span>Fleet grouping is not available in the current data model.</span></p>}
          {navigatorView === "assets" && <p className="live-fleet-navigator-empty"><strong>No non-vehicle assets configured</strong><span>Only registered fleet vehicles currently provide map locations.</span></p>}
        </div>
        <footer><span>{navigatorView === "vehicles" ? `${hiddenVehicleIds.size} hidden from map` : `${navigatorCount} ${navigatorLabel[navigatorView].toLowerCase()}`}</span><span>{eventsState === "error" ? "Safety events unavailable" : eventsState === "ready" ? `${safetyEvents.length} recent safety events` : "Loading safety events"}</span></footer>
      </aside>}
      <GeofenceWorkspace open={geofencePanelOpen} loadState={geofenceState} saveState={geofenceSaveState} geofences={geofences} selectedId={selectedGeofenceId} selected={selectedGeofenceId ? selectedGeofence : null} draft={geofenceDraft} onClose={() => { setGeofencePanelOpen(false); setGeofenceDrawing(false); setGeofencePlacement(false); }} onPlaceNew={() => { setGeofencePlacement(true); setSelectedGeofenceId(""); setSelectedGeofence(null); }} onSelect={selectGeofence} onEdit={editSelectedGeofence} onDraftChange={setGeofenceDraft} onShapeChange={changeGeofenceShape} onRadiusChange={changeGeofenceRadius} onRedraw={() => { setGeofenceDraft(current => current ? { ...current, vertices: [] } : current); setGeofenceDrawing(true); }} onFinishDrawing={() => setGeofenceDrawing(false)} onCancelDraft={() => { setGeofenceDraft(null); setGeofenceDrawing(false); }} onSave={() => void saveGeofence()} />
    </div>}
  </section>;
}
