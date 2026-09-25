import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, Download, Printer, RefreshCw, X } from "lucide-react";
import LoadingIndicator from "../../components/common/LoadingIndicator";
import {
  downloadFleetAssignmentCsv,
  fetchFleetAssignmentReport,
  type DriverAssignmentRow,
  type FleetAssignmentFilters,
  type FleetAssignmentReport,
  type ReportBreakdown,
  type VehicleAssignmentRow,
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
const initial = (): FleetAssignmentFilters => ({
  date_from: manilaDate(-29),
  date_to: manilaDate(),
  vehicle_page: 1,
  driver_page: 1,
  page_size: 15,
});
const displayDate = (value: string | null | undefined) =>
  value
    ? new Date(value).toLocaleString("en-PH", {
        timeZone: "Asia/Manila",
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "—";

function Breakdown({
  title,
  rows,
}: {
  title: string;
  rows: ReportBreakdown[];
}) {
  const total = Math.max(
    1,
    rows.reduce((sum, row) => sum + row.count, 0),
  );
  return (
    <article>
      <h2>{title}</h2>
      <div className="breakdown-list">
        {rows.length ? (
          rows.map((row) => (
            <div key={row.value}>
              <span>{row.label}</span>
              <strong>{row.count}</strong>
              <i>
                <b style={{ width: `${(row.count / total) * 100}%` }} />
              </i>
            </div>
          ))
        ) : (
          <p>No assignments match this report period.</p>
        )}
      </div>
    </article>
  );
}

function Drawer({
  item,
  close,
}: {
  item: VehicleAssignmentRow | DriverAssignmentRow;
  close: () => void;
}) {
  const vehicle = "identifier" in item;
  const current = item.current_assignment;
  const latest = item.latest_assignment;
  return (
    <div className="report-drawer-backdrop" onMouseDown={close}>
      <aside
        className="report-drawer"
        aria-label={`${vehicle ? "Vehicle" : "Driver"} assignment details`}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <small>
              {vehicle
                ? "Vehicle assignment summary"
                : "Driver assignment summary"}
            </small>
            <h2>{item.name}</h2>
            <span>{vehicle ? item.identifier : item.driver_code}</span>
          </div>
          <button aria-label="Close details" onClick={close}>
            <X />
          </button>
        </header>
        <div className="report-drawer-body">
          <section>
            <h3>
              {vehicle ? "Vehicle · Current state" : "Driver · Current state"}
            </h3>
            {vehicle ? (
              <dl>
                <div>
                  <dt>Identifier</dt>
                  <dd>{item.identifier}</dd>
                </div>
                <div>
                  <dt>Type</dt>
                  <dd>{item.vehicle_type_label}</dd>
                </div>
                <div>
                  <dt>Active state</dt>
                  <dd>{item.is_active ? "Active" : "Inactive"}</dd>
                </div>
                <div>
                  <dt>Fuel type</dt>
                  <dd>{item.fuel_type_label}</dd>
                </div>
                <div>
                  <dt>Fuel grade</dt>
                  <dd>{item.fuel_grade_label}</dd>
                </div>
                <div>
                  <dt>Capacity</dt>
                  <dd>
                    {item.passenger_capacity
                      ? `${item.passenger_capacity} passengers`
                      : item.payload_capacity_kg
                        ? `${item.payload_capacity_kg} kg payload`
                        : "—"}
                  </dd>
                </div>
              </dl>
            ) : (
              <dl>
                <div>
                  <dt>Driver code</dt>
                  <dd>{item.driver_code}</dd>
                </div>
                <div>
                  <dt>Employment status</dt>
                  <dd>{item.employment_status_label}</dd>
                </div>
              </dl>
            )}
          </section>
          <section>
            <h3>Report period</h3>
            <dl>
              <div>
                <dt>Assignments</dt>
                <dd>{item.assignments}</dd>
              </div>
              <div>
                <dt>Completed trips</dt>
                <dd>{item.completed_trips}</dd>
              </div>
            </dl>
          </section>
          <Assignment
            title="Current assignment · Current state"
            assignment={current}
            counterpart={vehicle ? current?.driver.name : current?.vehicle.name}
          />
          <Assignment
            title="Latest assignment · Report period"
            assignment={latest}
            counterpart={vehicle ? latest?.driver.name : latest?.vehicle.name}
          />
        </div>
      </aside>
    </div>
  );
}
function Assignment({
  title,
  assignment,
  counterpart,
}: {
  title: string;
  assignment: VehicleAssignmentRow["current_assignment"];
  counterpart?: string;
}) {
  return (
    <section>
      <h3>{title}</h3>
      {assignment ? (
        <dl>
          <div>
            <dt>Request</dt>
            <dd>{assignment.request_number}</dd>
          </div>
          <div>
            <dt>Driver / Vehicle</dt>
            <dd>{counterpart}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>{assignment.execution_status_label}</dd>
          </div>
          <div>
            <dt>Confirmed</dt>
            <dd>{displayDate(assignment.confirmed_at)}</dd>
          </div>
          <div>
            <dt>Selection</dt>
            <dd>{assignment.selection_mode_label}</dd>
          </div>
        </dl>
      ) : (
        <p>—</p>
      )}
    </section>
  );
}

export default function FleetAssignmentReportPage() {
  const [filters, setFilters] = useState<FleetAssignmentFilters>(initial);
  const [preset, setPreset] = useState("30");
  const [tab, setTab] = useState<"vehicles" | "drivers">("vehicles");
  const [report, setReport] = useState<FleetAssignmentReport | null>(null);
  const [selected, setSelected] = useState<
    VehicleAssignmentRow | DriverAssignmentRow | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    fetchFleetAssignmentReport(filters)
      .then((data) => {
        if (active) setReport(data);
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
    key: keyof FleetAssignmentFilters,
    value: string | number | undefined,
  ) => {
    setLoading(true);
    setError("");
    setFilters((old) => ({
      ...old,
      [key]: value === "" ? undefined : value,
      [tab === "vehicles" ? "vehicle_page" : "driver_page"]: key.endsWith(
        "_page",
      )
        ? Number(value)
        : 1,
    }));
  };
  const page = report?.[tab];
  const setRange = (value: string) => {
    setPreset(value);
    if (value !== "custom") {
      setLoading(true);
      setFilters((old) => ({
        ...old,
        date_from: manilaDate(-(Number(value) - 1)),
        date_to: manilaDate(),
        vehicle_page: 1,
        driver_page: 1,
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
            / Fleet Assignment Summary
          </p>
          <h1>Fleet Assignment Summary</h1>
        </div>
        <div className="report-actions">
          <button onClick={() => downloadFleetAssignmentCsv(tab, filters)}>
            <Download /> Export {tab === "vehicles" ? "Vehicle" : "Driver"} CSV
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
            <option value="7">Last 7 Days</option>
            <option value="30">Last 30 Days</option>
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
        {tab === "vehicles" ? (
          <>
            <label>
              Search
              <input
                aria-label="Vehicle search"
                placeholder="Name or identifier"
                value={filters.vehicle_search ?? ""}
                onChange={(e) => setFilter("vehicle_search", e.target.value)}
              />
            </label>
            <Select
              label="Vehicle"
              value={filters.vehicle}
              choices={report?.choices.vehicles}
              change={(v) => setFilter("vehicle", v)}
            />
            <Select
              label="Vehicle type"
              value={filters.vehicle_type}
              choices={report?.choices.vehicle_types}
              change={(v) => setFilter("vehicle_type", v)}
            />
            <Select
              label="Active state"
              value={filters.vehicle_active}
              choices={[
                { value: "true", label: "Active" },
                { value: "false", label: "Inactive" },
              ]}
              change={(v) => setFilter("vehicle_active", v)}
            />
          </>
        ) : (
          <>
            <label>
              Search
              <input
                aria-label="Driver search"
                placeholder="Name or driver code"
                value={filters.driver_search ?? ""}
                onChange={(e) => setFilter("driver_search", e.target.value)}
              />
            </label>
            <Select
              label="Driver"
              value={filters.driver}
              choices={report?.choices.drivers}
              change={(v) => setFilter("driver", v)}
            />
            <Select
              label="Employment status"
              value={filters.employment_status}
              choices={report?.choices.employment_statuses}
              change={(v) => setFilter("employment_status", v)}
            />
          </>
        )}
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
              Generated {displayDate(report.meta.generated_at)} by{" "}
              {report.meta.generated_by}
            </span>
            <span>Timezone: Asia/Manila</span>
            <span>
              Period: {report.meta.date_from}–{report.meta.date_to}
            </span>
            <span>Confirmed basis; completed counts use completed at</span>
          </section>
          <section className="report-kpis" aria-label="Report summary">
            {[
              ["Active Vehicles · Current", report.summary.active_vehicles],
              ["Active Drivers · Current", report.summary.active_drivers],
              [
                "Assignments Confirmed · Period",
                report.summary.assignments_confirmed,
              ],
              ["Completed Trips · Period", report.summary.completed_trips],
              [
                "Currently Assigned Vehicles · Current",
                report.summary.currently_assigned_vehicles,
              ],
            ].map(([label, value]) => (
              <article key={label}>
                <strong>{value}</strong>
                <span>{label}</span>
              </article>
            ))}
          </section>
          <section className="report-visuals fleet-assignment-visuals">
            <Breakdown
              title="Assignments by Vehicle"
              rows={report.breakdowns.by_vehicle}
            />
            <Breakdown
              title="Assignments by Driver"
              rows={report.breakdowns.by_driver}
            />
            <Breakdown
              title="Assignments by Vehicle Type"
              rows={report.breakdowns.by_vehicle_type}
            />
          </section>
          <section className="report-table-card">
            <div className="report-detail-tabs">
              <button
                className={tab === "vehicles" ? "active" : ""}
                onClick={() => setTab("vehicles")}
              >
                Vehicles
              </button>
              <button
                className={tab === "drivers" ? "active" : ""}
                onClick={() => setTab("drivers")}
              >
                Drivers
              </button>
            </div>
            <div className="report-table-scroll">
              {tab === "vehicles" ? (
                <VehicleTable
                  rows={report.vehicles.results}
                  view={setSelected}
                />
              ) : (
                <DriverTable rows={report.drivers.results} view={setSelected} />
              )}
              {page && !page.results.length && (
                <p className="empty-report">
                  No {tab} match the selected filters.
                </p>
              )}
            </div>
            {page && (
              <footer>
                <span>
                  Showing{" "}
                  {page.count ? (page.page - 1) * page.page_size + 1 : 0}–
                  {Math.min(page.page * page.page_size, page.count)} of{" "}
                  {page.count}
                </span>
                <label>
                  Rows
                  <select
                    value={page.page_size}
                    onChange={(e) =>
                      setFilter("page_size", Number(e.target.value))
                    }
                  >
                    {[15, 25, 50].map((size) => (
                      <option key={size}>{size}</option>
                    ))}
                  </select>
                </label>
                <div>
                  <button
                    disabled={page.page <= 1}
                    onClick={() =>
                      setFilter(
                        tab === "vehicles" ? "vehicle_page" : "driver_page",
                        page.page - 1,
                      )
                    }
                  >
                    Previous
                  </button>
                  <span>
                    Page {page.page} of {page.total_pages || 1}
                  </span>
                  <button
                    disabled={page.page >= page.total_pages}
                    onClick={() =>
                      setFilter(
                        tab === "vehicles" ? "vehicle_page" : "driver_page",
                        page.page + 1,
                      )
                    }
                  >
                    Next
                  </button>
                </div>
              </footer>
            )}
          </section>
        </>
      )}
      {selected && <Drawer item={selected} close={() => setSelected(null)} />}
    </main>
  );
}

function Select({
  label,
  value,
  choices,
  change,
}: {
  label: string;
  value?: string;
  choices?: { value: string | number; label: string }[];
  change: (value: string) => void;
}) {
  return (
    <label>
      {label}
      <select value={value ?? ""} onChange={(e) => change(e.target.value)}>
        <option value="">All</option>
        {choices?.map((choice) => (
          <option key={choice.value} value={choice.value}>
            {choice.label}
          </option>
        ))}
      </select>
    </label>
  );
}
function VehicleTable({
  rows,
  view,
}: {
  rows: VehicleAssignmentRow[];
  view: (row: VehicleAssignmentRow) => void;
}) {
  return (
    <table>
      <thead>
        <tr>
          <th>Vehicle</th>
          <th>Vehicle Type</th>
          <th>Fuel</th>
          <th>Active State</th>
          <th>Assignments</th>
          <th>Completed Trips</th>
          <th>Current Assignment</th>
          <th>Latest Assignment · Period</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>
              {row.name}
              <small>{row.identifier}</small>
            </td>
            <td>{row.vehicle_type_label}</td>
            <td>{row.fuel_type_label}<small>{row.fuel_grade_label}</small></td>
            <td>{row.is_active ? "Active" : "Inactive"}</td>
            <td>{row.assignments}</td>
            <td>{row.completed_trips}</td>
            <td>
              {row.current_assignment?.request_number ?? "—"}
              <small>{row.current_assignment?.execution_status_label}</small>
            </td>
            <td>
              {row.latest_assignment?.request_number ?? "—"}
              <small>{displayDate(row.latest_assignment?.confirmed_at)}</small>
            </td>
            <td>
              <button className="report-view" onClick={() => view(row)}>
                View
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
function DriverTable({
  rows,
  view,
}: {
  rows: DriverAssignmentRow[];
  view: (row: DriverAssignmentRow) => void;
}) {
  return (
    <table>
      <thead>
        <tr>
          <th>Driver</th>
          <th>Driver Code</th>
          <th>Employment Status</th>
          <th>Assignments</th>
          <th>Completed Trips</th>
          <th>Current Assignment</th>
          <th>Latest Assignment · Period</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>{row.name}</td>
            <td>{row.driver_code}</td>
            <td>{row.employment_status_label}</td>
            <td>{row.assignments}</td>
            <td>{row.completed_trips}</td>
            <td>
              {row.current_assignment?.request_number ?? "—"}
              <small>{row.current_assignment?.vehicle.name}</small>
            </td>
            <td>
              {row.latest_assignment?.request_number ?? "—"}
              <small>{displayDate(row.latest_assignment?.confirmed_at)}</small>
            </td>
            <td>
              <button className="report-view" onClick={() => view(row)}>
                View
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
