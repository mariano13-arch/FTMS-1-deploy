import { FormEvent, useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { ApiError } from "../../services/api";
import {
  confirmTwoFactor,
  disableTwoFactor,
  startTwoFactorSetup,
  twoFactorStatus,
  type TwoFactorSetup,
  type TwoFactorStatus,
} from "../../services/auth";
import SettingsLayout, { SettingsStatus } from "./SettingsLayout";
import "./SettingsPage.css";

const PlannedRow = ({ title, children }: { title: string; children: string }) => <article className="settings-row"><span><strong>{title}</strong><small>{children}</small></span><SettingsStatus value="Planned" /></article>;

export function SecuritySettingsPage() {
  const [status, setStatus] = useState<TwoFactorStatus | null>(null);
  const [setup, setSetup] = useState<TwoFactorSetup | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [code, setCode] = useState("");
  const [disablePassword, setDisablePassword] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const [disableMethod, setDisableMethod] = useState<"totp" | "recovery">("totp");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { twoFactorStatus().then(setStatus).catch(() => setError("Security status is unavailable.")); }, []);
  const beginSetup = async () => {
    setBusy(true); setError(""); setRecoveryCodes(null);
    try { setSetup(await startTwoFactorSetup()); } catch { setError("Unable to start authenticator setup."); }
    finally { setBusy(false); }
  };
  const confirm = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = await confirmTwoFactor(code);
      setRecoveryCodes(result.recovery_codes); setSetup(null); setCode("");
      setStatus(await twoFactorStatus());
    } catch { setError("Unable to verify the authenticator code."); }
    finally { setBusy(false); }
  };
  const disable = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await disableTwoFactor(disablePassword, disableMethod, disableCode);
      setDisablePassword(""); setDisableCode(""); setRecoveryCodes(null); setSetup(null);
      setStatus(await twoFactorStatus());
    } catch (failure) {
      setError(failure instanceof ApiError ? "Unable to disable two-factor authentication." : "Unable to disable two-factor authentication.");
    } finally { setBusy(false); }
  };
  return <SettingsLayout><section className="settings-panel"><header><div><h2>Security</h2><p>Staff account and session security controls.</p></div></header><div className="settings-rows">
    <article className="settings-row settings-row--expanded"><span><strong>Two-Factor Authentication</strong><small>Authenticator-app verification protects staff sign-in.</small></span><SettingsStatus value={status?.enabled ? "Configured" : "Disabled"} />
      {error && <div className="alert alert-danger small mt-2 mb-0" role="alert">{error}</div>}
      {!status && !error && <small>Loading security status…</small>}
      {status && !status.enabled && !setup && <button type="button" className="btn btn-sm btn-outline-primary mt-2" onClick={beginSetup} disabled={busy}>Set up authenticator</button>}
      {setup && <div className="settings-two-factor-setup mt-3"><div className="bg-white p-2 d-inline-block border rounded"><QRCodeSVG value={setup.provisioning_uri} size={156} /></div>
        <p className="small mt-2 mb-1">Scan this QR code with your authenticator app, or enter this manual key:</p><code className="d-block small text-break">{setup.manual_setup_key}</code>
        <form className="d-flex flex-wrap gap-2 mt-2" onSubmit={confirm}><input aria-label="Authenticator code" className="form-control form-control-sm" style={{ maxWidth: "13rem" }} value={code} onChange={(event) => setCode(event.target.value)} inputMode="numeric" autoComplete="one-time-code" placeholder="6-digit code" required /><button className="btn btn-sm btn-primary" disabled={busy}>Confirm setup</button></form>
      </div>}
      {status?.enabled && <div className="small mt-2">Enabled{status.enabled_at ? ` on ${new Date(status.enabled_at).toLocaleDateString()}` : ""}. Recovery codes remaining: {status.recovery_codes_remaining}.</div>}
      {recoveryCodes && <div className="alert alert-warning small mt-3 mb-0"><strong>Store these recovery codes securely now.</strong><br />They will not be shown again.<div className="mt-2 font-monospace">{recoveryCodes.join("\n")}</div><button type="button" className="btn btn-sm btn-outline-secondary mt-2" onClick={() => navigator.clipboard?.writeText(recoveryCodes.join("\n"))}>Copy all</button></div>}
      {status?.enabled && <form className="d-flex flex-wrap gap-2 align-items-end mt-3" onSubmit={disable}><label className="small">Current password<input aria-label="Current password" type="password" className="form-control form-control-sm" value={disablePassword} onChange={(event) => setDisablePassword(event.target.value)} required /></label><label className="small">Second factor<input aria-label="Disable two-factor code" className="form-control form-control-sm" value={disableCode} onChange={(event) => setDisableCode(event.target.value)} required /></label><select aria-label="Second factor method" className="form-select form-select-sm" style={{ maxWidth: "10rem" }} value={disableMethod} onChange={(event) => setDisableMethod(event.target.value as "totp" | "recovery")}><option value="totp">Authenticator</option><option value="recovery">Recovery code</option></select><button className="btn btn-sm btn-outline-danger" disabled={busy}>Disable 2FA</button></form>}
    </article>
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
