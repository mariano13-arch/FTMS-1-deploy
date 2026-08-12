import { useState } from "react";
import type { TransportRequestListItem, TransportRoute } from "../types";
import { PriorityChip, WorkflowStatusBadge } from "./RequestIndicators";

type OverviewTab = "Overview" | "Route" | "Activity";
const tabs: OverviewTab[] = ["Overview", "Route", "Activity"];
const label = (value: string) => value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, character => character.toUpperCase());

export default function SelectedRequestOverview({ request, route, routeState, onViewDetails }: {
  request: TransportRequestListItem | null;
  route?: TransportRoute | null;
  routeState: "idle" | "loading" | "ready" | "error";
  onViewDetails: (trigger: HTMLButtonElement) => void;
}) {
  const [tab, setTab] = useState<OverviewTab>("Overview");
  if (!request) return <section className="selected-request-overview selected-request-overview--empty" aria-labelledby="selected-request-overview-title"><h2 id="selected-request-overview-title">Selected Request Overview</h2><p>Select a request from the queue to view its operational summary.</p></section>;
  const delivery = request.request_category === "DELIVERY_LOGISTICS";
  return <section className="selected-request-overview" aria-labelledby="selected-request-overview-title"><header><div><h2 id="selected-request-overview-title">Selected Request Overview</h2><strong>{request.request_number}</strong></div><button type="button" className="button--secondary" onClick={event => onViewDetails(event.currentTarget)}>View Details</button></header>
    <div className="selected-overview-tabs" role="tablist" aria-label="Selected request overview sections">{tabs.map(item => <button key={item} type="button" role="tab" aria-selected={tab === item} aria-controls={`selected-overview-${item.toLowerCase()}`} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{item}</button>)}</div>
    <div id={`selected-overview-${tab.toLowerCase()}`} className="selected-overview-tab-panel" role="tabpanel">
      {tab === "Overview" && <div className="selected-overview-grid"><section><h3>Identity / Workflow</h3><dl><div><dt>Reference</dt><dd>{request.request_number}</dd></div><div><dt>Type</dt><dd>{label(request.request_type)}</dd></div><div><dt>Category</dt><dd>{request.request_category ? label(request.request_category) : label(request.request_type)}</dd></div><div><dt>Priority</dt><dd><PriorityChip value={request.priority} /></dd></div><div><dt>Status</dt><dd><WorkflowStatusBadge value={request.status} /></dd></div><div><dt>Source</dt><dd>{label(request.source_system)}</dd></div>{request.external_reference && <div><dt>External reference</dt><dd>{request.external_reference}</dd></div>}</dl></section><section><h3>Schedule</h3><dl><div><dt>Scheduled pickup</dt><dd>{new Date(request.scheduled_pickup_at).toLocaleString()}</dd></div><div><dt>Planning window</dt><dd>{request.estimated_duration_minutes} min</dd></div></dl></section><section><h3>{delivery ? "Delivery summary" : "Passenger summary"}</h3><dl>{delivery ? <>{request.load_description && <div><dt>Load</dt><dd>{request.load_description}</dd></div>}{request.load_quantity !== null && <div><dt>Quantity</dt><dd>{request.load_quantity}</dd></div>}{request.estimated_weight_kg && <div><dt>Estimated weight</dt><dd>{request.estimated_weight_kg} kg</dd></div>}{request.handling_instructions && <div><dt>Handling</dt><dd>{request.handling_instructions}</dd></div>}{request.temperature_requirement && <div><dt>Temperature</dt><dd>{request.temperature_requirement}</dd></div>}</> : <><div><dt>Passengers</dt><dd>{request.passenger_count}</dd></div>{request.luggage_count > 0 && <div><dt>Luggage items</dt><dd>{request.luggage_count}</dd></div>}</>}</dl></section></div>}
      {tab === "Route" && <div className="selected-overview-grid selected-overview-grid--route"><section><h3>Locations</h3><dl><div><dt>Pickup</dt><dd>{request.pickup_name || "Location unavailable"}</dd></div><div><dt>Destination</dt><dd>{request.destination_name || "Location unavailable"}</dd></div></dl></section><section><h3>Road route</h3>{routeState === "ready" && route ? <dl><div><dt>Distance</dt><dd>{(route.distance_meters / 1000).toFixed(1)} km</dd></div><div><dt>Travel time</dt><dd>{Math.round(route.duration_seconds / 60)} min</dd></div>{route.traffic_delay_seconds > 0 && <div><dt>Traffic delay</dt><dd>+{Math.round(route.traffic_delay_seconds / 60)} min</dd></div>}</dl> : <p className="selected-overview-state">{routeState === "loading" ? "Calculating route…" : routeState === "error" ? "Route unavailable" : "Not calculated"}</p>}</section></div>}
      {tab === "Activity" && (request.latest_event_type ? <ol className="selected-overview-activity"><li><span aria-hidden="true" /><div><strong>{label(request.latest_event_type)}</strong>{request.latest_event_at && <time>{new Date(request.latest_event_at).toLocaleString()}</time>}</div></li></ol> : <p className="selected-overview-state selected-overview-state--empty">No recorded request activity is available yet.</p>)}
    </div>
  </section>;
}
