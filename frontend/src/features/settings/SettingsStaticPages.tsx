import SettingsLayout, { SettingsStatus } from "./SettingsLayout";
import "./SettingsPage.css";

const PlannedRow = ({ title, children }: { title: string; children: string }) => <article className="settings-row"><span><strong>{title}</strong><small>{children}</small></span><SettingsStatus value="Planned" /></article>;

export function SecuritySettingsPage() {
  return <SettingsLayout><section className="settings-panel"><header><div><h2>Security</h2><p>Staff account and session security controls.</p></div></header><div className="settings-rows">
    <PlannedRow title="Two-Factor Authentication">Additional sign-in verification using an authenticator app.</PlannedRow>
    <PlannedRow title="Password">Secure password-management controls for configured staff accounts.</PlannedRow>
    <PlannedRow title="Active Sessions">Session visibility and revocation are not yet available.</PlannedRow>
  </div></section></SettingsLayout>;
}

export function OperationalRulesSettingsPage() {
  return <SettingsLayout><section className="settings-panel"><header><div><h2>Operational Rules</h2><p>Configuration controls are not available yet.</p></div></header><div className="settings-rows">
    <PlannedRow title="Dispatch Rules">Human dispatch confirmation remains mandatory; no automatic dispatch control is available.</PlannedRow>
    <PlannedRow title="Routing Rules">Routing configuration controls are not available yet.</PlannedRow>
    <PlannedRow title="Geofence Rules">Geofence configuration controls are not available in System Settings yet.</PlannedRow>
  </div></section></SettingsLayout>;
}

const integrations = [
  ["Hotel Management System", "Trusted service-to-service authentication is not configured."],
  ["Restaurant Management System", "Trusted service-to-service authentication is not configured."],
  ["TomTom Services", "A safe frontend configuration-status endpoint is not available."],
  ["Email / Staff Invitations", "A safe frontend configuration-status endpoint is not available."],
  ["MQTT / Telematics", "A safe frontend broker-status endpoint is not available."],
] as const;
export function IntegrationsSettingsPage() {
  return <SettingsLayout><section className="settings-panel"><header><div><h2>Integrations</h2><p>Safe connection-status visibility for FTMS subsystems.</p></div></header><div className="settings-rows">{integrations.map(([name, note]) => <article className="settings-row" key={name}><span><strong>{name}</strong><small>{note}</small></span><SettingsStatus value={name.includes("Management System") ? "Not configured" : "Status unavailable"} /></article>)}</div></section></SettingsLayout>;
}
