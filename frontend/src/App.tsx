import { useEffect, useState } from "react";
import { getHealth } from "./services/health";
import {
  getLatestStatus,
  type LatestStatusResponse,
} from "./services/telemetry";
import "./styles.css";

type ConnectionState = "loading" | "connected" | "error";
type VehicleState = "idle" | "loading" | "ready" | "error";

const pilotDeviceId = "LILYGO-001";

function formatValue(value: number | null, suffix: string) {
  return value === null ? "Unavailable" : `${value.toLocaleString()} ${suffix}`;
}

export default function App() {
  const [connection, setConnection] = useState<ConnectionState>("loading");
  const [vehicleState, setVehicleState] = useState<VehicleState>("idle");
  const [vehicle, setVehicle] = useState<LatestStatusResponse | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal)
      .then(() => setConnection("connected"))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setConnection("error");
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (connection !== "connected") {
      return;
    }

    let active = true;
    let controller: AbortController | null = null;
    const loadStatus = async () => {
      controller?.abort();
      controller = new AbortController();
      setVehicleState((current) => (current === "idle" ? "loading" : current));
      try {
        const result = await getLatestStatus(pilotDeviceId, controller.signal);
        if (active) {
          setVehicle(result);
          setVehicleState("ready");
        }
      } catch (error: unknown) {
        if (
          active &&
          !(error instanceof DOMException && error.name === "AbortError")
        ) {
          setVehicleState("error");
        }
      }
    };

    void loadStatus();
    const pollId = window.setInterval(() => void loadStatus(), 5_000);
    return () => {
      active = false;
      window.clearInterval(pollId);
      controller?.abort();
    };
  }, [connection]);

  const latest = vehicle?.latest;

  return (
    <main>
      <section className="shell" aria-labelledby="page-title">
        <p className="eyebrow">Sprint 1 Telemetry Vertical Slice</p>
        <h1 id="page-title">Fleet and Transportation Management System</h1>
        <div className={`status status--${connection}`} role="status" aria-live="polite">
          <span className="status__indicator" aria-hidden="true" />
          <span>
            Backend connection:{" "}
            {connection === "loading"
              ? "Loading"
              : connection === "connected"
                ? "Connected"
                : "Error"}
          </span>
        </div>

        <article className="pilot-card" aria-labelledby="pilot-title">
          <div className="pilot-card__header">
            <div>
              <p className="pilot-card__label">Live REST pilot</p>
              <h2 id="pilot-title">Simulated Pilot Data</h2>
            </div>
            <span className="pilot-card__device">{pilotDeviceId}</span>
          </div>

          {connection === "loading" && <p>Loading backend connection…</p>}
          {connection === "error" && (
            <p className="message message--error">Backend unavailable.</p>
          )}
          {connection === "connected" && vehicleState === "loading" && (
            <p>Loading vehicle status…</p>
          )}
          {connection === "connected" && vehicleState === "error" && (
            <p className="message message--error">Latest-status request failed.</p>
          )}
          {connection === "connected" &&
            vehicleState === "ready" &&
            vehicle &&
            !latest && <p>Waiting for the first telemetry event…</p>}
          {connection === "connected" && vehicleState === "ready" && latest && (
            <>
              <div className="vehicle-identity">
                <strong>{vehicle.vehicle.display_name}</strong>
                <span>{vehicle.vehicle.plate_number}</span>
              </div>
              <dl className="telemetry-grid">
                <div>
                  <dt>Speed</dt>
                  <dd>{formatValue(latest.gnss_speed_kph, "km/h")}</dd>
                </div>
                <div>
                  <dt>RPM</dt>
                  <dd>{formatValue(latest.rpm, "rpm")}</dd>
                </div>
                <div>
                  <dt>Coolant</dt>
                  <dd>{formatValue(latest.coolant_c, "°C")}</dd>
                </div>
                <div>
                  <dt>Engine load</dt>
                  <dd>{formatValue(latest.engine_load_pct, "%")}</dd>
                </div>
                <div>
                  <dt>Driving event</dt>
                  <dd>{latest.driving_event.replaceAll("_", " ")}</dd>
                </div>
                <div>
                  <dt>Position</dt>
                  <dd>
                    {latest.latitude.toFixed(4)}, {latest.longitude.toFixed(4)}
                  </dd>
                </div>
                <div className="telemetry-grid__wide">
                  <dt>Recorded at</dt>
                  <dd>{new Date(latest.recorded_at).toLocaleString()}</dd>
                </div>
                <div className="telemetry-grid__wide">
                  <dt>Received at</dt>
                  <dd>{new Date(latest.received_at).toLocaleString()}</dd>
                </div>
              </dl>
            </>
          )}
        </article>
      </section>
    </main>
  );
}
