import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import {
  Bot,
  ChevronRight,
  Gauge,
  Link2,
  LockKeyhole,
  Settings2,
} from "lucide-react";

export type SettingsStatusValue = "Available" | "Configured" | "Disabled" | "Blocked" | "Planned" | "Not configured" | "Status unavailable";
export function SettingsStatus({ value }: { value: SettingsStatusValue }) {
  return <span className={`settings-status settings-status--${value.toLowerCase().replaceAll(" ", "-")}`}>{value}</span>;
}

export default function SettingsLayout({ children }: { children: ReactNode }) {
  return <main className="settings-page">
    <div className="settings-breadcrumb">Administration / System Settings</div>
    <header className="settings-header">
      <h1>Settings</h1>
      <p>Manage system rules, security, integrations, and model readiness.</p>
    </header>
    <div className="settings-workspace">
      <aside className="settings-sidebar">
        <nav className="settings-tabs" aria-label="System Rules and Settings">
          <div className="settings-nav-group">
            <span className="settings-nav-heading">General</span>
            <NavLink exact to="/settings" activeClassName="active">
              <Gauge aria-hidden="true" /><span>Overview</span><ChevronRight className="settings-nav-chevron" aria-hidden="true" />
            </NavLink>
            <NavLink exact to="/settings/security" activeClassName="active">
              <LockKeyhole aria-hidden="true" /><span>Security</span><ChevronRight className="settings-nav-chevron" aria-hidden="true" />
            </NavLink>
          </div>
          <div className="settings-nav-group">
            <span className="settings-nav-heading">System</span>
            <NavLink exact to="/settings/operational-rules" activeClassName="active">
              <Settings2 aria-hidden="true" /><span>Operational Rules</span><ChevronRight className="settings-nav-chevron" aria-hidden="true" />
            </NavLink>
            <NavLink exact to="/settings/integrations" activeClassName="active">
              <Link2 aria-hidden="true" /><span>Integrations</span><ChevronRight className="settings-nav-chevron" aria-hidden="true" />
            </NavLink>
          </div>
          <div className="settings-nav-group">
            <span className="settings-nav-heading">Intelligence</span>
            <NavLink exact to="/settings/ai-models" activeClassName="active">
              <Bot aria-hidden="true" /><span>AI / ML Models</span><ChevronRight className="settings-nav-chevron" aria-hidden="true" />
            </NavLink>
          </div>
        </nav>
      </aside>
      <div className="settings-content">{children}</div>
    </div>
  </main>;
}
