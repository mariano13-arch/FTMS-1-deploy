import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, Download, Printer, RefreshCw, X } from "lucide-react";
import LoadingIndicator from "../../components/common/LoadingIndicator";
import {
  downloadDispatchTripCsv,
  fetchDispatchTripReport,
  type DispatchReportFilters,
  type DispatchReportRow,
  type DispatchTripReport,
} from "./api";
import "./reports.css";

function manilaDate(offset = 0) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Manila",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(Date.now() + offset * 86400000));
  const get = (type: string) =>
    parts.find((part) => part.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}
const initial = (): DispatchReportFilters => ({
  date_from: manilaDate(-29),
  date_to: manilaDate(),
  page: 1,
  page_size: 15,
});
const dateTime = (value: string | null) =>
  value
    ? new Date(value).toLocaleString("en-PH", {
        timeZone: "Asia/Manila",
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "—";
const duration = (seconds: number | null) =>
  seconds === null
    ? "—"
    : `${Math.floor(seconds / 3600) ? `${Math.floor(seconds / 3600)}h ` : ""}${Math.floor((seconds % 3600) / 60)}m`;

function DetailDrawer({
  row,
  close,
}: {
  row: DispatchReportRow;
  close: () => void;
}) {
  const stages = [
    ["Confirmed", row.confirmed_at],
    ["Accepted", row.accepted_at],
    ["Execution started", row.execution_started_at],
    ["Pickup arrived", row.pickup_arrived_at],
    ["Pickup departed", row.pickup_departed_at],
    ["Destination arrived", row.destination_arrived_at],
    ["Completed", row.completed_at],
  ] as const;
  const durations = [
    ["Assignment → Acceptance", "assignment_to_acceptance"],
    ["Acceptance → Start", "acceptance_to_start"],
    ["Start → Pickup", "start_to_pickup"],
    ["Pickup Dwell", "pickup_dwell"],
    ["Pickup → Destination", "pickup_to_destination"],
    ["Destination → Completion", "destination_to_completion"],
    ["Execution Duration", "execution_duration"],
    ["Assignment → Completion", "assignment_to_completion"],
  ] as const;
  return (
    <div className="report-drawer-backdrop" onMouseDown={close}>
      <aside
        className="report-drawer"
        aria-label="Assignment details"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <small>Dispatch assignment</small>
            <h2>{row.request_number}</h2>
            <span>{row.execution_status_label}</span>
          </div>
          <button aria-label="Close details" onClick={close}>
            <X />
          </button>
        </header>
        <div className="report-drawer-body">
          <section>
            <h3>Assignment</h3>
            <dl>
              <div>
                <dt>Request</dt>
                <dd>
                  <Link to={`/transport-requests/${row.request_id}`}>
                    {row.request_number}
                  </Link>
                </dd>
              </div>
              <div>
                <dt>Selection</dt>
                <dd>{row.selection_mode_label}</dd>
              </div>
              <div>
                <dt>Manual override reason</dt>
                <dd>{row.manual_override_reason || "—"}</dd>
              </div>
              <div>
                <dt>Confirmed by</dt>
                <dd>{row.confirmed_by}</dd>
              </div>
            </dl>
          </section>
          <section>
            <h3>Driver & vehicle</h3>
            <dl>
              <div>
                <dt>Driver</dt>
                <dd>
                  {row.driver.name} · {row.driver.code}
                </dd>
              </div>
              <div>
                <dt>Vehicle</dt>
                <dd>
                  {row.vehicle.name} · {row.vehicle.identifier}
                </dd>
              </div>
            </dl>
          </section>
          <section>
            <h3>Execution</h3>
            <dl>
              {stages.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{dateTime(value)}</dd>
                </div>
              ))}
            </dl>
          </section>
          <section>
            <h3>Durations</h3>
            <dl>
              {durations.map(([label, key]) => (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>{duration(row.durations[key])}</dd>
                </div>
              ))}
            </dl>
          </section>
        </div>
      </aside>
    </div>
  );
}

export default function DispatchTripReportPage() {
  const [filters, setFilters] = useState<DispatchReportFilters>(initial);
  const [preset, setPreset] = useState("30");
  const [report, setReport] = useState<DispatchTripReport | null>(null);
  const [selected, setSelected] = useState<DispatchReportRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    fetchDispatchTripReport(filters)
      .then((value) => {
        if (active) setReport(value);
      })
      .catch(() => {
        if (active) setError("Unable to load this report.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [filters]);
  const setFilter = (
    key: keyof DispatchReportFilters,
    value: string | number | undefined,
  ) => {
    setLoading(true);
    setError("");
    setFilters((old) => ({
      ...old,
      [key]: value || undefined,
      page: key === "page" ? Number(value) : 1,
    }));
  };
  const setRange = (value: string) => {
    setPreset(value);
    if (value !== "custom") {
      setLoading(true);
      setFilters((old) => ({
        ...old,
        date_from: manilaDate(-(Number(value) - 1)),
        date_to: manilaDate(),
        page: 1,
      }));
    }
  };
  return (
    <main className="reports-page transport-report">
      <header className="reports-heading report-title-row">
        <div>
          <p>
            <Link to="/reports">
              <ChevronLeft /> Reports
            </Link>{" "}
            / Dispatch & Trip Execution
          </p>
          <h1>Dispatch & Trip Execution</h1>
        </div>
        <div className="report-actions">
          <button onClick={() => downloadDispatchTripCsv(filters)}>
            <Download /> Export CSV
          </button>
          <button onClick={() => window.print()}>
            <Printer /> Print
          </button>
        </div>
      </header>
      <section className="report-filters" aria-label="Report filters">
        <label>
          Date range
          <select value={preset} onChange={(e) => setRange(e.target.value)}>
            <option value="1">Today</option>
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
            <option value="custom">Custom</option>
          </select>
        </label>
        {preset === "custom" && (
          <>
            <label>
              From
              <input
                type="date"
                value={filters.date_from}
                onChange={(e) => setFilter("date_from", e.target.value)}
              />
            </label>
            <label>
              To
              <input
                type="date"
                value={filters.date_to}
                onChange={(e) => setFilter("date_to", e.target.value)}
              />
            </label>
          </>
        )}
        <label>
          Search
          <input
            value={filters.search ?? ""}
            onChange={(e) => setFilter("search", e.target.value)}
            placeholder="Request, driver, vehicle"
          />
        </label>
        {(
          ["vehicle", "driver", "execution_status", "selection_mode"] as const
        ).map((key) => (
          <label key={key}>
            {key.replace("_", " ")}
            <select
              value={filters[key] ?? ""}
              onChange={(e) => setFilter(key, e.target.value)}
            >
              <option value="">All</option>
              {(key === "vehicle"
                ? report?.choices.vehicles
                : key === "driver"
                  ? report?.choices.drivers
                  : key === "execution_status"
                    ? report?.choices.execution_statuses
                    : report?.choices.selection_modes
              )?.map((choice) => (
                <option value={choice.value} key={choice.value}>
                  {choice.label}
                </option>
              ))}
            </select>
          </label>
        ))}
        <button
          className="report-reset"
          onClick={() => {
            setPreset("30");
            setLoading(true);
            setFilters(initial());
          }}
        >
          <RefreshCw /> Reset
        </button>
      </section>
      {loading && <LoadingIndicator variant="card" message="Loading report…" />}
      {!loading && error && (
        <section className="report-state">
          <p>{error}</p>
          <button
            onClick={() => {
              setLoading(true);
              setError("");
              setFilters((old) => ({ ...old }));
            }}
          >
            Retry
          </button>
        </section>
      )}
      {!loading && report && (
        <>
          <section className="report-metadata">
            <span>
              Generated {dateTime(report.meta.generated_at)} by{" "}
              {report.meta.generated_by}
            </span>
            <span>Timezone: Asia/Manila</span>
            <span>Date basis: Confirmed at</span>
          </section>
          <section className="report-kpis">
            {[
              [
                "Assignments Confirmed",
                String(report.summary.assignments_confirmed),
              ],
              ["Driver Acceptances", String(report.summary.driver_acceptances)],
              [
                "Trips In Progress · Current",
                String(report.summary.trips_in_progress),
              ],
              ["Completed Trips", String(report.summary.completed_trips)],
              [
                "Avg Execution Duration",
                duration(report.summary.average_execution_duration_seconds),
              ],
            ].map(([label, value]) => (
              <article key={label}>
                <strong>{value}</strong>
                <span>{label}</span>
              </article>
            ))}
          </section>
          <section className="report-visuals">
            {[
              [
                "Current Execution Status",
                report.breakdowns.by_execution_status,
              ],
              ["Assignment Selection", report.breakdowns.by_selection_mode],
            ].map(([title, rows]) => (
              <article key={title as string}>
                <h2>{title as string}</h2>
                <div className="breakdown-list">
                  {(
                    rows as DispatchTripReport["breakdowns"]["by_execution_status"]
                  ).map((row) => (
                    <div key={row.value}>
                      <span>{row.label}</span>
                      <strong>{row.count}</strong>
                      <i>
                        <b
                          style={{
                            width: `${
                              (row.count /
                                Math.max(
                                  1,
                                  (
                                    rows as DispatchTripReport["breakdowns"]["by_execution_status"]
                                  ).reduce((sum, item) => sum + item.count, 0),
                                )) *
                              100
                            }%`,
                          }}
                        />
                      </i>
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </section>
          <section className="report-table-card">
            <div className="report-table-heading">
              <div>
                <h2>Assignment details</h2>
                <span>{report.details.count} matching assignments</span>
              </div>
              <label>
                Rows
                <select
                  value={filters.page_size}
                  onChange={(e) =>
                    setFilter("page_size", Number(e.target.value))
                  }
                >
                  <option>15</option>
                  <option>25</option>
                  <option>50</option>
                </select>
              </label>
            </div>
            <div className="report-table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Request</th>
                    <th>Driver</th>
                    <th>Vehicle</th>
                    <th>Selection</th>
                    <th>Execution Status</th>
                    <th>Confirmed</th>
                    <th>Accepted</th>
                    <th>Started</th>
                    <th>Completed</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {report.details.results.map((row) => (
                    <tr key={row.id}>
                      <td>
                        {row.request_number}
                        <small>{row.request_type_label}</small>
                      </td>
                      <td>
                        {row.driver.name}
                        <small>{row.driver.code}</small>
                      </td>
                      <td>
                        {row.vehicle.name}
                        <small>{row.vehicle.identifier}</small>
                      </td>
                      <td>{row.selection_mode_label}</td>
                      <td>{row.execution_status_label}</td>
                      <td>{dateTime(row.confirmed_at)}</td>
                      <td>{dateTime(row.accepted_at)}</td>
                      <td>{dateTime(row.execution_started_at)}</td>
                      <td>{dateTime(row.completed_at)}</td>
                      <td>
                        <button
                          className="report-view"
                          onClick={() => setSelected(row)}
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!report.details.results.length && (
                <p className="empty-report">
                  No dispatch assignments match this range.
                </p>
              )}
            </div>
            <footer>
              <span>
                Showing{" "}
                {report.details.count
                  ? (report.details.page - 1) * report.details.page_size + 1
                  : 0}
                –
                {Math.min(
                  report.details.page * report.details.page_size,
                  report.details.count,
                )}{" "}
                of {report.details.count}
              </span>
              <div>
                <button
                  disabled={report.details.page <= 1}
                  onClick={() => setFilter("page", report.details.page - 1)}
                >
                  Previous
                </button>
                <span>
                  Page {report.details.page} of{" "}
                  {report.details.total_pages || 1}
                </span>
                <button
                  disabled={report.details.page >= report.details.total_pages}
                  onClick={() => setFilter("page", report.details.page + 1)}
                >
                  Next
                </button>
              </div>
            </footer>
          </section>
        </>
      )}
      {selected && (
        <DetailDrawer row={selected} close={() => setSelected(null)} />
      )}
    </main>
  );
}
