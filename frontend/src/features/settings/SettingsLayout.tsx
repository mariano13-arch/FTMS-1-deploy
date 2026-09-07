import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

export type SettingsStatusValue = "Available" | "Configured" | "Disabled" | "Blocked" | "Planned" | "Not configured" | "Status unavailable";
export function SettingsStatus({ value }: { value: SettingsStatusValue }) {
  return <span className={`settings-status settings-status--${value.toLowerCase().replaceAll(" ", "-")}`}>{value}</span>;
}

export default function SettingsLayout({ children }: { children: ReactNode }) {
  return <main className="settings-page">
    <div className="settings-breadcrumb">Administration / System Settings</div>
    <header className="settings-header"><h1>System Rules &amp; Settings</h1><p>Security, operational rules, integrations, and technical model status.</p></header>
    <nav className="settings-tabs" aria-label="System Rules and Settings">
      <NavLink exact to="/settings" activeClassName="active">Overview</NavLink>
      <NavLink exact to="/settings/security" activeClassName="active">Security</NavLink>
      <NavLink exact to="/settings/operational-rules" activeClassName="active">Operational Rules</NavLink>
      <NavLink exact to="/settings/integrations" activeClassName="active">Integrations</NavLink>
      <NavLink exact to="/settings/ai-models" activeClassName="active">AI / ML Models</NavLink>
    </nav>
    <div className="settings-content">{children}</div>
  </main>;
}
