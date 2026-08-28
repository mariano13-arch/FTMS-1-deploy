import LoadingIndicator from "../../components/common/LoadingIndicator";
import type { ConsolidationResponse, DispatchPlan } from "../../services/dispatch";
import { humanize as label } from "../../utils/text";

const duration = (seconds: number | null) =>
  seconds === null ? "Unavailable" : `${Math.ceil(seconds / 60)} min`;
const distance = (meters: number | null) =>
  meters === null
    ? "Unavailable"
    : meters >= 1000
      ? `${(meters / 1000).toFixed(1)} km`
      : `${meters} m`;

function Metric({
  name,
  value,
  detail,
}: {
  name: string;
  value: string;
  detail?: string;
}) {
  return (
    <div>
      <dt>{name}</dt>
      <dd>
        {value}
        {detail && <small>{detail}</small>}
      </dd>
    </div>
  );
}

export default function SmartConsolidation({
  loading,
  result,
  plan,
  busy,
  onAnalyze,
  onKeepSeparate,
  onConfirm,
  onPrepare,
}: {
  loading: boolean;
  result: ConsolidationResponse | null;
  plan: DispatchPlan | null;
  busy: boolean;
  onAnalyze: () => void;
  onKeepSeparate: () => void;
  onConfirm: () => void;
  onPrepare: () => void;
}) {
  const suggestion = result?.recommendation;
  return (
    <section className="dispatch-consolidation">
      <h3>Smart Consolidation</h3>
      {loading ? (
        <LoadingIndicator variant="card" message="Analyzing consolidation…" />
      ) : plan ? (
        <>
          <strong>Confirmed Consolidated Dispatch</strong>
          <p>
            {plan.stops.length / 2} requests · {plan.driver.full_name} ·{" "}
            {plan.vehicle.display_name}
          </p>
          <ol>
            {plan.stops.map((stop) => (
              <li key={`${stop.sequence}-${stop.transport_request_id}`}>
                {stop.sequence}. {label(stop.stop_type)} · {stop.request_number}{" "}
                · {stop.label}
              </li>
            ))}
          </ol>
          <button className="btn-confirm" disabled={busy} onClick={onPrepare}>
            Prepare Consolidated Dispatch
          </button>
        </>
      ) : suggestion ? (
        <>
          <strong>Optimized consolidation recommendation</strong>
          <p>
            {suggestion.requests.map((item) => item.request_number).join(" + ")}
          </p>
          <dl>
            <Metric name="Driver" value={suggestion.driver.full_name} />
            <Metric
              name="Vehicle"
              value={suggestion.vehicle.display_name}
              detail={suggestion.vehicle.plate_number}
            />
            <Metric
              name="Peak load"
              value={`${suggestion.route.peak_load_kg} / ${suggestion.route.capacity_kg} kg`}
              detail={`${suggestion.route.capacity_utilization_percent}%`}
            />
            <Metric
              name="Planned stops"
              value={String(suggestion.route.stops.length)}
            />
            <Metric
              name="Separate"
              value={`${suggestion.route.separate.vehicles} vehicles · ${distance(suggestion.route.separate.distance_meters)} · ${duration(suggestion.route.separate.travel_time_seconds)}`}
            />
            <Metric
              name="Consolidated"
              value={`${suggestion.route.consolidated.vehicles} vehicle · ${distance(suggestion.route.consolidated.distance_meters)} · ${duration(suggestion.route.consolidated.travel_time_seconds)}`}
            />
            <Metric
              name="Potential reduction"
              value={`${suggestion.route.difference.vehicles} vehicle · ${distance(suggestion.route.difference.distance_meters)} · ${duration(suggestion.route.difference.travel_time_seconds)}`}
            />
          </dl>
          <h4>Planned Stops</h4>
          <ol>
            {suggestion.route.stops.map((stop) => (
              <li key={`${stop.sequence}-${stop.request_id}`}>
                {stop.sequence}. {label(stop.stop_type)} · {stop.request_number}{" "}
                · {stop.label} · {Number(stop.load_change_kg) > 0 ? "+" : ""}
                {stop.load_change_kg} kg
              </li>
            ))}
          </ol>
          <h4>Why consolidate?</h4>
          <ul>
            {suggestion.explanation.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p className="dispatch-state-note">
            Multi-stop geometry unavailable; no route line is drawn. Metrics use
            the TomTom road matrix.
          </p>
          <div className="dispatch-consolidation-actions">
            <button className="btn-cancel" onClick={onKeepSeparate}>
              Keep Separate
            </button>
            <button className="btn-confirm" disabled={busy} onClick={onConfirm}>
              Confirm Consolidation
            </button>
          </div>
        </>
      ) : result ? (
        <>
          <p>No feasible consolidation opportunity.</p>
          {result.exclusions.length > 0 && (
            <>
              <h4>Why not?</h4>
              <ul>
                {result.exclusions.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          )}
          <button className="btn-action--filled" onClick={onAnalyze}>
            Analyze Consolidation
          </button>
        </>
      ) : (
        <button className="btn-action--filled" onClick={onAnalyze}>
          Analyze Consolidation
        </button>
      )}
    </section>
  );
}
