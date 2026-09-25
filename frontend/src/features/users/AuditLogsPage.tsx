import { useEffect, useMemo, useState } from "react";
import { ShieldAlert } from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";
import UsersAccessLayout from "./UsersAccessLayout";
import { listAuditLogs, type AuditEvent, type AuditLogFilters } from "./api";

const actionLabels: Record<string, string> = {
  LOGIN_SUCCESS: "Signed in",
  LOGIN_FAILURE: "Sign-in failed",
  ACCOUNT_LOCKED: "Account temporarily locked",
  ACCOUNT_LOCK_EXPIRED: "Account lock expired",
  LOGOUT: "Signed out",
  SESSION_REVOKED: "Session revoked",
  PASSWORD_CHANGED: "Password changed",
  PASSWORD_RESET_COMPLETED: "Password reset completed",
  MFA_ENABLED: "MFA enabled",
  MFA_DISABLED: "MFA disabled",
  MFA_DISABLE_REJECTED: "MFA disable rejected",
  RECOVERY_CODE_USED: "Recovery code used",
  STAFF_CREATED: "Staff created",
  STAFF_INVITED: "Staff invited",
  STAFF_ROLE_CHANGED: "Staff role changed",
  STAFF_STATUS_CHANGED: "Staff status changed",
  ROLE_PERMISSIONS_REPLACED: "Role permissions updated",
};

const actionOptions = Object.keys(actionLabels);
const outcomeOptions = ["SUCCESS", "FAILURE", "DENIED"];

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function valueText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "None";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function Changes({ changes }: { changes: Record<string, unknown> }) {
  const entries = Object.entries(changes);
  if (!entries.length) return <p>No changed fields recorded.</p>;
  return <dl className="audit-details-list">
    {entries.map(([field, value]) => {
      const pair = value && typeof value === "object" && !Array.isArray(value) ? value as { old?: unknown; new?: unknown } : null;
      return <div key={field}><dt>{field}</dt><dd>{pair && ("old" in pair || "new" in pair) ? `${valueText(pair.old)} -> ${valueText(pair.new)}` : valueText(value)}</dd></div>;
    })}
  </dl>;
}

function Metadata({ metadata }: { metadata: Record<string, unknown> }) {
  const entries = Object.entries(metadata);
  if (!entries.length) return <p>No metadata recorded.</p>;
  return <dl className="audit-details-list">{entries.map(([field, value]) => <div key={field}><dt>{field}</dt><dd>{valueText(value)}</dd></div>)}</dl>;
}

export default function AuditLogsPage() {
  const { user } = useAuth();
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [filters, setFilters] = useState<AuditLogFilters>({});
  const [draft, setDraft] = useState<AuditLogFilters>({});
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [selected, setSelected] = useState<AuditEvent | null>(null);

  const load = useMemo(() => (signal?: AbortSignal) => {
    setState("loading");
    listAuditLogs(filters, signal)
      .then((result) => { setEvents(result.results); setState("ready"); })
      .catch((error) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setState("error");
      });
  }, [filters]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  if (user?.role !== "FLEET_ADMIN") return <main className="users-page users-access-denied"><ShieldAlert size={28} /><h1>Access denied</h1><p>Only a Fleet Admin can access administrative activity.</p></main>;

  return <UsersAccessLayout><section className="users-audit-log">
    <header><h2>Audit Logs</h2></header>
    <div className="audit-filters">
      <label>Date From<input type="datetime-local" value={draft.occurred_after ?? ""} onChange={(event) => setDraft({ ...draft, occurred_after: event.target.value })} /></label>
      <label>Date To<input type="datetime-local" value={draft.occurred_before ?? ""} onChange={(event) => setDraft({ ...draft, occurred_before: event.target.value })} /></label>
      <label>Actor<input value={draft.actor ?? ""} onChange={(event) => setDraft({ ...draft, actor: event.target.value })} placeholder="User ID" /></label>
      <label>Action<select value={draft.action ?? ""} onChange={(event) => setDraft({ ...draft, action: event.target.value })}><option value="">Any</option>{actionOptions.map((action) => <option key={action} value={action}>{actionLabels[action]}</option>)}</select></label>
      <label>Result<select value={draft.outcome ?? ""} onChange={(event) => setDraft({ ...draft, outcome: event.target.value })}><option value="">Any</option>{outcomeOptions.map((outcome) => <option key={outcome} value={outcome}>{outcome}</option>)}</select></label>
      <button type="button" onClick={() => setFilters(draft)}>Apply</button>
      <button type="button" className="secondary" onClick={() => { setDraft({}); setFilters({}); }}>Clear</button>
    </div>
    {state === "loading" && <div className="audit-state" role="status">Loading audit logs...</div>}
    {state === "error" && <div className="audit-state audit-state--error" role="alert">Audit logs could not be loaded.<button type="button" onClick={() => load()}>Retry</button></div>}
    {state === "ready" && <div className="audit-table-wrap"><table className="audit-table">
      <thead><tr><th>Date / Time</th><th>User / Actor</th><th>Action</th><th>Target</th><th>Result</th><th>Details</th></tr></thead>
      <tbody>
        {events.map((event) => <tr key={event.id}>
          <td>{formatDate(event.occurred_at)}</td>
          <td>{event.actor_display || event.actor_type}</td>
          <td>{actionLabels[event.action] ?? event.action}</td>
          <td>{event.target_label || event.target_type || "None"}</td>
          <td><span className={`audit-outcome audit-outcome--${event.outcome.toLowerCase()}`}>{event.outcome}</span></td>
          <td><button type="button" className="link-button" onClick={() => setSelected(event)}>Details</button></td>
        </tr>)}
        {!events.length && <tr><td colSpan={6} className="audit-empty">{Object.keys(filters).length ? "No audit events found for the selected filters." : "No audit events recorded yet."}</td></tr>}
      </tbody>
    </table></div>}
    {selected && <div className="audit-drawer-backdrop" role="presentation" onClick={() => setSelected(null)}>
      <aside className="audit-drawer" role="dialog" aria-label="Audit log details" onClick={(event) => event.stopPropagation()}>
        <header><h3>{actionLabels[selected.action] ?? selected.action}</h3><button type="button" onClick={() => setSelected(null)}>Close</button></header>
        <dl className="audit-details-list">
          <div><dt>Timestamp</dt><dd>{formatDate(selected.occurred_at)}</dd></div>
          <div><dt>Actor</dt><dd>{selected.actor_display}</dd></div>
          <div><dt>Target</dt><dd>{selected.target_label || selected.target_type || "None"}</dd></div>
          <div><dt>Outcome</dt><dd>{selected.outcome}</dd></div>
          <div><dt>Source</dt><dd>{selected.source}</dd></div>
          {selected.ip_address && <div><dt>IP address</dt><dd>{selected.ip_address}</dd></div>}
          {selected.user_agent && <div><dt>User agent</dt><dd>{selected.user_agent}</dd></div>}
        </dl>
        <h4>Changes</h4><Changes changes={selected.changes} />
        <h4>Metadata</h4><Metadata metadata={selected.metadata} />
      </aside>
    </div>}
  </section></UsersAccessLayout>;
}
