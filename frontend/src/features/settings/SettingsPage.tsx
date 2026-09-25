import { Link } from "react-router-dom";
import SettingsLayout, { SettingsStatus } from "./SettingsLayout";
import "./SettingsPage.css";

const categories = [
  { to: "/settings/security", name: "Security", description: "Sign-in protection, passwords, and staff sessions.", status: "Available" as const },
  { to: "/settings/operational-rules", name: "Operational Rules", description: "Dispatch, routing, and geofence rule controls.", status: "Planned" as const },
  { to: "/settings/integrations", name: "Integrations", description: "Subsystem connection and status visibility.", status: "Status unavailable" as const },
  { to: "/settings/ai-models", name: "AI / ML Models", description: "Technical model identity, inputs, semantics, and readiness.", status: "Available" as const },
];

export default function SettingsPage() {
  return <SettingsLayout><section className="settings-panel" aria-labelledby="settings-overview-title">
    <header><div><h2 id="settings-overview-title">Settings Overview</h2></div></header>
    <div className="settings-category-list">{categories.map((item) => <Link to={item.to} key={item.to}>
      <span><strong>{item.name}</strong><small>{item.description}</small></span><SettingsStatus value={item.status} />
    </Link>)}</div>
  </section></SettingsLayout>;
}
