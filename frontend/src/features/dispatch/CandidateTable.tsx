import type { CandidateComparison, RecommendationResponse } from "../../services/dispatch";
import { humanize as label } from "../../utils/text";

const duration = (seconds: number | null) =>
  seconds === null ? "Unavailable" : `${Math.ceil(seconds / 60)} min`;
const distance = (meters: number | null) =>
  meters === null
    ? "Unavailable"
    : meters >= 1000
      ? `${(meters / 1000).toFixed(1)} km`
      : `${meters} m`;

export default function CandidateTable({
  items,
  exclusions,
  limited,
}: {
  items: CandidateComparison[];
  exclusions: RecommendationResponse["excluded_candidates"][string];
  limited: boolean;
}) {
  return (
    <section className="dispatch-candidates">
      <h3>Candidate Comparison</h3>
      {items.length === 0 ? (
        <p>No feasible GIS candidates available.</p>
      ) : (
        <div>
          <table>
            <thead>
              <tr>
                <th>Driver</th>
                <th>Vehicle</th>
                <th>Type / Capacity</th>
                <th>Travel / Distance</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={`${item.driver.id}-${item.vehicle.id}-${index}`}>
                  <td>
                    {item.driver.full_name}
                    <small>ELIGIBLE</small>
                  </td>
                  <td>
                    {item.vehicle.display_name}
                    <small>{item.vehicle.plate_number}</small>
                  </td>
                  <td>
                    {label(item.vehicle.vehicle_type)}
                    <small>{item.vehicle.passenger_capacity ?? "—"} pax</small>
                  </td>
                  <td>
                    {duration(item.travel_time_seconds)}
                    <small>
                      {distance(item.distance_meters)}
                      {item.traffic_delay_seconds
                        ? ` · +${duration(item.traffic_delay_seconds)}`
                        : ""}
                    </small>
                  </td>
                  <td>{item.result}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {exclusions.length > 0 && (
        <div className="dispatch-exclusions">
          <strong>Why excluded</strong>
          {exclusions.map((item) => (
            <p key={`${item.kind}-${item.code}`}>
              <b>{item.name}</b>
              <span>{label(item.reason)}</span>
            </p>
          ))}
        </div>
      )}
      {limited && (
        <small>
          Comparison is limited to the first validated candidates within the
          matrix scope.
        </small>
      )}
    </section>
  );
}
