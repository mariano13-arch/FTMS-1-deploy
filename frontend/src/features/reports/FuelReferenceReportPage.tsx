import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, Download, Printer, RefreshCw } from "lucide-react";
import LoadingIndicator from "../../components/common/LoadingIndicator";
import {
  downloadFuelReferenceCsv,
  fetchFuelReferenceReport,
  type FuelReferenceFilters,
  type FuelReferenceReport,
  type ReportChoice,
} from "./api";
import "./reports.css";

type Tab = "predictions" | "baselines" | "prices";
const manilaDate = (offset = 0) => {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Manila", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date(Date.now() + offset * 86400000));
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
};
const initial = (): FuelReferenceFilters => ({ date_from: manilaDate(-29), date_to: manilaDate(), prediction_page: 1, baseline_page: 1, price_page: 1, page_size: 15 });
const dateTime = (value?: string | null) => value ? new Date(value).toLocaleString("en-PH", { timeZone: "Asia/Manila", dateStyle: "medium", timeStyle: "short" }) : "—";

function Select({ label, value, choices, change }: { label: string; value?: string; choices?: ReportChoice[]; change: (value: string) => void }) {
  return <label>{label}<select value={value ?? ""} onChange={(event) => change(event.target.value)}><option value="">All</option>{choices?.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}</select></label>;
}

export default function FuelReferenceReportPage() {
  const [tab, setTab] = useState<Tab>("predictions");
  const [filters, setFilters] = useState<FuelReferenceFilters>(initial);
  const [report, setReport] = useState<FuelReferenceReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    fetchFuelReferenceReport(filters).then((result) => { if (active) setReport(result); }).catch(() => { if (active) setError("Unable to load this report."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [filters]);
  const setFilter = (key: keyof FuelReferenceFilters, value: string | number | undefined) => {
    setLoading(true); setError("");
    setFilters((current) => ({ ...current, [key]: value === "" ? undefined : value, [`${tab.slice(0, -1)}_page`]: 1 }));
  };
  const page = report?.[tab];
  return <main className="reports-page transport-report">
    <header className="reports-heading report-title-row"><div><p><Link to="/reports"><ChevronLeft /> Reports</Link> / Fuel Predictions &amp; Reference Data</p><h1>Fuel Predictions &amp; Reference Data</h1><span>Transparency for predicted rates and configured references—not actual consumption or expense.</span></div><div className="report-actions"><button onClick={() => downloadFuelReferenceCsv(tab, filters)}><Download /> Export CSV</button><button onClick={() => window.print()}><Printer /> Print</button></div></header>
    <section className="report-filters" aria-label="Report filters">
      <label>From<input type="date" value={filters.date_from} onChange={(event) => setFilter("date_from", event.target.value)} /></label>
      <label>To<input type="date" value={filters.date_to} onChange={(event) => setFilter("date_to", event.target.value)} /></label>
      {tab !== "prices" && <Select label="Vehicle" value={filters.vehicle} choices={report?.choices.vehicles} change={(value) => setFilter("vehicle", value)} />}
      {tab === "predictions" && <Select label="Prediction source" value={filters.prediction_source} choices={report?.choices.prediction_sources} change={(value) => setFilter("prediction_source", value)} />}
      {tab !== "predictions" && <><Select label="Fuel type" value={filters.fuel_type} choices={report?.choices.fuel_types} change={(value) => setFilter("fuel_type", value)} /><Select label="Fuel grade" value={filters.fuel_grade} choices={report?.choices.fuel_grades} change={(value) => setFilter("fuel_grade", value)} /></>}
      {tab === "prices" && <><Select label="Source" value={filters.price_source} choices={report?.choices.price_sources} change={(value) => setFilter("price_source", value)} /><Select label="Provider" value={filters.provider} choices={report?.choices.providers} change={(value) => setFilter("provider", value)} /></>}
      <button className="report-reset" onClick={() => { setLoading(true); setError(""); setFilters(initial()); }}><RefreshCw /> Reset</button>
    </section>
    {loading && <LoadingIndicator variant="card" message="Loading report…" />}
    {!loading && error && <section className="report-state"><p>{error}</p><button onClick={() => { setLoading(true); setError(""); setFilters((value) => ({ ...value })); }}>Retry</button></section>}
    {!loading && report && <>
      <section className="report-metadata"><span>Generated {dateTime(report.meta.generated_at)} by {report.meta.generated_by}</span><span>Prediction basis: input timestamp · Price basis: effective timestamp</span></section>
      <section className="report-kpis report-kpis-four" aria-label="Report summary">{[["Eligible Operational Predictions", report.summary.eligible_predictions], ["Vehicles with Reference Baselines", report.summary.vehicles_with_reference_baselines], ["Grades with Current Reference Price", report.summary.fuel_grades_with_current_reference_price], ["Latest Eligible Prediction", dateTime(report.summary.latest_eligible_prediction_at)]].map(([label, value]) => <article key={label}><strong>{value}</strong><span>{label}</span></article>)}</section>
      <section className="report-table-card"><div className="report-detail-tabs"><button className={tab === "predictions" ? "active" : ""} onClick={() => setTab("predictions")}>AI Predictions</button><button className={tab === "baselines" ? "active" : ""} onClick={() => setTab("baselines")}>Fleet Reference Baselines</button><button className={tab === "prices" ? "active" : ""} onClick={() => setTab("prices")}>Fuel Reference Prices</button></div><div className="report-table-scroll">
        {tab === "predictions" ? <table><thead><tr><th>Vehicle</th><th>Predicted L/h</th><th>Input / Predicted</th><th>Model</th><th>Source</th><th>Provenance</th></tr></thead><tbody>{report.predictions.results.map((row) => <tr key={row.id}><td>{row.vehicle.name}<small>{row.vehicle.identifier}</small></td><td>{row.estimated_fuel_lph}<small>Predicted—not actual</small></td><td>{dateTime(row.input_timestamp)}<small>{dateTime(row.predicted_at)}</small></td><td>{row.model_name}<small>{row.model_version}</small></td><td>{row.source_mode}</td><td><span className={`report-provenance ${row.operational_source ? "operational" : "simulated"}`}>{row.provenance_label}</span></td></tr>)}</tbody></table>
        : tab === "baselines" ? <table><thead><tr><th>Vehicle</th><th>Fuel</th><th>Reference L/h</th><th>Provenance</th><th>Basis</th><th>State</th></tr></thead><tbody>{report.baselines.results.map((row) => <tr key={row.id}><td>{row.vehicle.name}<small>{row.vehicle.identifier}</small></td><td>{row.fuel_type_label}<small>{row.fuel_grade_label}</small></td><td>{row.reference_fuel_rate_lph}</td><td><span className="report-provenance reference">{row.provenance_label}</span></td><td>{row.basis_version}</td><td>{row.is_active ? "Active" : "Inactive"}</td></tr>)}</tbody></table>
        : <table><thead><tr><th>Provider</th><th>Fuel</th><th>PHP/L</th><th>Source</th><th>Effective / Retrieved</th><th>State</th></tr></thead><tbody>{report.prices.results.map((row) => <tr key={row.id}><td>{row.provider}<small>Reference price</small></td><td>{row.fuel_type_label}<small>{row.fuel_grade_label}</small></td><td>{row.currency} {row.price_per_liter}</td><td>{row.source_mode_label}<small>{row.source_mode}</small></td><td>{dateTime(row.effective_at)}<small>{dateTime(row.retrieved_at)}</small></td><td>{row.is_active ? "Active" : "Inactive"}</td></tr>)}</tbody></table>}
        {page && !page.results.length && <p className="empty-report">No {tab === "predictions" ? "predictions" : tab === "baselines" ? "fleet reference baselines" : "fuel reference prices"} match the current filters.</p>}
      </div>{page && <footer><span>Showing {page.count ? (page.page - 1) * page.page_size + 1 : 0}–{Math.min(page.page * page.page_size, page.count)} of {page.count}</span><div><button disabled={page.page <= 1} onClick={() => setFilter(`${tab.slice(0, -1)}_page` as keyof FuelReferenceFilters, page.page - 1)}>Previous</button><span>Page {page.page} of {page.total_pages || 1}</span><button disabled={page.page >= page.total_pages} onClick={() => setFilter(`${tab.slice(0, -1)}_page` as keyof FuelReferenceFilters, page.page + 1)}>Next</button></div></footer>}</section>
    </>}
  </main>;
}
