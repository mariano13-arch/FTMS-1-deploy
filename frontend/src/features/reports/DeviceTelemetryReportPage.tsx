import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ChevronLeft,
  Download,
  ExternalLink,
  Printer,
  RefreshCw,
  X,
} from "lucide-react";
import LoadingIndicator from "../../components/common/LoadingIndicator";
import {
  downloadDeviceTelemetryCsv,
  fetchDeviceTelemetryReport,
  type BindingHistoryRow,
  type DeviceSummaryRow,
  type DeviceTelemetryFilters,
  type DeviceTelemetryReport,
  type ReportBreakdown,
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
const initial = (): DeviceTelemetryFilters => ({
  date_from: manilaDate(-29),
  date_to: manilaDate(),
  device_page: 1,
  binding_page: 1,
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
function Field({ name, text }: { name: string; text: string }) {
  return (
    <div>
      <dt>{name}</dt>
      <dd>{text}</dd>
    </div>
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
            <small>Read-only report detail</small>
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
function DeviceDrawer({
  item,
  close,
}: {
  item: DeviceSummaryRow;
  close: () => void;
}) {
  const binding = item.current_binding;
  const telemetry = item.latest_telemetry;
  return (
    <DrawerShell label="Device details" title={item.device_id} close={close}>
      <section>
        <h3>Device</h3>
        <dl>
          <Field name="Device ID" text={item.device_id} />
          <Field name="Registry status" text={item.registration_status_label} />
          <Field name="Registered at" text={displayDate(item.registered_at)} />
          <Field name="Historical bindings" text={String(item.binding_count)} />
        </dl>
        <Link className="report-drawer-link" to="/devices">
          <ExternalLink /> View Device
        </Link>
      </section>
      <section>
        <h3>Current binding</h3>
        {binding ? (
          <dl>
            <Field name="Vehicle" text={binding.vehicle.name} />
            <Field name="Identifier" text={binding.vehicle.identifier} />
            <Field name="Paired at" text={displayDate(binding.paired_at)} />
            <Field name="Paired by" text={binding.paired_by ?? "—"} />
          </dl>
        ) : (
          <p>Unpaired</p>
        )}
      </section>
      <section>
        <h3>Latest telemetry</h3>
        {telemetry ? (
          <dl>
            <Field
              name="Recorded at"
              text={displayDate(telemetry.recorded_at)}
            />
            <Field
              name="Received at"
              text={displayDate(telemetry.received_at)}
            />
            <Field
              name="Position source"
              text={telemetry.position_source_label}
            />
            <Field
              name="Position accuracy"
              text={
                telemetry.position_accuracy_m
                  ? `${telemetry.position_accuracy_m} m`
                  : "—"
              }
            />
            <Field
              name="OBD source"
              text={telemetry.obd_source_label ?? "No OBD Data"}
            />
          </dl>
        ) : (
          <p>No telemetry received</p>
        )}
      </section>
      {telemetry && (
        <section>
          <h3>Latest location</h3>
          <dl>
            <Field name="Latitude" text={String(telemetry.latitude)} />
            <Field name="Longitude" text={String(telemetry.longitude)} />
          </dl>
        </section>
      )}
    </DrawerShell>
  );
}
function BindingDrawer({
  item,
  close,
}: {
  item: BindingHistoryRow;
  close: () => void;
}) {
  return (
    <DrawerShell
      label="Binding details"
      title={item.device.device_id}
      close={close}
    >
      <section>
        <h3>Device</h3>
        <dl>
          <Field name="Device ID" text={item.device.device_id} />
          <Field
            name="Registry status"
            text={item.device.registration_status_label}
          />
        </dl>
      </section>
      <section>
        <h3>Vehicle</h3>
        <dl>
          <Field name="Vehicle" text={item.vehicle.name} />
          <Field name="Identifier" text={item.vehicle.identifier} />
        </dl>
      </section>
      <section>
        <h3>Binding</h3>
        <dl>
          <Field name="Bound at" text={displayDate(item.paired_at)} />
          <Field name="Unbound at" text={displayDate(item.unpaired_at)} />
          <Field name="State" text={item.binding_state_label} />
        </dl>
      </section>
      <section>
        <h3>Actors</h3>
        <dl>
          <Field name="Paired by" text={item.paired_by ?? "—"} />
          <Field name="Unpaired by" text={item.unpaired_by ?? "—"} />
        </dl>
      </section>
    </DrawerShell>
  );
}

export default function DeviceTelemetryReportPage() {
  const [filters, setFilters] = useState<DeviceTelemetryFilters>(initial);
  const [preset, setPreset] = useState("30");
  const [tab, setTab] = useState<"devices" | "bindings">("devices");
  const [report, setReport] = useState<DeviceTelemetryReport | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<DeviceSummaryRow | null>(
    null,
  );
  const [selectedBinding, setSelectedBinding] =
    useState<BindingHistoryRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    fetchDeviceTelemetryReport(filters)
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
    key: keyof DeviceTelemetryFilters,
    next: string | number | undefined,
  ) => {
    setLoading(true);
    setError("");
    setFilters((old) => ({
      ...old,
      [key]: next === "" ? undefined : next,
      [tab === "devices" ? "device_page" : "binding_page"]: key.endsWith(
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
        device_page: 1,
        binding_page: 1,
      }));
    }
  };
  const page = tab === "devices" ? report?.devices : report?.bindings;
  return (
    <main className="reports-page transport-report">
      <header className="reports-heading report-title-row">
        <div>
          <p>
            <Link to="/reports">
              <ChevronLeft /> Reports
            </Link>{" "}
            / Device & Telemetry Availability
          </p>
          <h1>Device & Telemetry Availability</h1>
        </div>
        <div className="report-actions">
          <button onClick={() => downloadDeviceTelemetryCsv(tab, filters)}>
            <Download /> Export{" "}
            {tab === "devices" ? "Device Summary" : "Binding History"} CSV
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
        {tab === "devices" ? (
          <>
            <label>
              Search
              <input
                aria-label="Device search"
                placeholder="Device or current vehicle"
                value={filters.device_search ?? ""}
                onChange={(event) =>
                  setFilter("device_search", event.target.value)
                }
              />
            </label>
            <Select
              label="Registry state"
              selected={filters.registry_status}
              choices={report?.choices.registry_statuses}
              change={(next) => setFilter("registry_status", next)}
            />
            <Select
              label="Binding state"
              selected={filters.binding_state}
              choices={[
                { value: "PAIRED", label: "Paired" },
                { value: "UNPAIRED", label: "Unpaired" },
              ]}
              change={(next) => setFilter("binding_state", next)}
            />
            <Select
              label="Telemetry state"
              selected={filters.telemetry_state}
              choices={[
                { value: "RECEIVED", label: "Telemetry Received" },
                { value: "NO_TELEMETRY", label: "No Telemetry" },
              ]}
              change={(next) => setFilter("telemetry_state", next)}
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
            <Select
              label="Vehicle"
              selected={filters.vehicle}
              choices={report?.choices.vehicles}
              change={(next) => setFilter("vehicle", next)}
            />
          </>
        ) : (
          <>
            <label>
              Search
              <input
                aria-label="Binding search"
                placeholder="Device or vehicle"
                value={filters.binding_search ?? ""}
                onChange={(event) =>
                  setFilter("binding_search", event.target.value)
                }
              />
            </label>
            <Select
              label="Device"
              selected={filters.binding_device}
              choices={report?.choices.devices}
              change={(next) => setFilter("binding_device", next)}
            />
            <Select
              label="Vehicle"
              selected={filters.binding_vehicle}
              choices={report?.choices.vehicles}
              change={(next) => setFilter("binding_vehicle", next)}
            />
            <Select
              label="Binding state"
              selected={filters.binding_history_state}
              choices={[
                { value: "ACTIVE", label: "Active" },
                { value: "HISTORICAL", label: "Historical" },
              ]}
              change={(next) => setFilter("binding_history_state", next)}
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
              Period telemetry basis: recorded at · binding basis: paired at
            </span>
            <span>Current state is not date-filtered</span>
          </section>
          <section className="report-kpis" aria-label="Report summary">
            {[
              [
                "Registered Devices · Current",
                report.summary.registered_devices,
              ],
              ["Paired Devices · Current", report.summary.paired_devices],
              ["Unpaired Devices · Current", report.summary.unpaired_devices],
              ["Retired Devices · Current", report.summary.retired_devices],
              ["No Telemetry · Registered", report.summary.no_telemetry],
            ].map(([label, count]) => (
              <article key={label}>
                <strong>{count}</strong>
                <span>{label}</span>
              </article>
            ))}
          </section>
          <section className="report-device-visuals">
            <Breakdown
              title="Telemetry Availability"
              rows={report.breakdowns.availability}
            />
            <Breakdown
              title="Current Device Binding"
              rows={report.breakdowns.binding_state}
            />
            <Breakdown
              title="Latest Position Source"
              rows={report.breakdowns.position_sources}
            />
            <Breakdown
              title="Latest OBD Source"
              rows={report.breakdowns.obd_sources}
            />
          </section>
          <section className="report-table-card">
            <div className="report-detail-tabs">
              <button
                className={tab === "devices" ? "active" : ""}
                onClick={() => setTab("devices")}
              >
                Devices
              </button>
              <button
                className={tab === "bindings" ? "active" : ""}
                onClick={() => setTab("bindings")}
              >
                Binding History
              </button>
            </div>
            <div className="report-table-scroll">
              {tab === "devices" ? (
                <DeviceTable
                  rows={report.devices.results}
                  view={setSelectedDevice}
                />
              ) : (
                <BindingTable
                  rows={report.bindings.results}
                  view={setSelectedBinding}
                />
              )}
              {page && !page.results.length && (
                <p className="empty-report">
                  No {tab === "devices" ? "devices" : "binding history"} match
                  the current filters.
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
                        tab === "devices" ? "device_page" : "binding_page",
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
                        tab === "devices" ? "device_page" : "binding_page",
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
      {selectedDevice && (
        <DeviceDrawer
          item={selectedDevice}
          close={() => setSelectedDevice(null)}
        />
      )}
      {selectedBinding && (
        <BindingDrawer
          item={selectedBinding}
          close={() => setSelectedBinding(null)}
        />
      )}
    </main>
  );
}
function DeviceTable({
  rows,
  view,
}: {
  rows: DeviceSummaryRow[];
  view: (row: DeviceSummaryRow) => void;
}) {
  return (
    <table>
      <thead>
        <tr>
          <th>Device</th>
          <th>Registry State</th>
          <th>Current Vehicle</th>
          <th>Binding State</th>
          <th>Last Telemetry</th>
          <th>Position Source</th>
          <th>OBD Source</th>
          <th>Telemetry State</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>{row.device_id}</td>
            <td>{row.registration_status_label}</td>
            <td>
              {row.current_binding?.vehicle.name ?? "—"}
              <small>{row.current_binding?.vehicle.identifier}</small>
            </td>
            <td>{row.binding_state_label}</td>
            <td>{displayDate(row.latest_telemetry?.recorded_at)}</td>
            <td>{row.latest_telemetry?.position_source_label ?? "—"}</td>
            <td>{row.latest_telemetry?.obd_source_label ?? "—"}</td>
            <td>
              {row.latest_telemetry
                ? "Telemetry Received"
                : "No telemetry received"}
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
function BindingTable({
  rows,
  view,
}: {
  rows: BindingHistoryRow[];
  view: (row: BindingHistoryRow) => void;
}) {
  return (
    <table>
      <thead>
        <tr>
          <th>Device</th>
          <th>Vehicle</th>
          <th>Bound At</th>
          <th>Unbound At</th>
          <th>State</th>
          <th>Paired By</th>
          <th>Unpaired By</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>{row.device.device_id}</td>
            <td>
              {row.vehicle.name}
              <small>{row.vehicle.identifier}</small>
            </td>
            <td>{displayDate(row.paired_at)}</td>
            <td>{displayDate(row.unpaired_at)}</td>
            <td>{row.binding_state_label}</td>
            <td>{row.paired_by ?? "—"}</td>
            <td>{row.unpaired_by ?? "—"}</td>
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
