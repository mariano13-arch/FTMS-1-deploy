import { useEffect, useState } from "react";
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
  onKeepSeparate,
  onConfirm,
  onPrepare,
  currentRequestNumber,
}: {
  loading: boolean;
  result: ConsolidationResponse | null;
  plan: DispatchPlan | null;
  busy: boolean;
  onKeepSeparate: () => void;
  onConfirm: () => void;
  onPrepare: () => void;
  currentRequestNumber: string;
}) {
  const suggestion = result?.recommendation;
  const [reviewing, setReviewing] = useState(false);
  useEffect(() => setReviewing(false), [suggestion?.recommendation_token]);
  const compatible = suggestion?.requests.filter(
    (item) => item.request_number !== currentRequestNumber,
  ) ?? [];
  if (loading || (!plan && !suggestion)) return null;
  return (
    <section className="dispatch-consolidation">
      <h3>Consolidation Opportunity</h3>
      {plan ? (
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
          <strong>{suggestion.requests.length} compatible delivery requests</strong>
          <div className="dispatch-consolidation-context">
            <p><b>Current request</b><span>{currentRequestNumber}</span></p>
            <p><b>Can be consolidated with</b><span>{compatible.map((item) => item.request_number).join(" · ")}</span></p>
          </div>
          <dl className="dispatch-consolidation-summary">
            <Metric name="Vehicle" value={suggestion.vehicle.display_name} detail={suggestion.vehicle.plate_number} />
            <Metric name="Driver" value={suggestion.driver.full_name} detail={suggestion.driver.driver_code} />
            <Metric name="Separate travel" value={duration(suggestion.route.separate.travel_time_seconds)} />
            <Metric name="Consolidated travel" value={duration(suggestion.route.consolidated.travel_time_seconds)} />
            <Metric name="Estimated reduction" value={duration(suggestion.route.difference.travel_time_seconds)} detail={distance(suggestion.route.difference.distance_meters)} />
          </dl>
          <h4>Pickup/Delivery Sequence</h4>
          <ol>
            {suggestion.route.stops.map((stop) => (
              <li key={`${stop.sequence}-${stop.request_id}`}>
                {stop.sequence}. {label(stop.stop_type)} · {stop.request_number}{" "}
                · {stop.label} · {Number(stop.load_change_kg) > 0 ? "+" : ""}
                {stop.load_change_kg} kg
              </li>
            ))}
          </ol>
          {!reviewing ? (
            <button className="btn-action--filled" onClick={() => setReviewing(true)}>
              Review Consolidation
            </button>
          ) : <div className="dispatch-consolidation-review">
            <dl>
              <Metric name="Peak load" value={`${suggestion.route.peak_load_kg} / ${suggestion.route.capacity_kg} kg`} detail={`${suggestion.route.capacity_utilization_percent}% capacity utilization`} />
              <Metric name="Separate distance" value={distance(suggestion.route.separate.distance_meters)} />
              <Metric name="Consolidated distance" value={distance(suggestion.route.consolidated.distance_meters)} />
            </dl>
            <h4>Why consolidate?</h4>
            <ul>{suggestion.explanation.map((item) => <li key={item}>{item}</li>)}</ul>
            <p className="dispatch-state-note">Multi-stop geometry unavailable; no route line is drawn. Metrics use the TomTom road matrix.</p>
            <div className="dispatch-consolidation-actions">
              <button className="btn-cancel" onClick={onKeepSeparate}>Keep Separate</button>
              <button className="btn-confirm" disabled={busy} onClick={onConfirm}>Confirm Consolidation</button>
            </div>
          </div>}
        </>
      ) : null}
    </section>
  );
}
