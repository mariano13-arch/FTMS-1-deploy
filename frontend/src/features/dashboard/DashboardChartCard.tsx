import type { DashboardValue, DashboardWidget } from "./api";

export type ChartKind = "donut" | "bar" | "horizontal" | "line";

const colors = ["#8f1d35", "#247ba0", "#16827a", "#d69e2e", "#7656a7", "#c05640", "#4f6d7a"];
const semanticColors: Record<string, string> = {
  ACTIVE: "#2f855a", APPROVED: "#2f855a", PASSED: "#2f855a", COMPLETED_TODAY: "#2f855a",
  READY_FOR_DISPATCH: "#16827a", CURRENTLY_ASSIGNED: "#247ba0", BOUND: "#247ba0", REGISTERED: "#247ba0", GENUINE_RECENT: "#16827a",
  FOR_APPROVAL: "#d69e2e", NEEDS_MORE_DETAILS: "#d69e2e", NEEDS_ATTENTION: "#d69e2e", SCHEDULED: "#d69e2e", FLEET_REFERENCE_BASELINE: "#d69e2e",
  REJECTED: "#8f1d35", CANCELLED: "#8f1d35", FAILED: "#b83248", INACTIVE: "#8f1d35", UNAVAILABLE: "#8f1d35", RESTRICTED_ENTRY: "#b83248",
  CURRENT_AI: "#16827a", HISTORICAL_AI_BASELINE: "#7656a7", IN_PROGRESS: "#7656a7", OPEN: "#c05640",
};
const colorFor = (item: DashboardValue, index: number) => semanticColors[item.value] ?? colors[index % colors.length];

function Donut({ values }: { values: DashboardValue[] }) {
  const total = values.reduce((sum, item) => sum + item.count, 0);
  let offset = 0;
  return (
    <div className="dashboard-donut-wrap">
      <svg className="dashboard-donut" viewBox="0 0 42 42" role="img" aria-label="Chart breakdown">
        <circle className="dashboard-donut-track" cx="21" cy="21" r="15.9" />
        {total > 0 && values.map((item, index) => {
          const length = (item.count / total) * 100;
          const segment = <circle key={item.value} cx="21" cy="21" r="15.9" fill="none" stroke={colorFor(item, index)} strokeWidth="8" strokeDasharray={`${length} ${100 - length}`} strokeDashoffset={-offset} pathLength="100"><title>{item.label}: {item.count}</title></circle>;
          offset += length;
          return segment;
        })}
      </svg>
      <span><strong>{total}</strong><small>Total</small></span>
    </div>
  );
}

function Bars({ values, horizontal = false }: { values: DashboardValue[]; horizontal?: boolean }) {
  const max = Math.max(1, ...values.map((item) => item.count));
  return <div className={horizontal ? "dashboard-hbars" : "dashboard-bars"}>{values.map((item, index) => (
    <div key={item.value} title={`${item.label}: ${item.count}`}>
      <span>{horizontal ? item.label : item.count}</span>
      <i style={horizontal ? { width: `${(item.count / max) * 100}%`, background: colorFor(item, index) } : { height: `${(item.count / max) * 100}%`, background: colorFor(item, index) }} />
      <small>{horizontal ? item.count : item.label}</small>
    </div>
  ))}</div>;
}

function Line({ values }: { values: DashboardValue[] }) {
  const max = Math.max(1, ...values.map((item) => item.count));
  const points = values.map((item, index) => `${values.length === 1 ? 50 : (index / (values.length - 1)) * 100},${92 - (item.count / max) * 75}`).join(" ");
  return <div className="dashboard-line"><svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Daily completion trend"><polygon points={`0,94 ${points} 100,94`} /><polyline points={points} /><g>{values.map((item, index) => <circle key={item.value} cx={values.length === 1 ? 50 : (index / (values.length - 1)) * 100} cy={92 - (item.count / max) * 75} r="2.4"><title>{item.label}: {item.count}</title></circle>)}</g></svg><div>{values.map(item => <small key={item.value}>{item.label}</small>)}</div></div>;
}

export default function DashboardChartCard({ title, widget, kind, emptyMessage, selected, onSelect }: { title: string; widget: DashboardWidget; kind: ChartKind; emptyMessage: string; selected: boolean; onSelect: () => void }) {
  const empty = widget.values.every((item) => item.count === 0);
  return <button type="button" className={`dashboard-chart-card${selected ? " selected" : ""}`} onClick={onSelect} aria-pressed={selected}>
    <header><h2>{title}</h2><span>{widget.scope}</span></header>
    <div className="dashboard-chart-area">
      {empty ? <div className="dashboard-chart-empty"><i /><strong>{emptyMessage}</strong><span>0 recorded</span></div> : <>
        {kind === "donut" && <Donut values={widget.values} />}
        {kind === "bar" && <Bars values={widget.values} />}
        {kind === "horizontal" && <Bars values={widget.values} horizontal />}
        {kind === "line" && <Line values={widget.values} />}
      </>}
    </div>
    <div className="dashboard-legend">{widget.values.slice(0, 7).map((item, index) => <span key={item.value}><i style={{ background: colorFor(item, index) }} />{item.label} <strong>{item.count}</strong></span>)}</div>
  </button>;
}
