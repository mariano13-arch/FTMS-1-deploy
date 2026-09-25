import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../contexts/AuthContext";
import { hasCapability } from "../../services/auth";
import { getVehicles, type Vehicle } from "../../services/vehicles";
import {
  getDevice,
  getDevices,
  pairDevice,
  unpairDevice,
  type Device,
  type DeviceDetail,
  type DevicePage,
} from "./api";

type LoadState = "loading" | "ready" | "error";
type BindingFilter = "all" | "paired" | "unpaired";

const formatDate = (value: string) => new Date(value).toLocaleString();
const telemetryLabel = (device: Device) => {
  if (!device.latest_telemetry) return "No telemetry received";
  const age = Date.now() - Date.parse(device.latest_telemetry.recorded_at);
  return age <= 5 * 60_000 ? "Recently seen" : "Stale";
};

export default function DevicesPage() {
  const { user } = useAuth();
  const canPair = hasCapability(user, "DEVICES", "PAIR");
  const canReplace = hasCapability(user, "DEVICES", "REPLACE");
  const canUnpair = hasCapability(user, "DEVICES", "UNPAIR");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<BindingFilter>("all");
  const [data, setData] = useState<DevicePage | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [selected, setSelected] = useState<DeviceDetail | null>(null);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [vehicleId, setVehicleId] = useState("");
  const [replaceCurrent, setReplaceCurrent] = useState(false);
  const [actionError, setActionError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  const query = useMemo(() => {
    const params = new URLSearchParams({ page_size: "100" });
    if (search.trim()) params.set("search", search.trim());
    if (filter !== "all") params.set("binding", filter);
    return params.toString();
  }, [filter, search]);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    const loadDevices = async () => {
      let response = await getDevices(query, controller.signal);
      const results = [...response.results];

      while (response.next) {
        const nextQuery = response.next.split("?", 2)[1] ?? "";
        response = await getDevices(nextQuery, controller.signal);
        results.push(...response.results);
      }

      setData({ ...response, count: results.length, results, next: null, previous: null });
      setState("ready");
    };

    void loadDevices()
      .catch((error) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setState("error");
      });
    return () => controller.abort();
  }, [query, refreshKey]);

  useEffect(() => {
    if (!canPair && !canReplace) return;
    const controller = new AbortController();
    getVehicles("page_size=100&is_active=true", controller.signal)
      .then((response) => setVehicles(response.results))
      .catch(() => setVehicles([]));
    return () => controller.abort();
  }, [canPair, canReplace]);

  const openDevice = async (deviceId: string) => {
    setActionError("");
    setSelected(await getDevice(deviceId));
    setVehicleId("");
    setReplaceCurrent(false);
  };

  const refreshSelected = async () => {
    if (!selected) return;
    setSelected(await getDevice(selected.device_id));
    setRefreshKey((value) => value + 1);
  };

  const confirmPair = async () => {
    if (!selected || !vehicleId) return;
    if (!window.confirm(`Pair ${selected.device_id} to the selected vehicle?`)) return;
    try {
      setActionError("");
      await pairDevice(selected.device_id, Number(vehicleId), replaceCurrent);
      await refreshSelected();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Unable to pair device.");
    }
  };

  const confirmUnpair = async () => {
    if (!selected || !window.confirm(`Unpair ${selected.device_id}? Binding history will be retained.`)) return;
    try {
      setActionError("");
      await unpairDevice(selected.device_id);
      await refreshSelected();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Unable to unpair device.");
    }
  };

  return (
    <main className="devices-page">
      <header className="devices-header">
        <small>Operations / Devices</small>
        <h1>Devices</h1>
      </header>

      <section className="devices-kpis" aria-label="Device registry summary">
        {data && Object.entries({
          "Total Registered": data.summary.total_registered,
          Paired: data.summary.paired,
          Unpaired: data.summary.unpaired,
          "Recently Seen": data.summary.recently_seen,
        }).map(([label, value]) => <article key={label}><strong>{value}</strong><span>{label}</span></article>)}
      </section>

      <section className="devices-workspace">
        <div className="devices-toolbar">
          <input
            aria-label="Search devices"
            placeholder="Search device or bound vehicle"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <div role="group" aria-label="Binding filters">
            {(["all", "paired", "unpaired"] as BindingFilter[]).map((value) => (
              <button key={value} className={filter === value ? "selected" : ""} onClick={() => setFilter(value)}>
                {value[0].toUpperCase() + value.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {state === "loading" ? <p role="status">Loading devices…</p> : state === "error" ? <p role="alert">Unable to load devices.</p> : (
          <>
            <div className="devices-table-wrap">
              <table>
                <thead><tr><th>Device ID</th><th>Registry</th><th>Current Vehicle</th><th>Binding</th><th>Last Seen</th><th>Position Source</th><th>Telemetry</th><th /></tr></thead>
                <tbody>
                  {data?.results.map((device) => (
                    <tr key={device.device_id}>
                      <td><strong>{device.device_id}</strong></td>
                      <td>{device.registration_status}</td>
                      <td>{device.current_vehicle ? `${device.current_vehicle.display_name} · ${device.current_vehicle.plate_number}` : "—"}</td>
                      <td><span className={`device-badge device-badge--${device.is_paired ? "paired" : "unpaired"}`}>{device.is_paired ? "Paired" : "Unpaired"}</span></td>
                      <td>{device.latest_telemetry ? formatDate(device.latest_telemetry.recorded_at) : "Never"}</td>
                      <td>{device.latest_telemetry?.position_source ?? "—"}</td>
                      <td>{telemetryLabel(device)}</td>
                      <td><button onClick={() => void openDevice(device.device_id)}>View</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!data?.results.length && <p className="devices-empty">No registered devices match this view.</p>}
          </>
        )}
      </section>

      {selected && <aside className="device-drawer" aria-label={`${selected.device_id} device details`}>
        <header><div><small>Device Details</small><h2>{selected.device_id}</h2></div><button aria-label="Close device details" onClick={() => setSelected(null)}>×</button></header>
        <div className="device-drawer-body">
          <section><h3>Device</h3><dl><div><dt>Registry</dt><dd>{selected.registration_status}</dd></div><div><dt>Registered</dt><dd>{formatDate(selected.created_at)}</dd></div></dl></section>
          <section><h3>Current Binding</h3>{selected.current_vehicle ? <dl><div><dt>Vehicle</dt><dd>{selected.current_vehicle.display_name} · {selected.current_vehicle.plate_number}</dd></div><div><dt>Paired</dt><dd>{selected.current_binding ? formatDate(selected.current_binding.paired_at) : "—"}</dd></div><div><dt>Paired by</dt><dd>{selected.current_binding?.paired_by ?? "Unavailable"}</dd></div></dl> : <p>Unpaired</p>}</section>
          <section><h3>Latest Telemetry</h3>{selected.latest_telemetry ? <dl><div><dt>Last recorded</dt><dd>{formatDate(selected.latest_telemetry.recorded_at)}</dd></div><div><dt>Position source</dt><dd>{selected.latest_telemetry.position_source}</dd></div><div><dt>OBD source</dt><dd>{selected.latest_telemetry.obd_source ?? "Unavailable"}</dd></div><div><dt>Coordinates</dt><dd>{selected.latest_telemetry.latitude.toFixed(5)}, {selected.latest_telemetry.longitude.toFixed(5)}</dd></div></dl> : <p>No telemetry received</p>}</section>
          <section><h3>Binding History</h3>{selected.binding_history.length ? <ol>{selected.binding_history.map((binding) => <li key={binding.id}><strong>{binding.vehicle_name} · {binding.plate_number}</strong><span>{formatDate(binding.paired_at)} — {binding.unpaired_at ? formatDate(binding.unpaired_at) : "Current"}</span></li>)}</ol> : <p>No binding history.</p>}</section>
          {((selected.is_paired && canUnpair) || (!selected.is_paired && canPair)) && <section className="device-actions"><h3>Actions</h3>{selected.is_paired ? <><p>Unpair this device before assigning it to another vehicle. Binding history and telemetry are retained.</p><button className="secondary" onClick={() => void confirmUnpair()}>Unpair</button></> : <><select aria-label="Vehicle for device pairing" value={vehicleId} onChange={(event) => setVehicleId(event.target.value)}><option value="">Select active vehicle</option>{vehicles.filter((vehicle) => vehicle.id != null).map((vehicle) => <option key={vehicle.id} value={vehicle.id}>{vehicle.display_name} · {vehicle.plate_number}</option>)}</select>{canReplace && <label><input type="checkbox" checked={replaceCurrent} onChange={(event) => setReplaceCurrent(event.target.checked)} /> Replace that vehicle's current device if it already has one</label>}<button disabled={!vehicleId} onClick={() => void confirmPair()}>{replaceCurrent ? "Replace Vehicle Device" : "Pair to Vehicle"}</button></>}</section>}
          {actionError && <p role="alert" className="message message--error">{actionError}</p>}
        </div>
      </aside>}
    </main>
  );
}
