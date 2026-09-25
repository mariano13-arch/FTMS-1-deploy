import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, Download, Printer, RefreshCw, X } from "lucide-react";
import LoadingIndicator from "../../components/common/LoadingIndicator";
import {
  downloadInspectionMaintenanceCsv,
  fetchInspectionMaintenanceReport,
  type InspectionMaintenanceFilters,
  type InspectionMaintenanceReport,
  type InspectionRow,
  type MaintenanceRow,
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
const initial = (): InspectionMaintenanceFilters => ({
  date_from: manilaDate(-29),
  date_to: manilaDate(),
  inspection_page: 1,
  maintenance_page: 1,
  page_size: 15,
});
const displayDate = (value: string | null) =>
  value
    ? new Date(
        value.length === 10 ? `${value}T00:00:00+08:00` : value,
      ).toLocaleString("en-PH", {
        timeZone: "Asia/Manila",
        dateStyle: "medium",
        ...(value.length === 10 ? {} : { timeStyle: "short" }),
      })
    : "—";

function Drawer({
  item,
  close,
}: {
  item: InspectionRow | MaintenanceRow;
  close: () => void;
}) {
  const inspection = "checklist" in item;
  return (
    <div className="report-drawer-backdrop" onMouseDown={close}>
      <aside
        className="report-drawer"
        aria-label={`${inspection ? "Inspection" : "Maintenance"} details`}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <small>
              {inspection ? "Vehicle inspection" : "Maintenance record"}
            </small>
            <h2>{inspection ? item.inspection_type_label : item.title}</h2>
            <span>{inspection ? item.result_label : item.status_label}</span>
          </div>
          <button aria-label="Close details" onClick={close}>
            <X />
          </button>
        </header>
        <div className="report-drawer-body">
          <section>
            <h3>Vehicle</h3>
            <p>
              {item.vehicle.name} · {item.vehicle.identifier}
            </p>
          </section>
          {inspection ? (
            <>
              <section>
                <h3>Inspection</h3>
                <p>
                  {displayDate(item.inspection_date)} ·{" "}
                  {item.inspection_type_label} · {item.result_label}
                </p>
                <p>Inspector: {item.inspector}</p>
              </section>
              <section>
                <h3>Readings</h3>
                <p>
                  Odometer: {item.odometer_km ?? "—"} km · Fuel:{" "}
                  {item.fuel_level_percent ?? "—"}%
                </p>
              </section>
              <section>
                <h3>Checklist</h3>
                <dl>
                  {Object.entries(item.checklist).map(([key, value]) => (
                    <div key={key}>
                      <dt>{key.replaceAll("_", " ")}</dt>
                      <dd>{value.label}</dd>
                    </div>
                  ))}
                </dl>
              </section>
              <section>
                <h3>Issues</h3>
                <p>{item.issues_found || "—"}</p>
                <p>{item.notes || "—"}</p>
              </section>
              <section>
                <h3>Related maintenance</h3>
                {item.related_maintenance.length ? (
                  item.related_maintenance.map((row) => (
                    <p key={row.id}>
                      {row.title} · {row.status_label}
                    </p>
                  ))
                ) : (
                  <p>—</p>
                )}
              </section>
            </>
          ) : (
            <>
              <section>
                <h3>Maintenance</h3>
                <p>
                  {item.source_label} · {item.status_label}
                </p>
                <p>
                  Created {displayDate(item.created_at)} by {item.creator}
                </p>
              </section>
              <section>
                <h3>Schedule</h3>
                <p>Scheduled: {displayDate(item.scheduled_at)}</p>
                <p>Started: {displayDate(item.started_at)}</p>
                <p>Completed: {displayDate(item.completed_at)}</p>
              </section>
              <section>
                <h3>Related inspection</h3>
                <p>
                  {item.linked_inspection
                    ? `${displayDate(item.linked_inspection.inspection_date)} · ${item.linked_inspection.type_label} · ${item.linked_inspection.result_label}`
                    : "—"}
                </p>
              </section>
              <section>
                <h3>Details</h3>
                <p>{item.notes || "—"}</p>
              </section>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

export default function InspectionMaintenanceReportPage() {
  const [filters, setFilters] = useState<InspectionMaintenanceFilters>(initial);
  const [preset, setPreset] = useState("30");
  const [tab, setTab] = useState<"inspections" | "maintenance">("inspections");
  const [report, setReport] = useState<InspectionMaintenanceReport | null>(
    null,
  );
  const [selected, setSelected] = useState<
    InspectionRow | MaintenanceRow | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    fetchInspectionMaintenanceReport(filters)
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
    key: keyof InspectionMaintenanceFilters,
    value: string | number,
  ) => {
    setLoading(true);
    setError("");
    setFilters((old) => ({
      ...old,
      [key]: value || undefined,
      [tab === "inspections" ? "inspection_page" : "maintenance_page"]: 1,
    }));
  };
  const setPage = (value: number) => {
    setLoading(true);
    setError("");
    setFilters((old) => ({
      ...old,
      [tab === "inspections" ? "inspection_page" : "maintenance_page"]: value,
    }));
  };
  const page = report?.[tab];
  return (
    <main className="reports-page transport-report">
      <header className="reports-heading report-title-row">
        <div>
          <p>
            <Link to="/reports">
              <ChevronLeft /> Reports
            </Link>{" "}
            / Inspection & Maintenance
          </p>
          <h1>Inspection & Maintenance</h1>
        </div>
        <div className="report-actions">
          <button
            onClick={() => downloadInspectionMaintenanceCsv(tab, filters)}
          >
            <Download /> Export{" "}
            {tab === "inspections" ? "Inspections" : "Maintenance"} CSV
          </button>
          <button onClick={() => window.print()}>
            <Printer /> Print
          </button>
        </div>
      </header>
      <section className="report-filters" aria-label="Report filters">
        <label>
          Date range
          <select
            value={preset}
            onChange={(e) => {
              const value = e.target.value;
              setPreset(value);
              if (value !== "custom") {
                setLoading(true);
                setFilters((old) => ({
                  ...old,
                  date_from: manilaDate(-(Number(value) - 1)),
                  date_to: manilaDate(),
                  inspection_page: 1,
                  maintenance_page: 1,
                }));
              }
            }}
          >
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
        {tab === "inspections" ? (
          <>
            <label>
              Search
              <input
                value={filters.inspection_search ?? ""}
                onChange={(e) => setFilter("inspection_search", e.target.value)}
              />
            </label>
            <Filter
              label="Vehicle"
              value={filters.inspection_vehicle}
              choices={report?.choices.vehicles}
              change={(v) => setFilter("inspection_vehicle", v)}
            />
            <Filter
              label="Type"
              value={filters.inspection_type}
              choices={report?.choices.inspection_types}
              change={(v) => setFilter("inspection_type", v)}
            />
            <Filter
              label="Result"
              value={filters.inspection_result}
              choices={report?.choices.inspection_results}
              change={(v) => setFilter("inspection_result", v)}
            />
          </>
        ) : (
          <>
            <Filter
              label="Vehicle"
              value={filters.maintenance_vehicle}
              choices={report?.choices.vehicles}
              change={(v) => setFilter("maintenance_vehicle", v)}
            />
            <Filter
              label="Status"
              value={filters.maintenance_status}
              choices={report?.choices.maintenance_statuses}
              change={(v) => setFilter("maintenance_status", v)}
            />
            <Filter
              label="Source"
              value={filters.maintenance_source}
              choices={report?.choices.maintenance_sources}
              change={(v) => setFilter("maintenance_source", v)}
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
              Inspection basis: inspection date · Maintenance basis: created at
            </span>
          </section>
          <section className="report-kpis report-kpis-six">
            {[
              ["Inspections", report.summary.inspections],
              ["Passed", report.summary.passed],
              ["Needs Attention", report.summary.needs_attention],
              ["Failed", report.summary.failed],
              [
                "Active Maintenance · Current",
                report.summary.active_maintenance,
              ],
              ["Completed Maintenance", report.summary.completed_maintenance],
            ].map(([label, value]) => (
              <article key={label}>
                <strong>{value}</strong>
                <span>{label}</span>
              </article>
            ))}
          </section>
          <section className="report-maintenance-visuals">
            <Break
              title="Inspection Results"
              rows={report.breakdowns.inspection_results}
            />
            <Break
              title="Checklist Attention Areas"
              rows={report.breakdowns.checklist_attention}
            />
            <Break
              title="Current Maintenance Status"
              rows={report.breakdowns.maintenance_status}
            />
            <Break
              title="Maintenance Source"
              rows={report.breakdowns.maintenance_source}
            />
          </section>
          <section className="report-table-card">
            <div className="report-detail-tabs">
              <button
                className={tab === "inspections" ? "active" : ""}
                onClick={() => setTab("inspections")}
              >
                Inspections
              </button>
              <button
                className={tab === "maintenance" ? "active" : ""}
                onClick={() => setTab("maintenance")}
              >
                Maintenance
              </button>
            </div>
            <div className="report-table-scroll">
              {tab === "inspections" ? (
                <InspectionTable
                  rows={report.inspections.results}
                  view={setSelected}
                />
              ) : (
                <MaintenanceTable
                  rows={report.maintenance.results}
                  view={setSelected}
                />
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
                <div>
                  <button
                    disabled={page.page <= 1}
                    onClick={() => setPage(page.page - 1)}
                  >
                    Previous
                  </button>
                  <span>
                    Page {page.page} of {page.total_pages || 1}
                  </span>
                  <button
                    disabled={page.page >= page.total_pages}
                    onClick={() => setPage(page.page + 1)}
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

function Filter({
  label,
  value,
  choices,
  change,
}: {
  label: string;
  value: string | undefined;
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
function Break({
  title,
  rows,
}: {
  title: string;
  rows: { value: string | number; label: string; count: number }[];
}) {
  const total = Math.max(
    1,
    rows.reduce((sum, row) => sum + row.count, 0),
  );
  return (
    <article>
      <h2>{title}</h2>
      <div className="breakdown-list">
        {rows.map((row) => (
          <div key={row.value}>
            <span>{row.label}</span>
            <strong>{row.count}</strong>
            <i>
              <b style={{ width: `${(row.count / total) * 100}%` }} />
            </i>
          </div>
        ))}
      </div>
    </article>
  );
}
function InspectionTable({
  rows,
  view,
}: {
  rows: InspectionRow[];
  view: (row: InspectionRow) => void;
}) {
  return (
    <table>
      <thead>
        <tr>
          <th>Inspection Date</th>
          <th>Vehicle</th>
          <th>Type</th>
          <th>Result</th>
          <th>Inspector</th>
          <th>Odometer</th>
          <th>Fuel</th>
          <th>Exceptions</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>{displayDate(row.inspection_date)}</td>
            <td>
              {row.vehicle.name}
              <small>{row.vehicle.identifier}</small>
            </td>
            <td>{row.inspection_type_label}</td>
            <td>{row.result_label}</td>
            <td>{row.inspector}</td>
            <td>{row.odometer_km ?? "—"}</td>
            <td>
              {row.fuel_level_percent === null
                ? "—"
                : `${row.fuel_level_percent}%`}
            </td>
            <td>{row.exception_count}</td>
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
function MaintenanceTable({
  rows,
  view,
}: {
  rows: MaintenanceRow[];
  view: (row: MaintenanceRow) => void;
}) {
  return (
    <table>
      <thead>
        <tr>
          <th>Created</th>
          <th>Vehicle</th>
          <th>Title</th>
          <th>Source</th>
          <th>Status</th>
          <th>Scheduled</th>
          <th>Completed</th>
          <th>Linked Inspection</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>{displayDate(row.created_at)}</td>
            <td>
              {row.vehicle.name}
              <small>{row.vehicle.identifier}</small>
            </td>
            <td>{row.title}</td>
            <td>{row.source_label}</td>
            <td>{row.status_label}</td>
            <td>{displayDate(row.scheduled_at)}</td>
            <td>{displayDate(row.completed_at)}</td>
            <td>
              {row.linked_inspection
                ? displayDate(row.linked_inspection.inspection_date)
                : "—"}
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
