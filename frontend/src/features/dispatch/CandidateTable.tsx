import { useEffect, useMemo, useState } from "react";
import type {
  CandidateComparison,
  FuelEstimate,
  RecommendationResponse,
} from "../../services/dispatch";
import { humanize as label } from "../../utils/text";

const PAGE_SIZE = 10;
const duration = (seconds: number | null) =>
  seconds === null ? "Unavailable" : `${Math.ceil(seconds / 60)} min`;
const distance = (meters: number | null) =>
  meters === null
    ? "Unavailable"
    : meters >= 1000
      ? `${(meters / 1000).toFixed(1)} km`
      : `${meters} m`;
const basisLabels: Record<string, string> = {
  CURRENT_AI: "Current AI",
  HISTORICAL_AI_BASELINE: "Historical AI Baseline",
  FLEET_REFERENCE_BASELINE: "Fleet Reference Baseline",
  UNAVAILABLE: "Unavailable",
};
const compactBasisLabels: Record<string, string> = {
  CURRENT_AI: "Current AI",
  HISTORICAL_AI_BASELINE: "Historical AI",
  FLEET_REFERENCE_BASELINE: "Fleet Reference",
  UNAVAILABLE: "Unavailable",
};
const gradeLabels: Record<string, string> = {
  UNLEADED_91: "Unleaded 91",
  PREMIUM_95: "Premium 95",
  PREMIUM_97: "Premium 97",
  REGULAR_DIESEL: "Regular Diesel",
  PREMIUM_DIESEL: "Premium Diesel",
};
const reasonLabels: Record<string, string> = {
  FUEL_GRADE_NOT_RECORDED: "Fuel grade not recorded",
  NO_VALID_PREFERRED_PARTNER_PRICE: "No valid Shell partner price",
  INSUFFICIENT_ELIGIBLE_SAME_VEHICLE_HISTORY: "Insufficient vehicle fuel history",
  FUEL_RATE_UNAVAILABLE: "Fuel rate unavailable",
  INVALID_TRAVEL_DURATION: "Travel duration unavailable",
  INVALID_TRAFFIC_AWARE_TRAVEL_TIME: "Travel duration unavailable",
};
const value = (input: string | null | undefined, suffix: string) =>
  input ? `${input}${suffix}` : "Unavailable";
export const fuelBasisLabel = (basis: string | null | undefined) =>
  basisLabels[basis ?? ""] ?? "Unavailable";
export const fuelGradeLabel = (grade: string | null | undefined) =>
  gradeLabels[grade ?? ""] ?? "Not recorded";
export const fuelReasonLabel = (reason: string | null | undefined) =>
  reasonLabels[reason ?? ""] ?? "Fuel information unavailable";

export function FuelAdvisory({ estimate }: { estimate: FuelEstimate }) {
  const historicalDetail =
    estimate.fuel_rate_basis === "HISTORICAL_AI_BASELINE" &&
    (estimate.history_sample_count ?? 0) > 0
      ? `Based on ${estimate.history_sample_count} vehicle predictions`
      : estimate.fuel_rate_basis === "FLEET_REFERENCE_BASELINE"
        ? "Configured fleet reference"
        : undefined;
  return (
    <section className="dispatch-fuel-advisory" aria-label="Fuel and Cost">
      <h3>Fuel &amp; Cost</h3>
      <dl>
        <div><dt>Fuel Rate</dt><dd>{value(estimate.fuel_rate_lph, " L/h")}</dd></div>
        <div><dt>Rate Basis</dt><dd>{fuelBasisLabel(estimate.fuel_rate_basis)}{historicalDetail && <small>{historicalDetail}</small>}</dd></div>
        <div><dt>Estimated Fuel</dt><dd>{value(estimate.estimated_fuel_liters, " L")}</dd></div>
        <div><dt>Fuel Grade</dt><dd>{fuelGradeLabel(estimate.fuel_grade)}</dd></div>
        <div><dt>Shell Reference Price</dt><dd>{estimate.price_per_liter ? `₱${estimate.price_per_liter}/L` : "Unavailable"}{estimate.price_provider === "ShellPH" && <small>Shell</small>}</dd></div>
        <div><dt>Estimated Fuel Cost</dt><dd>{estimate.estimated_fuel_cost_php ? `₱${estimate.estimated_fuel_cost_php}` : "Unavailable"}</dd></div>
      </dl>
      {estimate.status === "UNAVAILABLE" && <p>{fuelReasonLabel(estimate.reason)}</p>}
    </section>
  );
}
const reasonLabel = (reason: string) => ({
  NUMBER_CODING_RESTRICTION: "Number Coding Restriction",
  NUMBER_CODING_UNKNOWN: "Number Coding Needs Verification",
}[reason] ?? label(reason));
const reasonSummary = (reason: string) => ({
  NUMBER_CODING_RESTRICTION: "Number coding restriction applies for the scheduled pickup time.",
  NUMBER_CODING_UNKNOWN: "Number coding eligibility could not be verified.",
}[reason]);

function Pagination({
  page,
  total,
  onPage,
}: {
  page: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const start = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  return (
    <nav className="dispatch-pagination" aria-label="Pagination">
      <span>
        Showing {start}–{Math.min(page * PAGE_SIZE, total)} of {total}
      </span>
      <div>
        <button
          type="button"
          onClick={() => onPage(page - 1)}
          disabled={page === 1}
        >
          Previous
        </button>
        <span>
          Page {page} of {pages}
        </span>
        <button
          type="button"
          onClick={() => onPage(page + 1)}
          disabled={page === pages}
        >
          Next
        </button>
      </div>
    </nav>
  );
}

export default function CandidateTable({
  items,
  limited,
}: {
  items: CandidateComparison[];
  limited: boolean;
}) {
  const [page, setPage] = useState(1);
  useEffect(() => setPage(1), [items]);
  const visible = items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  return (
    <section className="dispatch-candidates" aria-label="Candidate Comparison">
      <div className="dispatch-candidate-summary">
        <span>
          <b>{items.length}</b> candidate pairs
        </span>
        <span>
          <b>{new Set(items.map((item) => item.driver.id)).size}</b> eligible
          drivers
        </span>
        <span>
          <b>{new Set(items.map((item) => item.vehicle.id)).size}</b> eligible
          vehicles
        </span>
      </div>
      {items.length === 0 ? (
        <p>No feasible GIS candidates available.</p>
      ) : (
        <>
          <div className="dispatch-table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Driver</th>
                  <th>Vehicle</th>
                  <th>Type / Capacity</th>
                  <th>Travel / Distance</th>
                  <th>Fuel</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((item, index) => (
                  <tr
                    key={`${item.driver.id}-${item.vehicle.id}-${(page - 1) * PAGE_SIZE + index}`}
                  >
                    <td>
                      {item.driver.full_name}
                      <small>{item.driver.driver_code} · ELIGIBLE</small>
                    </td>
                    <td>
                      {item.vehicle.display_name}
                      <small>{item.vehicle.plate_number}</small>
                    </td>
                    <td>
                      {label(item.vehicle.vehicle_type)}
                      <small>
                        {item.vehicle.passenger_capacity ?? "—"} pax
                      </small>
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
                    <td className="dispatch-candidate-fuel">
                      {value(item.fuel_estimate?.estimated_fuel_liters, " L")}
                      <small>
                        {item.fuel_estimate?.estimated_fuel_cost_php
                          ? `₱${item.fuel_estimate.estimated_fuel_cost_php} est.`
                          : "Cost unavailable"}
                      </small>
                      <small>
                        {compactBasisLabels[item.fuel_estimate?.fuel_rate_basis ?? ""] ?? "Unavailable"}
                      </small>
                    </td>
                    <td>
                      <span
                        className={`dispatch-result dispatch-result--${item.result.toLowerCase()}`}
                      >
                        {label(item.result)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} total={items.length} onPage={setPage} />
        </>
      )}
      {limited && (
        <small>
          Comparison is limited to the validated candidates returned within the
          matrix scope.
        </small>
      )}
    </section>
  );
}

type Exclusion = RecommendationResponse["excluded_candidates"][string][number];

export function ExclusionsPanel({ items }: { items: Exclusion[] }) {
  const groups = useMemo(() => {
    const grouped = new Map<
      string,
      { kind: Exclusion["kind"]; reason: string; items: Exclusion[] }
    >();
    for (const item of items) {
      const key = `${item.kind}:${item.reason}`;
      const group = grouped.get(key) ?? {
        kind: item.kind,
        reason: item.reason,
        items: [],
      };
      if (!group.items.some((entry) => entry.code === item.code))
        group.items.push(item);
      grouped.set(key, group);
    }
    return [...grouped.values()];
  }, [items]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [pages, setPages] = useState<Record<string, number>>({});
  useEffect(() => {
    setExpanded(null);
    setPages({});
  }, [items]);
  return (
    <section className="dispatch-exclusion-groups" aria-label="Exclusions">
      {(["DRIVER", "VEHICLE"] as const).map((kind) => {
        const kindGroups = groups.filter((group) => group.kind === kind);
        return (
          <div key={kind}>
            <h3>Excluded {kind === "DRIVER" ? "Drivers" : "Vehicles"}</h3>
            {kindGroups.length === 0 ? (
              <p>No excluded {kind === "DRIVER" ? "drivers" : "vehicles"}.</p>
            ) : (
              kindGroups.map((group) => {
                const key = `${kind}:${group.reason}`;
                const open = expanded === key;
                const page = pages[key] ?? 1;
                return (
                  <article key={key}>
                    <button
                      type="button"
                      aria-expanded={open}
                      onClick={() => setExpanded(open ? null : key)}
                    >
                      <span>{reasonLabel(group.reason)}</span>
                      <b>{group.items.length}</b>
                      <small>
                        {open
                          ? "Hide details"
                          : `View ${kind === "DRIVER" ? "drivers" : "vehicles"}`}
                      </small>
                    </button>
                    {open && (
                      <div className="dispatch-exclusion-list">
                        {reasonSummary(group.reason) && <p><span>{reasonSummary(group.reason)}</span></p>}
                        {group.items
                          .slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
                          .map((item) => (
                            <p key={item.code}>
                              <b>{item.name}</b>
                              <small>{item.code}</small>
                              {item.details.map((detail) => (
                                <span key={detail}>{detail}</span>
                              ))}
                            </p>
                          ))}
                        {group.items.length > PAGE_SIZE && (
                          <Pagination
                            page={page}
                            total={group.items.length}
                            onPage={(next) =>
                              setPages((current) => ({
                                ...current,
                                [key]: next,
                              }))
                            }
                          />
                        )}
                      </div>
                    )}
                  </article>
                );
              })
            )}
          </div>
        );
      })}
    </section>
  );
}
