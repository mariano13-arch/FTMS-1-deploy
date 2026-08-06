import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, Redirect, Route, Switch, useHistory, useParams } from "react-router-dom";
import { useAuth } from "../../AuthContext";
import LiveVehicleMap from "../../components/LiveVehicleMap";
import { useVehicleStatus } from "../../hooks/useVehicleStatus";
import { ApiError } from "../../services/api";
import type { Role } from "../../services/auth";
import { changeVehicleStatus, createVehicle, editVehicle, getVehicle, getVehicles, vehicleTypes, type Vehicle } from "../../services/vehicles";

const canEdit = (role: Role) => role === "SUPER_ADMIN" || role === "FLEET_MANAGER";

function VehicleList() {
  const { user } = useAuth(); const [page, setPage] = useState<Awaited<ReturnType<typeof getVehicles>> | null>(null);
  const [error, setError] = useState(false); const [query, setQuery] = useState(""); const [search, setSearch] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    getVehicles(query, controller.signal).then(setPage).catch((reason: unknown) => {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) setError(true);
    }); return () => controller.abort();
  }, [query]);
  const filter = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget); const values = new URLSearchParams();
    if (search.trim()) values.set("search", search.trim());
    for (const key of ["is_active", "vehicle_type"]) { const value = String(data.get(key) ?? ""); if (value) values.set(key, value); }
    setPage(null); setError(false); setQuery(values.toString());
  };
  return <><div className="page-title"><div><p className="eyebrow">Sprint 3</p><h1>Vehicles</h1></div>
    {user?.role === "SUPER_ADMIN" && <Link className="button" to="/vehicles/new">Create vehicle</Link>}</div>
    <form className="filters" onSubmit={filter}><label>Search<input value={search} onChange={e => setSearch(e.target.value)} /></label>
      <label>Status<select name="is_active"><option value="">All</option><option value="true">Active</option><option value="false">Inactive</option></select></label>
      <label>Type<select name="vehicle_type"><option value="">All</option>{vehicleTypes.map(v => <option key={v}>{v}</option>)}</select></label><button>Apply filters</button></form>
    {!page && !error && <p>Loading vehicles…</p>}{error && <p role="alert" className="message message--error">Unable to load vehicles.</p>}
    {page?.results.length === 0 && <p>No vehicles match these filters.</p>}
    <div className="vehicle-list">{page?.results.map(vehicle => <article key={vehicle.device_id}><div>
      <h2><Link to={`/vehicles/${encodeURIComponent(vehicle.device_id)}`}>{vehicle.display_name}</Link></h2>
      <p>{vehicle.device_id} · {vehicle.plate_number} · {vehicle.vehicle_type}</p></div>
      <span className={vehicle.is_active ? "freshness--fresh" : "freshness--stale"}>{vehicle.is_active ? "Active" : "Inactive"}</span>
      {user && canEdit(user.role) && <Link to={`/vehicles/${encodeURIComponent(vehicle.device_id)}/edit`}>Edit</Link>}</article>)}</div>
    {page && <nav className="pagination" aria-label="Vehicle pages"><button disabled={!page.previous} onClick={() => { setError(false); setPage(null); setQuery(new URL(page.previous!).search.slice(1)); }}>Previous</button>
      <span>{page.count} vehicle{page.count === 1 ? "" : "s"}</span><button disabled={!page.next} onClick={() => { setError(false); setPage(null); setQuery(new URL(page.next!).search.slice(1)); }}>Next</button></nav>}
  </>;
}
function VehicleForm({ editing = false }: { editing?: boolean }) {
  const { user } = useAuth(); const { deviceId = "" } = useParams<{ deviceId: string }>(); const history = useHistory();
  const [vehicle, setVehicle] = useState<Vehicle | null>(null); const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const mounted = useRef(true);
  const submitInFlight = useRef(false);
  const submitController = useRef<AbortController | null>(null);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false; submitController.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (!editing) return;
    let active = true; const controller = new AbortController();
    getVehicle(deviceId, controller.signal)
      .then((loaded) => { if (active) setVehicle(loaded); })
      .catch((reason: unknown) => {
        if (active && !(reason instanceof DOMException && reason.name === "AbortError")) {
          setError(reason instanceof ApiError && reason.status === 403 ? "You do not have permission to edit this vehicle." : reason instanceof ApiError && reason.status === 404 ? "Vehicle not found." : "Unable to load vehicle.");
        }
      });
    return () => { active = false; controller.abort(); };
  }, [editing, deviceId]);
  if (!user || (editing ? !canEdit(user.role) : user.role !== "SUPER_ADMIN")) return <Redirect to="/vehicles" />;
  if (editing && !vehicle && !error) return <p>Loading vehicle…</p>;
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitInFlight.current) return;
    submitInFlight.current = true;
    setError(""); setFieldErrors({}); const data = new FormData(event.currentTarget); const payload: Record<string, unknown> = {};
    for (const key of ["device_id","plate_number","display_name","vehicle_type","manufacturer","model"]) if (!editing || key !== "device_id") payload[key] = String(data.get(key) ?? "");
    for (const key of ["model_year","passenger_capacity"]) { const value = String(data.get(key) ?? ""); payload[key] = value ? Number(value) : null; }
    setBusy(true);
    const controller = new AbortController(); submitController.current = controller;
    try {
      const saved = editing
        ? await editVehicle(deviceId, payload, controller.signal)
        : await createVehicle(payload, controller.signal);
      if (mounted.current) history.push(`/vehicles/${encodeURIComponent(saved.device_id)}`);
    }
    catch (reason) {
      if (!mounted.current) return;
      if (reason instanceof ApiError && reason.body && typeof reason.body === "object") {
        const safe = Object.fromEntries(
          Object.entries(reason.body as Record<string, unknown>).map(([key, value]) => [
            key, Array.isArray(value) ? String(value[0]) : String(value),
          ]),
        );
        setFieldErrors(safe); setError("Please correct the vehicle information.");
      } else if (!(reason instanceof DOMException && reason.name === "AbortError")) {
        setError("Unable to save vehicle.");
      }
    } finally {
      if (submitController.current === controller) {
        submitController.current = null;
        submitInFlight.current = false;
        if (mounted.current) setBusy(false);
      }
    }
  };
  return <><h1>{editing ? "Edit vehicle" : "Create vehicle"}</h1><form key={editing ? deviceId : "create"} className="vehicle-form" onSubmit={submit}>
    <label>Device ID<input name="device_id" required={!editing} disabled={editing} defaultValue={vehicle?.device_id} pattern="[A-Z0-9][A-Z0-9._-]{0,63}" aria-describedby="device_id-error" />{fieldErrors.device_id && <span id="device_id-error" role="alert">{fieldErrors.device_id}</span>}</label>
    <label>Plate number<input name="plate_number" required defaultValue={vehicle?.plate_number} aria-describedby="plate_number-error" />{fieldErrors.plate_number && <span id="plate_number-error" role="alert">{fieldErrors.plate_number}</span>}</label>
    <label>Display name<input name="display_name" required defaultValue={vehicle?.display_name} aria-describedby="display_name-error" />{fieldErrors.display_name && <span id="display_name-error" role="alert">{fieldErrors.display_name}</span>}</label>
    <label>Vehicle type<select name="vehicle_type" defaultValue={vehicle?.vehicle_type ?? "OTHER"} aria-describedby="vehicle_type-error">{vehicleTypes.map(v => <option key={v}>{v}</option>)}</select>{fieldErrors.vehicle_type && <span id="vehicle_type-error" role="alert">{fieldErrors.vehicle_type}</span>}</label>
    <label>Manufacturer<input name="manufacturer" defaultValue={vehicle?.manufacturer} aria-describedby="manufacturer-error" />{fieldErrors.manufacturer && <span id="manufacturer-error" role="alert">{fieldErrors.manufacturer}</span>}</label>
    <label>Model<input name="model" defaultValue={vehicle?.model} aria-describedby="model-error" />{fieldErrors.model && <span id="model-error" role="alert">{fieldErrors.model}</span>}</label>
    <label>Model year<input name="model_year" type="number" min="1980" max={new Date().getUTCFullYear() + 1} defaultValue={vehicle?.model_year ?? ""} aria-describedby="model_year-error" />{fieldErrors.model_year && <span id="model_year-error" role="alert">{fieldErrors.model_year}</span>}</label>
    <label>Passenger capacity<input name="passenger_capacity" type="number" min="1" max="100" defaultValue={vehicle?.passenger_capacity ?? ""} aria-describedby="passenger_capacity-error" />{fieldErrors.passenger_capacity && <span id="passenger_capacity-error" role="alert">{fieldErrors.passenger_capacity}</span>}</label>
    {error && <p role="alert" className="message message--error">{error}</p>}<button disabled={busy}>{busy ? "Saving…" : "Save vehicle"}</button>
  </form></>;
}
function LiveStatus({ deviceId }: { deviceId: string }) {
  const [now, setNow] = useState(() => Date.now()); const { status: vehicle, requestState, realtimeState } = useVehicleStatus(deviceId);
  useEffect(() => { const id = window.setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(id); }, []);
  const latest = vehicle?.latest ?? null; const stale = latest && now - Date.parse(latest.recorded_at) > 60_000;
  const value = (number: number | null, suffix: string) => number === null ? "Unavailable" : `${number.toLocaleString()} ${suffix}`;
  return <section aria-labelledby="pilot-title"><p className="eyebrow">Live MQTT/WebSocket pilot</p><h2 id="pilot-title">Simulated Pilot Data</h2><p>Real-time status: {realtimeState}</p>
    {requestState === "loading" && <p>Loading vehicle status…</p>}{requestState === "error" && !vehicle && <p className="message message--error">Latest-status request failed.</p>}
    {vehicle && !latest && <p>Waiting for the first telemetry event…</p>}{latest && <><span className={stale ? "freshness--stale" : "freshness--fresh"}>{stale ? "Stale telemetry" : "Fresh telemetry"}</span>
      <dl className="telemetry-grid"><div><dt>Speed</dt><dd>{value(latest.gnss_speed_kph, "km/h")}</dd></div><div><dt>RPM</dt><dd>{value(latest.rpm, "rpm")}</dd></div>
        <div><dt>Coolant</dt><dd>{value(latest.coolant_c, "°C")}</dd></div><div><dt>Engine load</dt><dd>{value(latest.engine_load_pct, "%")}</dd></div>
        <div><dt>Driving event</dt><dd>{latest.driving_event.replaceAll("_", " ")}</dd></div><div><dt>Position</dt><dd>{latest.latitude.toFixed(4)}, {latest.longitude.toFixed(4)}</dd></div>
        <div><dt>Recorded at</dt><dd>{new Date(latest.recorded_at).toLocaleString()}</dd></div><div><dt>Received at</dt><dd>{new Date(latest.received_at).toLocaleString()}</dd></div></dl></>}
    <LiveVehicleMap latest={latest} /></section>;
}
function VehicleDetail() {
  const { deviceId = "" } = useParams<{ deviceId: string }>(); const { user } = useAuth(); const [vehicle, setVehicle] = useState<Vehicle | null>(null);
  const [state, setState] = useState<"loading"|"error"|"missing">("loading");
  const [actionError, setActionError] = useState("");
  const [actionBusy, setActionBusy] = useState(false);
  const mounted = useRef(true);
  const actionInFlight = useRef(false);
  const actionController = useRef<AbortController | null>(null);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false; actionController.current?.abort();
    };
  }, []);
  useEffect(() => {
    let active = true; const controller = new AbortController();
    getVehicle(deviceId, controller.signal)
      .then((loaded) => { if (active) setVehicle(loaded); })
      .catch((error: unknown) => {
        if (active && !(error instanceof DOMException && error.name === "AbortError")) {
          setState(error instanceof ApiError && error.status === 404 ? "missing" : "error");
        }
      });
    return () => { active = false; controller.abort(); };
  }, [deviceId]);
  if (!vehicle || vehicle.device_id !== deviceId) return <p role={state === "error" ? "alert" : undefined}>{state === "loading" ? "Loading vehicle…" : state === "missing" ? "Vehicle not found." : "Unable to load vehicle."}</p>;
  const toggle = async () => {
    if (actionInFlight.current) return;
    const action = vehicle.is_active ? "deactivate" : "reactivate";
    if (!window.confirm(`Confirm ${action} ${vehicle.device_id}?`)) return;
    actionInFlight.current = true;
    setActionBusy(true);
    setActionError("");
    const controller = new AbortController(); actionController.current = controller;
    try {
      const updated = await changeVehicleStatus(
        vehicle.device_id, !vehicle.is_active, controller.signal,
      );
      if (mounted.current) setVehicle(updated);
    } catch (error) {
      if (
        mounted.current &&
        !(error instanceof DOMException && error.name === "AbortError")
      ) setActionError(`Unable to ${action} this vehicle.`);
    } finally {
      if (actionController.current === controller) {
        actionController.current = null;
        actionInFlight.current = false;
        if (mounted.current) setActionBusy(false);
      }
    }
  };
  return <><div className="page-title"><div><p className="eyebrow">{vehicle.device_id}</p><h1>{vehicle.display_name}</h1></div>
    {user && canEdit(user.role) && <Link className="button" to="edit">Edit</Link>}{user?.role === "SUPER_ADMIN" && <button disabled={actionBusy} onClick={() => void toggle()}>{actionBusy ? "Updating…" : vehicle.is_active ? "Deactivate" : "Reactivate"}</button>}</div>
    {actionError && <p role="alert" className="message message--error">{actionError}</p>}<dl className="registry-grid">{Object.entries(vehicle).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{value === null || value === "" ? "Unavailable" : String(value)}</dd></div>)}</dl>
    <LiveStatus deviceId={vehicle.device_id} /></>;
}
function VehicleEditRoute() {
  const { deviceId = "" } = useParams<{ deviceId: string }>();
  return <VehicleForm key={deviceId} editing />;
}
function VehicleDetailRoute() {
  const { deviceId = "" } = useParams<{ deviceId: string }>();
  return <VehicleDetail key={deviceId} />;
}
export default function VehicleRoutes() {
  return <Switch>
    <Route path="/vehicles/new" exact><VehicleForm /></Route>
    <Route path="/vehicles/:deviceId/edit" exact><VehicleEditRoute /></Route>
    <Route path="/vehicles/:deviceId" exact><VehicleDetailRoute /></Route>
    <Route path="/vehicles" exact><VehicleList /></Route>
  </Switch>;
}
