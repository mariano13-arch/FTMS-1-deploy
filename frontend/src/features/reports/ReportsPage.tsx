import { Link } from "react-router-dom";
import { BarChart3 } from "lucide-react";
import "./reports.css";

const reports = [
  { title: "Transport Request Summary", description: "Created requests, decisions, dispatch readiness, and filtered request details.", to: "/reports/transport-requests" },
  { title: "Dispatch & Trip Execution", description: "Confirmed assignments, driver acceptance, and actual trip execution.", to: "/reports/dispatch-trips" },
  { title: "Fleet Assignment Summary", description: "Vehicle and driver assignment reporting.", to: "/reports/fleet-assignments" },
  { title: "Inspection & Maintenance", description: "Inspection outcomes and maintenance activity.", to: "/reports/inspection-maintenance" },
  { title: "Safety, Geofence & SOS Activity", description: "Operational driver safety, geofence transitions, and emergency activity.", to: "/reports/safety-geofence" },
  { title: "Device & Telemetry Availability", description: "Device registry, binding history, and telemetry availability.", to: "/reports/device-telemetry" },
  { title: "Fuel Predictions & Reference Data", description: "Predicted fuel rates, fleet reference baselines, and reference prices.", to: "/reports/fuel-reference" },
] as const;

export default function ReportsPage() {
  return (
    <main className="reports-page">
      <header className="reports-heading">
        <div><p>Intelligence / Reports</p><h1>Reports</h1></div>
      </header>
      <section className="report-catalog" aria-label="Report catalog">
        {reports.map(({ title, description, to }) => (
          <article className="report-card is-active" key={title}>
            <div className="report-card-icon"><BarChart3 /></div>
            <div><h2>{title}</h2><p>{description}</p></div>
            <Link to={to}>Open report</Link>
          </article>
        ))}
      </section>
    </main>
  );
}
