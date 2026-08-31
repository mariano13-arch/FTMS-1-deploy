import { useEffect, useMemo, useRef, useState } from "react";
import { RotateCcw, Save, ShieldAlert } from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";
import { useConfirmModal } from "../../hooks/useConfirmModal";
import { ApiError } from "../../services/api";
import type { ManagedRole } from "../users/api";
import UsersAccessLayout from "../users/UsersAccessLayout";
import { getRolePermissions, replaceRolePermissions, type PermissionMatrix } from "./permissionsApi";
import "./RolesPermissionsPage.css";

const roleLabels: Record<ManagedRole, string> = {
  FLEET_MANAGER: "Fleet Manager",
  DISPATCHER: "Dispatcher",
};
const moduleLabels: Record<string, string> = {
  TRANSPORT_REQUESTS: "Transport Requests",
  DISPATCH_BOARD: "Dispatch Board",
  LIVE_MAP: "Live Map",
  DRIVERS: "Drivers",
  VEHICLES: "Vehicles",
  FUEL_ANALYTICS: "Fleet Fuel Analytics",
  MAINTENANCE: "Maintenance & Predictions",
  SYSTEM_SETTINGS: "System Rules & Settings",
  USERS_ACCESS: "Users & Access",
};

const keyOf = (module: string, action: string) => `${module}:${action}`;
const labelOf = (identifier: string) => identifier.toLowerCase().split("_").map((word) => word[0].toUpperCase() + word.slice(1)).join(" ");
const grantsFor = (matrix: PermissionMatrix, role: ManagedRole) => new Set(
  Object.entries(matrix.roles[role] ?? {}).flatMap(([module, actions]) => actions.map((action) => keyOf(module, action))),
);
const sameSet = (left: Set<string>, right: Set<string>) => left.size === right.size && [...left].every((item) => right.has(item));

function messageFor(reason: unknown) {
  if (reason instanceof ApiError && reason.body && typeof reason.body === "object" && "detail" in reason.body && typeof reason.body.detail === "string") return reason.body.detail;
  return "Permission settings could not be saved. Please try again.";
}

function MasterCheckbox({ checked, partial, onChange, label }: { checked: boolean; partial: boolean; onChange: () => void; label: string }) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { if (ref.current) ref.current.indeterminate = partial; }, [partial]);
  return <label className="permissions-master"><input ref={ref} type="checkbox" checked={checked} onChange={onChange} aria-label={label} /><span>Master</span></label>;
}

function MatrixManager() {
  const [matrix, setMatrix] = useState<PermissionMatrix | null>(null);
  const [role, setRole] = useState<ManagedRole>("FLEET_MANAGER");
  const [draft, setDraft] = useState<Set<string>>(new Set());
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const { confirm, ConfirmModalComponent } = useConfirmModal();

  useEffect(() => {
    const controller = new AbortController();
    getRolePermissions(controller.signal).then((result) => {
      setMatrix(result);
      setDraft(grantsFor(result, "FLEET_MANAGER"));
      setState("ready");
    }).catch((reason) => {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) setState("error");
    });
    return () => controller.abort();
  }, []);

  const serverGrants = useMemo(() => matrix ? grantsFor(matrix, role) : new Set<string>(), [matrix, role]);
  const dirty = !sameSet(draft, serverGrants);

  const toggle = (module: string, action: string) => setDraft((current) => {
    const next = new Set(current);
    const key = keyOf(module, action);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  const toggleModule = (module: string, actions: string[]) => setDraft((current) => {
    const next = new Set(current);
    const keys = actions.map((action) => keyOf(module, action));
    const allSelected = keys.every((key) => next.has(key));
    keys.forEach((key) => allSelected ? next.delete(key) : next.add(key));
    return next;
  });

  const switchRole = async (nextRole: ManagedRole) => {
    if (nextRole === role || !matrix) return;
    if (dirty && !await confirm({ title: "Discard unsaved changes?", message: "Switching roles will discard the permission changes you have not saved.", variant: "warning", confirmText: "Discard & Switch" })) return;
    setRole(nextRole);
    setDraft(grantsFor(matrix, nextRole));
    setNotice(null);
  };

  const save = async () => {
    if (!matrix || !dirty) return;
    const accepted = await confirm({ title: `Save permission changes for ${roleLabels[role]}?`, message: "These policies control future module access as permission enforcement is applied separately.", variant: "primary", confirmText: "Save Changes" });
    if (!accepted) return;
    setSaving(true);
    setNotice(null);
    const permissions = Object.entries(matrix.definitions).flatMap(([module, actions]) => actions.filter((action) => draft.has(keyOf(module, action))).map((action) => ({ module, action })));
    try {
      const updated = await replaceRolePermissions(role, permissions);
      setMatrix(updated);
      setDraft(grantsFor(updated, role));
      setNotice({ kind: "success", text: `${roleLabels[role]} permissions saved.` });
    } catch (reason) {
      setNotice({ kind: "error", text: messageFor(reason) });
    } finally {
      setSaving(false);
    }
  };

  if (state === "loading") return <div className="permissions-page"><div className="permissions-state" role="status">Loading roles and permissions…</div></div>;
  if (state === "error" || !matrix) return <div className="permissions-page"><div className="permissions-state permissions-state--error" role="alert">Roles and permissions could not be loaded.</div></div>;

  return <div className="permissions-page">
    <header><div><h2>Roles &amp; Permissions</h2><p>Configure managed-role permission policies using supported FTMS actions.</p></div></header>
      <section className="permissions-workspace">
        <div className="permissions-toolbar"><label>Role / User Type<select value={role} onChange={(event) => void switchRole(event.target.value as ManagedRole)}><option value="FLEET_MANAGER">Fleet Manager</option><option value="DISPATCHER">Dispatcher</option></select></label><p>Super Admin has system-level access and is not managed through this matrix.</p></div>
        <div className="permissions-info">Permission policies are configured here. Module-by-module enforcement is being applied separately.</div>
        {notice && <div className={`permissions-notice permissions-notice--${notice.kind}`} role={notice.kind === "error" ? "alert" : "status"}>{notice.text}</div>}
        <div className="permissions-matrix" role="table" aria-label={`${roleLabels[role]} permission matrix`}>
          <div className="permissions-matrix-head" role="row"><span role="columnheader">Module</span><span role="columnheader">Valid actions</span><span role="columnheader">Master</span></div>
          {Object.entries(matrix.definitions).map(([module, actions]) => {
            const selectedCount = actions.filter((action) => draft.has(keyOf(module, action))).length;
            return <div className="permissions-row" role="row" key={module}>
              <div className="permissions-module" role="rowheader"><strong>{moduleLabels[module] ?? labelOf(module)}</strong><small>{module}</small></div>
              <div className="permissions-actions" role="cell">{actions.map((action) => <label key={action}><input type="checkbox" checked={draft.has(keyOf(module, action))} onChange={() => toggle(module, action)} aria-label={`${moduleLabels[module] ?? labelOf(module)}: ${labelOf(action)}`} /><span>{labelOf(action)}</span></label>)}</div>
              <div role="cell"><MasterCheckbox checked={selectedCount === actions.length} partial={selectedCount > 0 && selectedCount < actions.length} onChange={() => toggleModule(module, actions)} label={`Master permissions for ${moduleLabels[module] ?? labelOf(module)}`} /></div>
            </div>;
          })}
        </div>
        <footer className="permissions-savebar"><span className={dirty ? "permissions-dirty" : ""}>{dirty ? "Unsaved changes" : "All changes saved"}</span><div><button type="button" onClick={() => setDraft(serverGrants)} disabled={!dirty || saving}><RotateCcw size={14} /> Reset</button><button type="button" className="permissions-save" onClick={() => void save()} disabled={!dirty || saving}><Save size={14} /> {saving ? "Saving…" : "Save Changes"}</button></div></footer>
      </section>
    {ConfirmModalComponent}
  </div>;
}

export default function RolesPermissionsPage() {
  const { user } = useAuth();
  if (user?.role !== "SUPER_ADMIN") return <main className="permissions-page permissions-denied"><ShieldAlert size={28} /><h1>Access denied</h1><p>Only a Super Admin can manage role permissions.</p></main>;
  return <UsersAccessLayout><MatrixManager /></UsersAccessLayout>;
}
