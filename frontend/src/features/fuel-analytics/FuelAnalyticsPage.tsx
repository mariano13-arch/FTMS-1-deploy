import { useEffect, useMemo, useState } from "react";
import {
  getFuelDashboard,
  getFuelModelInfo,
  getFuelReadiness,
  type FuelDashboard,
  type FuelDashboardRange,
  type FuelDashboardVehicle,
  type FuelModelInfo,
  type FuelReadiness,
} from "./api";

const featureLabel = (value: string) => value
  .replaceAll("_", " ")
  .replace("km per h", "km/h")
  .replace(" pct", " (%)")
  .replace(/\b\w/g, letter => letter.toUpperCase());

const dateTime = (value: string | null) => value
  ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })
  : "—";

const statusLabel = (status: string) => ({
  prediction_available: "Available",
  demo_ready: "Demo Ready",
  prediction_blocked: "Blocked",
  invalid_input: "Invalid input",
  model_unavailable: "Model unavailable",
  no_telemetry: "No telemetry",
}[status] ?? status);

const fuelTabs = [
  { id: "overview", label: "Overview" },
  { id: "fleet-status", label: "Fleet Status" },
  { id: "input-readiness", label: "Input Readiness" },
  { id: "model-details", label: "Model Details" },
] as const;
type FuelTab = typeof fuelTabs[number]["id"];

function FuelTrendChart({ dashboard }: { dashboard: FuelDashboard }) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const points = dashboard.trend;
  if (points.length === 0) return <div className="fuel-chart-empty"><strong>No prediction history yet</strong><span>Validated model predictions will appear here once all required operational inputs are available.</span></div>;
  const values = points.map(point => point.estimated_fuel_lph);
  const rawMinimum = Math.min(...values);
  const rawMaximum = Math.max(...values);
  const padding = Math.max((rawMaximum - rawMinimum) * 0.18, rawMaximum * 0.08, 0.25);
  const minimum = Math.max(0, rawMinimum - padding);
  const maximum = rawMaximum + padding;
  const spread = maximum - minimum;
  const plot = { left: 64, right: 576, top: 24, bottom: 188 };
  const coordinates = points.map((point, index) => ({
    ...point,
    x: points.length === 1 ? (plot.left + plot.right) / 2 : plot.left + (index / (points.length - 1)) * (plot.right - plot.left),
    y: plot.bottom - ((point.estimated_fuel_lph - minimum) / spread) * (plot.bottom - plot.top),
  }));
  const linePath = coordinates.slice(1).reduce((path, point, index) => {
    const previous = coordinates[index];
    const middle = (previous.x + point.x) / 2;
    return `${path} C ${middle} ${previous.y}, ${middle} ${point.y}, ${point.x} ${point.y}`;
  }, `M ${coordinates[0].x} ${coordinates[0].y}`);
  const areaPath = `${linePath} L ${coordinates.at(-1)?.x} ${plot.bottom} L ${coordinates[0].x} ${plot.bottom} Z`;
  const average = values.reduce((total, value) => total + value, 0) / values.length;
  const current = points.at(-1)!;
  const activePoint = activeIndex === null ? null : coordinates[activeIndex];
  const yTicks = Array.from({ length: 5 }, (_, index) => maximum - index * spread / 4);
  const tooltipX = activePoint ? Math.min(Math.max(activePoint.x - 60, plot.left), plot.right - 120) : 0;
  const tooltipY = activePoint ? Math.max(activePoint.y - 54, plot.top) : 0;
  return <div className="fuel-trend-plot">
    <div className="fuel-trend-stats" aria-label="Prediction trend summary">
      <article><small>Current estimate</small><strong>{current.estimated_fuel_lph.toFixed(2)} L/h</strong><span>{dateTime(current.timestamp)}</span></article>
      <article><small>Average estimate</small><strong>{average.toFixed(2)} L/h</strong><span>{points.length} persisted {points.length === 1 ? "point" : "points"}</span></article>
      <article><small>Observed prediction range</small><strong>{rawMinimum.toFixed(2)}–{rawMaximum.toFixed(2)} L/h</strong><span>Model estimates only</span></article>
    </div>
    <svg viewBox="0 0 600 220" role="img" aria-label={`Estimated fuel-rate trend with ${points.length} persisted prediction ${points.length === 1 ? "point" : "points"}`} onMouseLeave={() => setActiveIndex(null)}>
      <title>Persisted estimated fuel rate in liters per hour over time</title>
      <defs><linearGradient id="fuelTrendArea" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#008f8c" stopOpacity=".34" /><stop offset="72%" stopColor="#55b8b1" stopOpacity=".09" /><stop offset="100%" stopColor="#ffffff" stopOpacity="0" /></linearGradient><filter id="fuelTrendGlow"><feGaussianBlur stdDeviation="2.4" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter></defs>
      {yTicks.map((value, index) => { const y = plot.top + index * (plot.bottom - plot.top) / 4; return <g key={value}><line className="fuel-chart-grid" x1={plot.left} x2={plot.right} y1={y} y2={y} /><text className="fuel-chart-y-label" x={plot.left - 10} y={y + 3}>{value.toFixed(1)}</text></g>; })}
      <text className="fuel-chart-unit" x="14" y="16">L/h</text>
      <path className="fuel-trend-area" d={areaPath} />
      {coordinates.length > 1 && <path className="fuel-trend-line-glow" d={linePath} />}
      {coordinates.length > 1 && <path className="fuel-trend-line" d={linePath} />}
      {coordinates.map((point, index) => <circle className={activeIndex === index ? "fuel-trend-point active" : "fuel-trend-point"} key={point.timestamp} cx={point.x} cy={point.y} r={activeIndex === index ? 5 : 3.7} tabIndex={0} onMouseEnter={() => setActiveIndex(index)} onFocus={() => setActiveIndex(index)} onBlur={() => setActiveIndex(null)}><title>{dateTime(point.timestamp)}: {point.estimated_fuel_lph.toFixed(2)} L/h model estimate</title></circle>)}
      {activePoint && <g className="fuel-chart-tooltip" transform={`translate(${tooltipX} ${tooltipY})`}><rect width="120" height="42" rx="5" /><text x="9" y="15">{activePoint.estimated_fuel_lph.toFixed(2)} L/h estimate</text><text className="fuel-chart-tooltip-time" x="9" y="30">{dateTime(activePoint.timestamp)}</text></g>}
    </svg>
    <div className="fuel-chart-axis"><span>{dateTime(points[0].timestamp)}</span><strong>Estimated Fuel Rate (L/h)</strong><span>{dateTime(points.at(-1)?.timestamp ?? null)}</span></div>
    <p className="fuel-trend-disclosure">Persisted model estimates only. Actual measured fuel and a validated prediction interval are not available.</p>
  </div>;
}

function ReadinessChart({ dashboard }: { dashboard: FuelDashboard }) {
  const groups = [
    ["Ready", dashboard.readiness_breakdown.ready, "ready"],
    ["Demo/Test", dashboard.readiness_breakdown.demo_ready, "demo"],
    ["Blocked", dashboard.readiness_breakdown.blocked, "blocked"],
    ["No telemetry", dashboard.readiness_breakdown.no_telemetry, "no-telemetry"],
    ["Model unavailable", dashboard.readiness_breakdown.model_unavailable, "unavailable"],
  ] as const;
  const total = groups.reduce((sum, group) => sum + group[1], 0);
  let offset = 0;
  return <div className="fuel-readiness-chart">
    <svg viewBox="0 0 120 120" role="img" aria-label={`Prediction readiness for ${total} fleet vehicles`}>
      <title>Prediction readiness status breakdown</title>
      <circle className="fuel-ring-base" cx="60" cy="60" r="42" />
      {total > 0 && groups.map(([label, value, kind]) => {
        const length = value / total * 100;
        const segment = <circle key={label} className={`fuel-ring-segment fuel-ring-segment--${kind}`} cx="60" cy="60" r="42" pathLength="100" strokeDasharray={`${length} ${100 - length}`} strokeDashoffset={-offset}><title>{label}: {value}</title></circle>;
        offset += length;
        return segment;
      })}
      <text x="60" y="57">{total}</text><text className="fuel-ring-caption" x="60" y="70">vehicles</text>
    </svg>
    <ul>{groups.map(([label, value, kind]) => <li key={label}><i className={`fuel-key fuel-key--${kind}`} /><span>{label}</span><strong>{value}</strong></li>)}</ul>
  </div>;
}

function VehicleComparison({ dashboard }: { dashboard: FuelDashboard }) {
  if (dashboard.vehicle_comparison.length === 0) return <div className="fuel-chart-empty fuel-chart-empty--short"><strong>No vehicle estimates available</strong><span>Only successful persisted model estimates appear in this comparison.</span></div>;
  const ranked = [...dashboard.vehicle_comparison].sort((first, second) => second.estimated_fuel_lph - first.estimated_fuel_lph);
  const maximum = Math.max(...ranked.map(item => item.estimated_fuel_lph));
  return <div className="fuel-comparison-bars" role="img" aria-label="Latest model-estimated fuel rate comparison by vehicle">
    {ranked.map((item, index) => <div className="fuel-comparison-row" key={item.vehicle_id}>
      <b className="fuel-comparison-rank">{index + 1}</b>
      <span><strong>{item.vehicle_name}</strong><small>{item.plate_number}{item.is_demo_prediction ? " · Demo/Test" : ""}</small></span>
      <div className="fuel-comparison-track"><i className={item.is_demo_prediction ? "demo" : ""} style={{ width: `${item.estimated_fuel_lph / maximum * 100}%` }} /></div>
      <strong className="fuel-comparison-value">{item.estimated_fuel_lph.toFixed(2)} L/h</strong>
      <span className={item.is_demo_prediction ? "fuel-comparison-badge demo" : "fuel-comparison-badge"}>{item.is_demo_prediction ? "Demo/Test" : "Model estimate"}</span>
    </div>)}
  </div>;
}

function VehicleDetail({ vehicle, onClose }: { vehicle: FuelDashboardVehicle; onClose: () => void }) {
  const readiness = vehicle.input_readiness;
  return <aside className="fuel-details-drawer" role="dialog" aria-label={`${vehicle.vehicle_name} fuel detail`}>
    <header><div><small>Vehicle fuel record</small><h3>{vehicle.vehicle_name}</h3><span>{vehicle.plate_number} · {vehicle.device_id}</span></div><button type="button" aria-label="Close vehicle fuel detail" onClick={onClose}>×</button></header>
    <div className="fuel-details-drawer-body">
      <section><h4>Latest Fuel Analytics</h4><dl><div><dt>Prediction status</dt><dd>{statusLabel(vehicle.prediction_status)}</dd></div><div><dt>Latest estimate</dt><dd>{vehicle.latest_estimated_fuel_lph === null ? "—" : `${vehicle.latest_estimated_fuel_lph.toFixed(2)} L/h`}</dd></div><div><dt>Source</dt><dd>{vehicle.prediction_source_label ?? "No prediction"}</dd></div><div><dt>Last prediction</dt><dd>{dateTime(vehicle.last_prediction_at)}</dd></div></dl>{vehicle.is_demo_prediction && <p className="fuel-demo-inline-note">DEMO / TEST / RESEARCH — not an operational fuel measurement.</p>}</section>
      <section><h4>Telemetry</h4><dl><div><dt>Telemetry status</dt><dd>{vehicle.telemetry_status === "available" ? "Available" : "No telemetry"}</dd></div><div><dt>Telemetry timestamp</dt><dd>{dateTime(vehicle.telemetry_timestamp)}</dd></div></dl></section>
      {vehicle.latest_prediction_inputs.length > 0 && <section><h4>Latest Model Inputs</h4><div className="fuel-model-input-list">{vehicle.latest_prediction_inputs.map(input => <div key={input.feature}><span><strong>{featureLabel(input.feature)}</strong><small>{input.source}</small></span><b>{input.value.toLocaleString()}{input.unit ? ` ${input.unit}` : ""}</b></div>)}</div></section>}
      <section><h4>Input Readiness</h4><div className="fuel-drawer-readiness-summary"><strong>{readiness.available_count} / {readiness.required_count} inputs</strong><span>Missing {readiness.missing_features.length} · Unverified {readiness.unverified_features.length}</span></div><div className="fuel-detail-readiness"><div><strong>Missing</strong>{readiness.missing_features.length ? <ul>{readiness.missing_features.map(item => <li key={item}>{featureLabel(item)}</li>)}</ul> : <span>None</span>}</div><div><strong>Unverified</strong>{readiness.unverified_features.length ? <ul>{readiness.unverified_features.map(item => <li key={item}>{featureLabel(item)}</li>)}</ul> : <span>None</span>}</div></div></section>
    </div>
  </aside>;
}

export default function FuelAnalyticsPage() {
  const [model, setModel] = useState<FuelModelInfo | null>(null);
  const [readiness, setReadiness] = useState<FuelReadiness | null>(null);
  const [dashboard, setDashboard] = useState<FuelDashboard | null>(null);
  const [range, setRange] = useState<FuelDashboardRange>("24h");
  const [vehicleId, setVehicleId] = useState<number | null>(null);
  const [searchValue, setSearchValue] = useState("");
  const [tableSearch, setTableSearch] = useState("");
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [selectedRow, setSelectedRow] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<FuelTab>("overview");
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      getFuelModelInfo(controller.signal),
      getFuelReadiness(controller.signal),
      getFuelDashboard(range, vehicleId, tableSearch, controller.signal),
    ]).then(([modelInfo, readinessInfo, dashboardInfo]) => {
      setModel(modelInfo);
      setReadiness(readinessInfo);
      setDashboard(dashboardInfo);
      setState("ready");
    }).catch(reason => {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) setState("error");
    });
    return () => controller.abort();
  }, [range, vehicleId, tableSearch]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setTableSearch(searchValue.trim());
      setSelectedRow(null);
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [searchValue]);

  const selectedVehicle = useMemo(() => dashboard?.vehicles.find(item => item.vehicle_id === selectedRow) ?? null, [dashboard, selectedRow]);
  if (state === "loading") return <section className="fuel-analytics-page"><div className="fuel-analytics-state" role="status">Loading Fleet Fuel Analytics…</div></section>;
  if (state === "error" || !model || !readiness || !dashboard) return <section className="fuel-analytics-page"><div className="fuel-analytics-state fuel-analytics-state--error" role="alert"><strong>Fuel Analytics backend unavailable</strong><span>Dashboard, model, or readiness information could not be loaded.</span></div></section>;
  const normalizedSearch = searchValue.trim().toLowerCase();
  const searchSuggestions = normalizedSearch
    ? dashboard.vehicle_options.filter(vehicle => [vehicle.vehicle_name, vehicle.plate_number, vehicle.device_id].some(value => value.toLowerCase().includes(normalizedSearch))).slice(0, 6)
    : [];
  const displayingDemoAverage = dashboard.summary.average_estimated_fuel_lph === null && dashboard.summary.demo_average_estimated_fuel_lph !== null;
  const displayedAverage = dashboard.summary.average_estimated_fuel_lph ?? dashboard.summary.demo_average_estimated_fuel_lph;

  return <section className="fuel-analytics-page">
    <header className="fuel-dashboard-header"><div><p className="breadcrumb">Operations / Fuel Analytics</p><h1>Fleet Fuel Analytics</h1></div></header>
    {dashboard.model_availability === "unavailable" && <div className="fuel-dashboard-alert" role="alert">The selected model is unavailable. Historical estimates remain visible, but new inference cannot run.</div>}
    {dashboard.demo_data_present && <div className="fuel-demo-data-note" role="note"><strong>DEMO ANALYTICS DATA</strong><span>{dashboard.demo_data_note}</span></div>}
    <nav className="fuel-dashboard-tabs" role="tablist" aria-label="Fuel Analytics views">{fuelTabs.map(tab => {
      const count = tab.id === "fleet-status" ? dashboard.summary.vehicle_count : tab.id === "input-readiness" ? readiness.inputs.length : null;
      return <button id={`fuel-tab-${tab.id}`} type="button" role="tab" aria-selected={activeTab === tab.id} aria-controls={`fuel-panel-${tab.id}`} className={activeTab === tab.id ? "active" : ""} key={tab.id} onClick={() => { setActiveTab(tab.id); setSelectedRow(null); }}>{tab.label}{count !== null && <span>{count}</span>}</button>;
    })}</nav>
    {activeTab === "overview" && <div id="fuel-panel-overview" className="fuel-dashboard-tab-panel" role="tabpanel" aria-labelledby="fuel-tab-overview">
    <div className="fuel-kpi-grid">
      <article><small>Fleet Vehicles</small><strong>{dashboard.summary.vehicle_count}</strong><span>Active registered vehicles</span></article>
      <article><small>Prediction Ready</small><strong>{dashboard.summary.prediction_ready_count}</strong><span>Operational only{dashboard.summary.demo_ready_count ? ` · ${dashboard.summary.demo_ready_count} Demo/Test ready` : ""}</span></article>
      <article><small>Average Estimated Fuel Rate</small><strong>{displayedAverage === null ? "—" : `${displayedAverage.toFixed(2)} L/h`}</strong><span>{displayedAverage === null ? "No successful estimates" : displayingDemoAverage ? "Demo/Test Dataset" : "Operational model estimates only"}</span></article>
      <article><small>Prediction Blocked</small><strong>{dashboard.summary.prediction_blocked_count}</strong><span>Includes missing telemetry or inputs</span></article>
    </div>
    <div className="fuel-dashboard-primary-grid">
      <section className="fuel-dashboard-card fuel-trend-card"><header><div><small>Persisted successful predictions</small><h2>Estimated Fuel Consumption Trend</h2></div><div className="fuel-chart-filters"><label>Vehicle<select aria-label="Trend vehicle" value={vehicleId ?? ""} onChange={event => setVehicleId(event.target.value ? Number(event.target.value) : null)}><option value="">All Vehicles</option>{dashboard.vehicle_options.map(vehicle => <option key={vehicle.vehicle_id} value={vehicle.vehicle_id}>{vehicle.vehicle_name} · {vehicle.plate_number}</option>)}</select></label><div role="group" aria-label="Trend time range">{(["24h", "7d", "30d"] as const).map(value => <button className={range === value ? "active" : ""} key={value} type="button" aria-pressed={range === value} onClick={() => setRange(value)}>{value === "24h" ? "24 Hours" : value === "7d" ? "7 Days" : "30 Days"}</button>)}</div></div></header><FuelTrendChart dashboard={dashboard} /><p className="fuel-chart-note">{dashboard.filters.selected_vehicle ? dashboard.filters.selected_vehicle.vehicle_name : "All Vehicles"} · {dashboard.filters.trend_aggregation}; blocked vehicles are excluded.</p></section>
      <section className="fuel-dashboard-card fuel-readiness-summary"><header><div><small>Current fleet states</small><h2>Prediction Readiness</h2></div></header><ReadinessChart dashboard={dashboard} /></section>
    </div>
    <section className="fuel-dashboard-card"><header><div><small>Latest successful result per vehicle</small><h2>Vehicle Fuel Rate Comparison</h2></div></header><VehicleComparison dashboard={dashboard} /></section>
    </div>}
    {activeTab === "fleet-status" && <div id="fuel-panel-fleet-status" className="fuel-dashboard-tab-panel" role="tabpanel" aria-labelledby="fuel-tab-fleet-status"><section className="fuel-dashboard-card fuel-table-card"><header><div><small>Operational vehicle status</small><h2>Fleet Fuel Status</h2></div><label className="fuel-vehicle-search">Search vehicles<input type="search" role="combobox" aria-autocomplete="list" aria-controls="fuel-vehicle-search-options" aria-expanded={suggestionsOpen && Boolean(normalizedSearch)} placeholder="Name, plate or device ID" value={searchValue} onFocus={() => setSuggestionsOpen(true)} onBlur={() => window.setTimeout(() => setSuggestionsOpen(false), 100)} onChange={event => { setSearchValue(event.target.value); setSuggestionsOpen(true); if (!event.target.value) setTableSearch(""); }} onKeyDown={event => { if (event.key === "Escape") setSuggestionsOpen(false); }} />{suggestionsOpen && normalizedSearch && <div id="fuel-vehicle-search-options" className="fuel-vehicle-search-options" role="listbox">{searchSuggestions.length ? searchSuggestions.map(vehicle => <button type="button" role="option" aria-selected="false" key={vehicle.vehicle_id} onMouseDown={event => event.preventDefault()} onClick={() => { setSearchValue(vehicle.vehicle_name); setTableSearch(vehicle.vehicle_name); setSuggestionsOpen(false); setSelectedRow(null); }}><strong>{vehicle.vehicle_name}</strong><small>{vehicle.plate_number} · {vehicle.device_id}</small></button>) : <span>No matching vehicles</span>}</div>}</label></header><div className={`fuel-table-workspace${selectedVehicle ? " fuel-table-workspace--drawer-open" : ""}`}><div className="fuel-table-list-panel"><div className="fuel-table-wrap"><table><thead><tr><th>Vehicle</th><th>Plate Number</th><th>Telemetry</th><th>Latest Estimated Fuel Rate</th><th>Prediction Status</th><th>Last Prediction</th><th>Input Readiness</th><th>Action</th></tr></thead><tbody>{dashboard.vehicles.length === 0 ? <tr><td colSpan={8}>{tableSearch ? "No vehicles match your search." : "No active fleet vehicles registered."}</td></tr> : dashboard.vehicles.map(vehicle => <tr className={selectedRow === vehicle.vehicle_id ? "selected" : ""} key={vehicle.vehicle_id}><td><strong>{vehicle.vehicle_name}</strong><small>{vehicle.device_id}</small></td><td>{vehicle.plate_number}</td><td><span className={`fuel-status fuel-status--${vehicle.telemetry_status}`}>{vehicle.telemetry_status === "available" ? "Available" : "No telemetry"}</span><small>{dateTime(vehicle.telemetry_timestamp)}</small></td><td>{!["prediction_available", "demo_ready"].includes(vehicle.prediction_status) || vehicle.latest_estimated_fuel_lph === null ? <strong>—</strong> : <><strong>{vehicle.latest_estimated_fuel_lph.toFixed(2)} L/h</strong><small>{vehicle.is_demo_prediction ? "Demo/Test estimate" : "Model estimate"}</small></>}</td><td><span className={`fuel-status fuel-status--${vehicle.prediction_status}`}>{statusLabel(vehicle.prediction_status)}</span>{vehicle.prediction_source_label && <small>Source: {vehicle.prediction_source_label}</small>}</td><td>{dateTime(vehicle.last_prediction_at)}</td><td><strong>{vehicle.input_readiness.available_count} / {vehicle.input_readiness.required_count} inputs</strong><small>Missing {vehicle.input_readiness.missing_features.length} · Unverified {vehicle.input_readiness.unverified_features.length}</small></td><td><button type="button" onClick={() => setSelectedRow(vehicle.vehicle_id)}>View</button></td></tr>)}</tbody></table></div><footer className="fuel-table-pagination fuel-table-pagination--summary"><span>{tableSearch ? `${dashboard.vehicle_pagination.total_count} matching vehicle${dashboard.vehicle_pagination.total_count === 1 ? "" : "s"}` : `Showing ${dashboard.vehicle_pagination.end} of ${dashboard.summary.vehicle_count} vehicles`}</span></footer></div>{selectedVehicle && <VehicleDetail vehicle={selectedVehicle} onClose={() => setSelectedRow(null)} />}</div></section></div>}
    {activeTab === "input-readiness" && <div id="fuel-panel-input-readiness" className="fuel-dashboard-tab-panel" role="tabpanel" aria-labelledby="fuel-tab-input-readiness"><section className="fuel-dashboard-card fuel-input-card"><header><div><small>Operational source mapping</small><h2>Model Input Readiness</h2></div><span>{readiness.inputs.filter(item => item.status === "available").length} of {readiness.inputs.length} mapped</span></header><div className="fuel-readiness-list">{readiness.inputs.map(input => <article key={input.feature}><span className={`fuel-readiness-status fuel-readiness-status--${input.status}`}>{input.status}</span><div><strong>{featureLabel(input.feature)}</strong><small>{input.source ?? input.note}</small></div></article>)}</div></section></div>}
    {activeTab === "model-details" && <div id="fuel-panel-model-details" className="fuel-dashboard-tab-panel" role="tabpanel" aria-labelledby="fuel-tab-model-details"><section className="fuel-dashboard-card fuel-model-details"><header><div><small>Technical reference</small><h2>Model &amp; Analytics Details</h2></div><strong>R² {model.metrics.r2.toFixed(4)}</strong></header><dl><div><dt>Model</dt><dd>Experiment 3 Tuned XGBoost</dd></div><div><dt>Target</dt><dd>Estimated Fuel L/h</dd></div><div><dt>MAE</dt><dd>{model.metrics.mae_lph.toFixed(4)} L/h</dd></div><div><dt>RMSE</dt><dd>{model.metrics.rmse_lph.toFixed(4)} L/h</dd></div><div><dt>Role</dt><dd>{model.model_role}</dd></div><div><dt>Actual measured fuel</dt><dd>Not available</dd></div></dl><p>{model.accuracy_note} Every numeric result on this dashboard is a model estimate, not actual measured or billing-grade fuel consumption.</p></section></div>}
  </section>;
}
