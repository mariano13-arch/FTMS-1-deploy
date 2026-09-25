import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, Download, Printer, RefreshCw } from "lucide-react";
import LoadingIndicator from "../../components/common/LoadingIndicator";
import {
  downloadTransportReportCsv,
  downloadTransportReportPdf,
  downloadTransportReportXlsx,
  fetchTransportReport,
  type ReportFilterValues,
  type TransportReport,
} from "./api";
import "./reports.css";

function manilaDate(offsetDays = 0) {
  const value = new Date(Date.now() + offsetDays * 86400000);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Manila",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(value);
  const part = (name: string) =>
    parts.find((item) => item.type === name)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

const initialFilters = (): ReportFilterValues => ({
  date_from: manilaDate(-29),
  date_to: manilaDate(),
  page: 1,
  page_size: 15,
});
const localTime = (value: string) =>
  new Date(value).toLocaleString("en-PH", {
    timeZone: "Asia/Manila",
    dateStyle: "medium",
    timeStyle: "short",
  });

export default function TransportRequestReportPage() {
  const [filters, setFilters] = useState<ReportFilterValues>(initialFilters);
  const [preset, setPreset] = useState("30");
  const [report, setReport] = useState<TransportReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    fetchTransportReport(filters)
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
    key: keyof ReportFilterValues,
    value: string | number | undefined,
  ) => {
    setLoading(true);
    setError("");
    setFilters((current) => ({
      ...current,
      [key]: value || undefined,
      page: key === "page" ? Number(value) : 1,
    }));
  };
  const choosePreset = (value: string) => {
    setPreset(value);
    if (value === "custom") return;
    const days = Number(value);
    setLoading(true);
    setError("");
    setFilters((current) => ({
      ...current,
      date_from: manilaDate(-(days - 1)),
      date_to: manilaDate(),
      page: 1,
    }));
  };
  return (
    <main className="reports-page transport-report">
      <header className="reports-heading report-title-row">
        <div>
          <p>
            <Link to="/reports">
              <ChevronLeft /> Reports
            </Link>{" "}
            / Transport Request Summary
          </p>
          <h1>Transport Request Summary</h1>
        </div>
        <div className="report-actions">
          <button
            type="button"
            onClick={() => downloadTransportReportCsv(filters)}
          >
            <Download /> Export CSV
          </button>
          <button
            type="button"
            onClick={() => downloadTransportReportXlsx(filters)}
          >
            <Download /> Export Excel
          </button>
          <button
            type="button"
            onClick={() => downloadTransportReportPdf(filters)}
          >
            <Download /> Export PDF
          </button>
          <button type="button" onClick={() => window.print()}>
            <Printer /> Print
          </button>
        </div>
      </header>

      <section className="report-filters" aria-label="Report filters">
        <label>
          Date range
          <select
            value={preset}
            onChange={(event) => choosePreset(event.target.value)}
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
        {["source", "request_type", "status", "priority"].map((key) => (
          <label key={key}>
            {key.replace("_", " ")}
            <select
              value={String(filters[key as keyof ReportFilterValues] ?? "")}
              onChange={(event) =>
                setFilter(key as keyof ReportFilterValues, event.target.value)
              }
            >
              <option value="">All</option>
              {(key === "source"
                ? report?.choices.sources
                : key === "request_type"
                  ? report?.choices.request_types
                  : key === "status"
                    ? report?.choices.statuses
                    : report?.choices.priorities
              )?.map((choice) => (
                <option key={choice.value} value={choice.value}>
                  {choice.label}
                </option>
              ))}
            </select>
          </label>
        ))}
        <button
          className="report-reset"
          type="button"
          onClick={() => {
            setPreset("30");
            setLoading(true);
            setError("");
            setFilters(initialFilters());
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
            type="button"
            onClick={() => {
              setLoading(true);
              setError("");
              setFilters((current) => ({ ...current }));
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
              Generated {localTime(report.meta.generated_at)} by{" "}
              {report.meta.generated_by}
            </span>
            <span>Timezone: {report.meta.timezone}</span>
            <span>Date basis: Created at</span>
          </section>
          <section className="report-kpis" aria-label="Report summary">
            {[
              ["Requests Created", report.summary.requests_created],
              ["Approved", report.summary.approved],
              ["Rejected", report.summary.rejected],
              ["Cancelled", report.summary.cancelled],
              [
                "Currently Dispatch Ready",
                report.summary.currently_dispatch_ready,
              ],
            ].map(([label, value]) => (
              <article key={label}>
                <strong>{value}</strong>
                <span>{label}</span>
              </article>
            ))}
          </section>
          <section className="report-visuals">
            {(
              [
                ["By source", report.breakdowns.by_source],
                ["By current status", report.breakdowns.by_status],
              ] as const
            ).map(([title, rows]) => (
              <article key={title}>
                <h2>{title}</h2>
                <div className="breakdown-list">
                  {rows.map((row) => (
                    <div key={row.value}>
                      <span>{row.label}</span>
                      <strong>{row.count}</strong>
                      <i>
                        <b
                          style={{
                            width: `${report.summary.requests_created ? (row.count / report.summary.requests_created) * 100 : 0}%`,
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
                <h2>Request details</h2>
                <span>{report.details.count} matching requests</span>
              </div>
              <label>
                Rows
                <select
                  value={filters.page_size}
                  onChange={(event) =>
                    setFilter("page_size", Number(event.target.value))
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
                    <th>Source</th>
                    <th>Type / category</th>
                    <th>Priority</th>
                    <th>Status</th>
                    <th>Scheduled pickup</th>
                    <th>Created</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {report.details.results.map((row) => (
                    <tr key={row.id}>
                      <td>{row.request_number}</td>
                      <td>{row.source_label}</td>
                      <td>
                        {row.request_type_label}
                        <small>{row.request_category_label}</small>
                      </td>
                      <td>{row.priority_label}</td>
                      <td>{row.status_label}</td>
                      <td>{localTime(row.scheduled_pickup_at)}</td>
                      <td>{localTime(row.created_at)}</td>
                      <td>
                        <Link to={`/transport-requests/${row.id}`}>View</Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!report.details.results.length && (
                <p className="empty-report">No requests match these filters.</p>
              )}
            </div>
            <footer>
              <span>
                Page {report.details.page} of {report.details.total_pages || 1}
              </span>
              <div>
                <button
                  type="button"
                  disabled={report.details.page <= 1}
                  onClick={() => setFilter("page", report.details.page - 1)}
                >
                  Previous
                </button>
                <button
                  type="button"
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
    </main>
  );
}
