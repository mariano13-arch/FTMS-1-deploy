import { useEffect, useState } from "react";
import LiveVehicleMap from "./components/LiveVehicleMap";
import { useVehicleStatus } from "./hooks/useVehicleStatus";
import { getHealth } from "./services/health";
import "./styles.css";

type ConnectionState = "loading" | "connected" | "error";
const pilotDeviceId = "LILYGO-001";

function formatValue(value: number | null, suffix: string) {
  return value === null ? "Unavailable" : `${value.toLocaleString()} ${suffix}`;
}

export default function App() {
  const [connection, setConnection] = useState<ConnectionState>("loading");
  const [currentTime, setCurrentTime] = useState(() => Date.now());
  const { status: vehicle, requestState, realtimeState } =
    useVehicleStatus(pilotDeviceId);

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

  const latest = vehicle?.latest ?? null;

  useEffect(() => {
    const interval = window.setInterval(() => setCurrentTime(Date.now()), 1_000);
    return () => window.clearInterval(interval);
  }, []);

  const isStale =
    latest !== null && currentTime - Date.parse(latest.recorded_at) > 60_000;
  const realtimeLabel = {
    connecting: "Connecting",
    live: "Live",
    reconnecting: "Reconnecting / REST fallback",
    disconnected: "Disconnected",
  }[realtimeState];

  return (
    <main>
      <section className="shell" aria-labelledby="page-title">
        <p className="eyebrow">Sprint 2 Real-Time Tracking</p>
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
        <p className={`realtime realtime--${realtimeState}`}>
          Real-time status: {realtimeLabel}
        </p>

        <article className="pilot-card" aria-labelledby="pilot-title">
          <div className="pilot-card__header">
            <div>
              <p className="pilot-card__label">Live MQTT/WebSocket pilot</p>
              <h2 id="pilot-title">Simulated Pilot Data</h2>
            </div>
            <span className="pilot-card__device">{pilotDeviceId}</span>
          </div>

          {connection === "loading" && <p>Loading backend connection…</p>}
          {connection === "error" && (
            <p className="message message--error">Backend unavailable.</p>
          )}
          {connection === "connected" && requestState === "loading" && (
            <p>Loading vehicle status…</p>
          )}
          {connection === "connected" && requestState === "error" && !vehicle && (
            <p className="message message--error">Latest-status request failed.</p>
          )}
          {connection === "connected" &&
            requestState === "ready" &&
            vehicle &&
            !latest && <p>Waiting for the first telemetry event…</p>}
          {connection === "connected" && vehicle && latest && (
            <>
              <div className="vehicle-identity">
                <strong>{vehicle.vehicle.display_name}</strong>
                <span>{vehicle.vehicle.plate_number}</span>
                <span className={isStale ? "freshness--stale" : "freshness--fresh"}>
                  {isStale ? "Stale telemetry" : "Fresh telemetry"}
                </span>
              </div>
              <dl className="telemetry-grid">
                <div><dt>Speed</dt><dd>{formatValue(latest.gnss_speed_kph, "km/h")}</dd></div>
                <div><dt>RPM</dt><dd>{formatValue(latest.rpm, "rpm")}</dd></div>
                <div><dt>Coolant</dt><dd>{formatValue(latest.coolant_c, "°C")}</dd></div>
                <div><dt>Engine load</dt><dd>{formatValue(latest.engine_load_pct, "%")}</dd></div>
                <div><dt>Driving event</dt><dd>{latest.driving_event.replaceAll("_", " ")}</dd></div>
                <div><dt>Position</dt><dd>{latest.latitude.toFixed(4)}, {latest.longitude.toFixed(4)}</dd></div>
                <div className="telemetry-grid__wide"><dt>Recorded at</dt><dd>{new Date(latest.recorded_at).toLocaleString()}</dd></div>
                <div className="telemetry-grid__wide"><dt>Received at</dt><dd>{new Date(latest.received_at).toLocaleString()}</dd></div>
              </dl>
            </>
          )}
        </article>
        <LiveVehicleMap latest={latest} />
      </section>
    </main>
  );
}
