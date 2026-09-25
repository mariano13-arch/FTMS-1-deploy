import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import LoadingIndicator from "../../components/common/LoadingIndicator";
import { apiBaseUrl } from "../../services/api";
import { getFleetLiveVehicles, type FleetLiveVehicle } from "./api";
import "./VehicleStatusPage.css";

const unavailable = "—";
const value = (item: number | null | undefined, suffix = "") =>
  item == null ? unavailable : `${item}${suffix}`;
const words = (item: string) =>
  item.toLowerCase().replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());

export default function VehicleStatusPage() {
  const { deviceId = "" } = useParams<{ deviceId: string }>();
  const [vehicle, setVehicle] = useState<FleetLiveVehicle | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "missing" | "error">("loading");

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    getFleetLiveVehicles(controller.signal)
      .then((response) => {
        if (!active) return;
        const match = response.vehicles.find((item) => item.device_id === deviceId) ?? null;
        setVehicle(match);
        setState(match ? "ready" : "missing");
      })
      .catch((reason) => {
        if (
          active &&
          !(reason instanceof DOMException && reason.name === "AbortError")
        ) {
          setState("error");
        }
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [deviceId]);

  if (state === "loading") return <LoadingIndicator variant="card" message="Loading vehicle status…" />;
  if (state === "error") return <p role="alert" className="vehicle-status-state">Unable to load vehicle status.</p>;
  if (!vehicle) return <p className="vehicle-status-state">Vehicle not found.</p>;

  return <VehicleStatusDrawer vehicle={vehicle} />;
}

export function VehicleStatusDrawer({
  vehicle,
  onClose,
}: {
  vehicle: FleetLiveVehicle;
  onClose?: () => void;
}) {
  const telemetry = vehicle.telemetry;
  return (
    <div className="vehicle-status-backdrop">
    <aside className="vehicle-status-page" role="dialog" aria-modal="true" aria-labelledby="vehicle-status-title">
      <header className="vehicle-status-toolbar">
        <div><small>FTMS</small><strong>Vehicle Status</strong><span>Real-time vehicle information and system status</span></div>
        {onClose ? (
          <button type="button" className="vehicle-status-close" onClick={onClose} aria-label="Close vehicle status">×</button>
        ) : (
          <Link className="vehicle-status-close" to="/live-map" aria-label="Close vehicle status">×</Link>
        )}
      </header>

      <section className="vehicle-status-hero">
        <div className="vehicle-status-photo">
          {vehicle.photo_url ? <img src={`${apiBaseUrl}${vehicle.photo_url}`} alt={`${vehicle.display_name} vehicle`} /> : <div role="img" aria-label={`No photo available for ${vehicle.display_name}`}><span aria-hidden="true">▰</span><small>No vehicle photo</small></div>}
        </div>
        <div className="vehicle-status-identity">
          <span className={`vehicle-status-pill vehicle-status-pill--${vehicle.telemetry_state}`}>● {words(vehicle.telemetry_state)}</span>
          <h1 id="vehicle-status-title">{vehicle.display_name}</h1>
          <strong>{vehicle.plate_number} <span>·</span> {vehicle.device_id}</strong>
          <p><span>Latest update</span>{telemetry ? new Date(telemetry.recorded_at).toLocaleString() : unavailable}</p>
        </div>
      </section>

      <section className="vehicle-status-summary" aria-label="Telemetry status">
        <div><span>Telemetry state</span><strong>{words(vehicle.telemetry_state)}</strong></div>
        <div><span>Vehicle identifier</span><strong>{vehicle.device_id}</strong></div>
        <div><span>Last update</span><strong>{telemetry ? new Date(telemetry.recorded_at).toLocaleString() : unavailable}</strong></div>
        <div><span>OBD source</span><strong>{telemetry?.obd_source ? words(telemetry.obd_source) : unavailable}</strong></div>
      </section>

      {vehicle.emergency_sos && (
        <section className="vehicle-status-emergency" aria-label="Emergency SOS">
          <div><strong>EMERGENCY SOS</strong><span>Active</span></div>
          <dl>
            <div><dt>Activated</dt><dd>{new Date(vehicle.emergency_sos.activated_at).toLocaleString()}</dd></div>
            <div><dt>Source</dt><dd>Physical emergency button</dd></div>
          </dl>
        </section>
      )}

      {!telemetry ? (
        <section className="vehicle-status-empty"><h2>No telemetry received</h2><p>Current position and vehicle readings are unavailable.</p></section>
      ) : (
        <div className="vehicle-status-grid">
          <section>
            <header><h2>Position</h2>{telemetry.position_source === "CELLULAR_LBS" && <strong>Approximate cellular location</strong>}{telemetry.position_source === "SIMULATED_TEST" && <strong className="vehicle-status-simulated">SIMULATED TEST POSITION DATA</strong>}</header>
            <dl>
              <div><dt>Latitude</dt><dd>{value(telemetry.latitude)}</dd></div>
              <div><dt>Longitude</dt><dd>{value(telemetry.longitude)}</dd></div>
              <div><dt>GNSS speed</dt><dd>{telemetry.position_source === "GNSS" ? value(telemetry.speed_kph, " km/h") : unavailable}</dd></div>
              <div><dt>Position source</dt><dd>{telemetry.position_source === "SIMULATED_TEST" ? "SIMULATED TEST DATA" : telemetry.position_source ? words(telemetry.position_source) : unavailable}</dd></div>
              <div><dt>Position accuracy</dt><dd>{telemetry.position_accuracy_m == null ? unavailable : `~${telemetry.position_accuracy_m} m`}</dd></div>
            </dl>
          </section>

          <section>
            <header><h2>Engine / OBD</h2>{telemetry.obd_source === "SIMULATED_TEST" && <strong className="vehicle-status-simulated">SIMULATED TEST OBD DATA</strong>}</header>
            <dl>
              <div><dt>Engine RPM</dt><dd>{value(telemetry.rpm)}</dd></div>
              <div><dt>Engine load</dt><dd>{value(telemetry.engine_load_pct, "%")}</dd></div>
              <div><dt>Coolant temperature</dt><dd>{value(telemetry.coolant_c, " °C")}</dd></div>
            </dl>
          </section>

          <section>
            <header><h2>Driver Behavior</h2></header>
            <dl><div><dt>Current event</dt><dd>{telemetry.driving_event ? words(telemetry.driving_event) : "No event"}</dd></div></dl>
          </section>
        </div>
      )}
    </aside>
    </div>
  );
}
