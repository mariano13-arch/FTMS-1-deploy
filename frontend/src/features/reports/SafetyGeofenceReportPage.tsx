import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, Download, Printer, RefreshCw, X } from "lucide-react";
import LoadingIndicator from "../../components/common/LoadingIndicator";
import {
  downloadSafetyGeofenceCsv,
  fetchSafetyGeofenceReport,
  type GeofenceEventRow,
  type ReportBreakdown,
  type SafetyEventRow,
  type SafetyGeofenceFilters,
  type SafetyGeofenceReport,
  type SosEventRow,
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
const initial = (): SafetyGeofenceFilters => ({
  date_from: manilaDate(-29),
  date_to: manilaDate(),
  safety_page: 1,
  geofence_page: 1,
  sos_page: 1,
  page_size: 15,
});
const displayDate = (value?: string | null) =>
  value
    ? new Date(value).toLocaleString("en-PH", {
        timeZone: "Asia/Manila",
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "—";
const value = (item: string | number | null | undefined, suffix = "") =>
  item === null || item === undefined ? "—" : `${item}${suffix}`;

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
          <p>No matching activity.</p>
        )}
      </div>
    </article>
  );
}
function Select({
  label,
  selected,
  choices,
  change,
}: {
  label: string;
  selected?: string;
  choices?: { value: string | number; label: string }[];
  change: (value: string) => void;
}) {
  return (
    <label>
      {label}
      <select
        value={selected ?? ""}
        onChange={(event) => change(event.target.value)}
      >
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

function SafetyDrawer({
  item,
  close,
}: {
  item: SafetyEventRow;
  close: () => void;
}) {
  return (
    <DrawerShell
      label="Safety event details"
      title={item.event_type_label}
      close={close}
    >
      <section>
        <h3>Safety event</h3>
        <dl>
          <Field name="Type" text={item.event_type_label} />
          <Field name="Occurred at" text={displayDate(item.occurred_at)} />
          <Field name="Event ID" text={item.event_id} />
          <Field name="Provenance" text="Operational" />
        </dl>
      </section>
      <section>
        <h3>Driver / Assignment</h3>
        <dl>
          <Field name="Driver" text={`${item.driver.code} · ${item.driver.name}`} />
          <Field name="Request" text={item.assignment.request_number} />
          <Field name="Vehicle" text={item.vehicle.name} />
          <Field name="Vehicle identifier" text={item.vehicle.identifier} />
          <Field name="Device ID" text={item.device_id} />
        </dl>
      </section>
      <section>
        <h3>Linked telemetry provenance</h3>
        <dl>
          <Field name="Position source" text={item.position_source_label} />
          <Field name="OBD source" text={item.obd_source_label ?? "—"} />
        </dl>
      </section>
    </DrawerShell>
  );
}

function SosDrawer({ item, close }: { item: SosEventRow; close: () => void }) {
  return <DrawerShell label="SOS activity details" title={`SOS · ${item.status_label}`} close={close}>
    <section><h3>Emergency event</h3><dl>
      <Field name="Status" text={item.status_label} />
      <Field name="Source" text={item.source_label} />
      <Field name="Activated at" text={displayDate(item.activated_at)} />
      <Field name="Cleared at" text={displayDate(item.cleared_at)} />
      <Field name="Device" text={item.device.device_id} />
      <Field name="Vehicle" text={item.vehicle ? `${item.vehicle.name} · ${item.vehicle.identifier}` : "Not resolved"} />
      <Field name="Driver" text={item.driver ? `${item.driver.code} · ${item.driver.name}` : "Not resolved"} />
      <Field name="Location" text={item.location_label} />
    </dl></section>
  </DrawerShell>;
}
function GeofenceDrawer({
  item,
  close,
}: {
  item: GeofenceEventRow;
  close: () => void;
}) {
  return (
    <DrawerShell
      label="Geofence activity details"
      title={item.display_classification}
      close={close}
    >
      <section>
        <h3>Event</h3>
        <dl>
          <Field name="Event" text={item.event_type_label} />
          <Field name="Classification" text={item.display_classification} />
          <Field name="Occurred at" text={displayDate(item.occurred_at)} />
          <Field name="Created at" text={displayDate(item.created_at)} />
        </dl>
      </section>
      <section>
        <h3>Geofence</h3>
        <dl>
          <Field name="Name" text={item.geofence.name} />
          <Field name="Category" text={item.geofence.category_label} />
          <Field name="Boundary type" text={item.geofence.shape_type_label} />
          <Field
            name="Radius"
            text={value(item.geofence.radius_meters, " m")}
          />
        </dl>
      </section>
      <section>
        <h3>Vehicle / Location</h3>
        <dl>
          <Field name="Vehicle" text={item.vehicle.name} />
          <Field name="Identifier" text={item.vehicle.identifier} />
          <Field name="Latitude" text={String(item.latitude)} />
          <Field name="Longitude" text={String(item.longitude)} />
        </dl>
      </section>
      <section>
        <h3>Source telemetry</h3>
        <dl>
          <Field name="Telemetry event ID" text={item.telemetry.event_id} />
          <Field
            name="Recorded at"
            text={displayDate(item.telemetry.recorded_at)}
          />
          <Field
            name="Position source"
            text={item.telemetry.position_source_label}
          />
          <Field
            name="OBD source"
            text={item.telemetry.obd_source_label ?? "—"}
          />
        </dl>
      </section>
    </DrawerShell>
  );
}
function DrawerShell({
  label,
  title,
  close,
  children,
}: {
  label: string;
  title: string;
  close: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="report-drawer-backdrop" onMouseDown={close}>
      <aside
        className="report-drawer"
        aria-label={label}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <small>Persisted report record</small>
            <h2>{title}</h2>
          </div>
          <button aria-label="Close details" onClick={close}>
            <X />
          </button>
        </header>
        <div className="report-drawer-body">{children}</div>
      </aside>
    </div>
  );
}
function Field({ name, text }: { name: string; text: string }) {
  return (
    <div>
      <dt>{name}</dt>
      <dd>{text}</dd>
    </div>
  );
}

export default function SafetyGeofenceReportPage() {
  const [filters, setFilters] = useState<SafetyGeofenceFilters>(initial);
  const [preset, setPreset] = useState("30");
  const [tab, setTab] = useState<"safety" | "geofence" | "sos">("safety");
  const [report, setReport] = useState<SafetyGeofenceReport | null>(null);
  const [selectedSafety, setSelectedSafety] = useState<SafetyEventRow | null>(
    null,
  );
  const [selectedGeofence, setSelectedGeofence] =
    useState<GeofenceEventRow | null>(null);
  const [selectedSos, setSelectedSos] = useState<SosEventRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    fetchSafetyGeofenceReport(filters)
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
    key: keyof SafetyGeofenceFilters,
    next: string | number | undefined,
  ) => {
    setLoading(true);
    setError("");
    setFilters((old) => ({
      ...old,
      [key]: next === "" ? undefined : next,
      [tab === "safety" ? "safety_page" : tab === "geofence" ? "geofence_page" : "sos_page"]: key.endsWith(
        "_page",
      )
        ? Number(next)
        : 1,
    }));
  };
  const setRange = (next: string) => {
    setPreset(next);
    if (next !== "custom") {
      setLoading(true);
      setFilters((old) => ({
        ...old,
        date_from: manilaDate(-(Number(next) - 1)),
        date_to: manilaDate(),
        safety_page: 1,
        geofence_page: 1,
        sos_page: 1,
      }));
    }
  };
  const page = tab === "safety" ? report?.safety_events : tab === "geofence" ? report?.geofence_activity : report?.sos_activity;
  return (
    <main className="reports-page transport-report">
      <header className="reports-heading report-title-row">
        <div>
          <p>
            <Link to="/reports">
              <ChevronLeft /> Reports
            </Link>{" "}
            / Safety, Geofence &amp; SOS Activity
          </p>
          <h1>Safety, Geofence &amp; SOS Activity</h1>
        </div>
        <div className="report-actions">
          <button onClick={() => downloadSafetyGeofenceCsv(tab, filters)}>
            <Download /> Export{" "}
            {tab === "safety" ? "Safety Events" : tab === "geofence" ? "Geofence Activity" : "SOS Activity"} CSV
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
            onChange={(event) => setRange(event.target.value)}
          >
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
                onChange={(event) => setFilter("date_from", event.target.value)}
              />
            </label>
            <label>
              To
              <input
                type="date"
                value={filters.date_to}
                onChange={(event) => setFilter("date_to", event.target.value)}
              />
            </label>
          </>
        )}
        {tab === "safety" ? (
          <>
            <label>
              Search
              <input
                aria-label="Safety search"
                placeholder="Vehicle or device"
                value={filters.safety_search ?? ""}
                onChange={(event) =>
                  setFilter("safety_search", event.target.value)
                }
              />
            </label>
            <Select
              label="Event type"
              selected={filters.safety_event_type}
              choices={report?.choices.safety_event_types}
              change={(next) => setFilter("safety_event_type", next)}
            />
            <Select
              label="Vehicle"
              selected={filters.safety_vehicle}
              choices={report?.choices.vehicles}
              change={(next) => setFilter("safety_vehicle", next)}
            />
            <Select
              label="Driver"
              selected={filters.safety_driver}
              choices={report?.choices.drivers}
              change={(next) => setFilter("safety_driver", next)}
            />
            <Select
              label="Position source"
              selected={filters.position_source}
              choices={report?.choices.position_sources}
              change={(next) => setFilter("position_source", next)}
            />
            <Select
              label="OBD source"
              selected={filters.obd_source}
              choices={report?.choices.obd_sources}
              change={(next) => setFilter("obd_source", next)}
            />
          </>
        ) : tab === "geofence" ? (
          <>
            <label>
              Search
              <input
                aria-label="Geofence search"
                placeholder="Geofence or vehicle"
                value={filters.geofence_search ?? ""}
                onChange={(event) =>
                  setFilter("geofence_search", event.target.value)
                }
              />
            </label>
            <Select
              label="Event type"
              selected={filters.geofence_event_type}
              choices={report?.choices.geofence_event_types}
              change={(next) => setFilter("geofence_event_type", next)}
            />
            <Select
              label="Category"
              selected={filters.category}
              choices={report?.choices.categories}
              change={(next) => setFilter("category", next)}
            />
            <Select
              label="Geofence"
              selected={filters.geofence}
              choices={report?.choices.geofences}
              change={(next) => setFilter("geofence", next)}
            />
            <Select
              label="Vehicle"
              selected={filters.geofence_vehicle}
              choices={report?.choices.vehicles}
              change={(next) => setFilter("geofence_vehicle", next)}
            />
            <Select
              label="Position source"
              selected={filters.geofence_position_source}
              choices={report?.choices.position_sources}
              change={(next) => setFilter("geofence_position_source", next)}
            />
          </>
        ) : (
          <>
            <Select label="Status" selected={filters.sos_status} choices={report?.choices.sos_statuses} change={(next) => setFilter("sos_status", next)} />
            <Select label="Vehicle" selected={filters.sos_vehicle} choices={report?.choices.vehicles} change={(next) => setFilter("sos_vehicle", next)} />
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
            <span>Safety basis: operational event · Geofence/SOS basis: occurred/activated at</span>
            <span>
              Date range: {report.meta.date_from}–{report.meta.date_to}
            </span>
          </section>
          <section
            className="report-kpis report-kpis-six"
            aria-label="Report summary"
          >
            {[
              ["Safety Events", report.summary.safety_events],
              ["Harsh Braking", report.summary.harsh_braking],
              ["Harsh Acceleration", report.summary.harsh_acceleration],
              ["Sharp Turns", report.summary.sharp_turns],
              ["Restricted Entries", report.summary.restricted_entries],
              ["Geofence Activity", report.summary.geofence_activity],
              ["SOS Activations", report.summary.sos_activations],
              ["Active SOS", report.summary.active_sos],
            ].map(([label, count]) => (
              <article key={label}>
                <strong>{count}</strong>
                <span>{label}</span>
              </article>
            ))}
          </section>
          <section className="report-safety-visuals">
            <Breakdown
              title="Safety Event Types"
              rows={report.breakdowns.safety_types}
            />
            <Breakdown
              title="Position Source"
              rows={report.breakdowns.position_sources}
            />
            <Breakdown
              title="Entry / Exit Activity"
              rows={report.breakdowns.geofence_events}
            />
            <Breakdown
              title="Restricted Entries by Geofence"
              rows={report.breakdowns.restricted_by_geofence}
            />
          </section>
          <section className="report-table-card">
            <div className="report-detail-tabs">
              <button
                className={tab === "safety" ? "active" : ""}
                onClick={() => setTab("safety")}
              >
                Safety Events
              </button>
              <button
                className={tab === "geofence" ? "active" : ""}
                onClick={() => setTab("geofence")}
              >
                Geofence Activity
              </button>
              <button className={tab === "sos" ? "active" : ""} onClick={() => setTab("sos")}>SOS Activity</button>
            </div>
            <div className="report-table-scroll">
              {tab === "safety" ? (
                <SafetyTable
                  rows={report.safety_events.results}
                  view={setSelectedSafety}
                />
              ) : tab === "geofence" ? (
                <GeofenceTable
                  rows={report.geofence_activity.results}
                  view={setSelectedGeofence}
                />
              ) : (
                <SosTable rows={report.sos_activity.results} view={setSelectedSos} />
              )}
              {page && !page.results.length && (
                <p className="empty-report">
                  No {tab === "safety" ? "operational safety events" : tab === "geofence" ? "geofence activity" : "SOS activity"}{" "}
                  match the selected range and filters.
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
                    onChange={(event) =>
                      setFilter("page_size", Number(event.target.value))
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
                        tab === "safety" ? "safety_page" : tab === "geofence" ? "geofence_page" : "sos_page",
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
                        tab === "safety" ? "safety_page" : tab === "geofence" ? "geofence_page" : "sos_page",
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
      {selectedSafety && (
        <SafetyDrawer
          item={selectedSafety}
          close={() => setSelectedSafety(null)}
        />
      )}
      {selectedGeofence && (
        <GeofenceDrawer
          item={selectedGeofence}
          close={() => setSelectedGeofence(null)}
        />
      )}
      {selectedSos && <SosDrawer item={selectedSos} close={() => setSelectedSos(null)} />}
    </main>
  );
}

function SafetyTable({
  rows,
  view,
}: {
  rows: SafetyEventRow[];
  view: (row: SafetyEventRow) => void;
}) {
  return (
    <table>
      <thead>
        <tr>
          <th>Time</th>
          <th>Type</th>
          <th>Driver / Assignment</th>
          <th>Vehicle</th>
          <th>Device</th>
          <th>Provenance</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>{displayDate(row.occurred_at)}</td>
            <td>{row.event_type_label}</td>
            <td>{row.driver.name}<small>{row.driver.code} · {row.assignment.request_number}</small></td>
            <td>
              {row.vehicle.name}
              <small>{row.vehicle.identifier}</small>
            </td>
            <td>{row.device_id}</td>
            <td>
              {row.position_source_label}
              <small>OBD: {row.obd_source_label ?? "—"}</small>
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

function SosTable({ rows, view }: { rows: SosEventRow[]; view: (row: SosEventRow) => void }) {
  return <table><thead><tr><th>Activated</th><th>Status</th><th>Vehicle</th><th>Driver</th><th>Device / Source</th><th>Location</th><th /></tr></thead>
    <tbody>{rows.map((row) => <tr key={row.id}>
      <td>{displayDate(row.activated_at)}<small>Cleared: {displayDate(row.cleared_at)}</small></td>
      <td>{row.status_label}</td><td>{row.vehicle?.name ?? "Not resolved"}<small>{row.vehicle?.identifier}</small></td>
      <td>{row.driver?.name ?? "Not resolved"}<small>{row.driver?.code}</small></td>
      <td>{row.device.device_id}<small>{row.source_label}</small></td><td>{row.location_label}</td>
      <td><button className="report-view" onClick={() => view(row)}>View</button></td>
    </tr>)}</tbody></table>;
}
function GeofenceTable({
  rows,
  view,
}: {
  rows: GeofenceEventRow[];
  view: (row: GeofenceEventRow) => void;
}) {
  return (
    <table>
      <thead>
        <tr>
          <th>Time</th>
          <th>Event</th>
          <th>Geofence</th>
          <th>Category</th>
          <th>Vehicle</th>
          <th>Location</th>
          <th>Provenance</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>{displayDate(row.occurred_at)}</td>
            <td>
              {row.event_type_label}
              {row.display_classification === "Restricted Zone Entry" && (
                <small className="report-event-badge">
                  Restricted Zone Entry
                </small>
              )}
            </td>
            <td>{row.geofence.name}</td>
            <td>{row.geofence.category_label}</td>
            <td>
              {row.vehicle.name}
              <small>{row.vehicle.identifier}</small>
            </td>
            <td>
              {row.latitude.toFixed(3)}, {row.longitude.toFixed(3)}
            </td>
            <td>
              {row.telemetry.position_source_label}
              <small>OBD: {row.telemetry.obd_source_label ?? "—"}</small>
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
