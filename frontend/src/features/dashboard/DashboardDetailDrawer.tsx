import { ArrowRight, X } from "lucide-react";
import { Link } from "react-router-dom";
import type { DashboardWidget } from "./api";

export default function DashboardDetailDrawer({ title, widget, onClose }: { title: string; widget: DashboardWidget; onClose: () => void }) {
  return <aside className="dashboard-detail" aria-label={`${title} details`}>
    <header><div><span>{widget.scope}</span><h2>{title}</h2></div><button type="button" onClick={onClose} aria-label="Close dashboard details"><X /></button></header>
    <section><div className="dashboard-classification"><span>{widget.classification}</span><strong>{widget.total}</strong></div><p>{widget.description}</p></section>
    <section><h3>Exact breakdown</h3><dl>{widget.values.map(item => <div key={item.value}><dt>{item.label}</dt><dd>{item.count}</dd></div>)}</dl></section>
    {widget.secondary && <section><h3>Vehicle types</h3><dl>{widget.secondary.map(item => <div key={item.value}><dt>{item.label}</dt><dd>{item.count}</dd></div>)}</dl></section>}
    {widget.recent && widget.recent.length > 0 && <section><h3>Recent records</h3><ul>{widget.recent.map(item => <li key={item.id}><strong>{item.label}</strong><span>{item.detail}</span><small>{new Date(item.occurred_at).toLocaleString()}{item.provenance ? ` · ${item.provenance}` : ""}</small>{item.location === null && <small>Location not stored</small>}</li>)}</ul></section>}
    <section><h3>Data provenance</h3><p>{widget.provenance}</p></section>
    <footer><Link to={widget.module_url}>Open full module <ArrowRight /></Link></footer>
  </aside>;
}
