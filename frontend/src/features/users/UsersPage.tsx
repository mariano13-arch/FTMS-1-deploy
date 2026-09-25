import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { MoreVertical, Plus, RefreshCw, Search, ShieldAlert } from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";
import { ApiError } from "../../services/api";
import { useConfirmModal } from "../../hooks/useConfirmModal";
import {
  createStaff,
  listStaff,
  resendStaffInvitation,
  updateStaffRole,
  updateStaffStatus,
  type CreateStaffInput,
  type ManagedRole,
  type StaffRecord,
} from "./api";
import UsersAccessLayout from "./UsersAccessLayout";
import "./UsersPage.css";

const roleLabels: Record<ManagedRole, string> = {
  FLEET_MANAGER: "Fleet Manager",
  DISPATCHER: "Dispatcher",
  FLEET_STAFF: "Fleet Staff",
};

const emptyForm: CreateStaffInput = {
  first_name: "",
  last_name: "",
  username: "",
  email: "",
  role: "FLEET_MANAGER",
};

function errorMessage(reason: unknown) {
  if (reason instanceof ApiError && reason.body && typeof reason.body === "object") {
    const body = reason.body as Record<string, unknown>;
    if (typeof body.detail === "string") return body.detail;
    const messages = Object.values(body).flatMap((value) =>
      Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [],
    );
    if (messages.length) return messages.join(" ");
  }
  return "The request could not be completed. Please try again.";
}

function StaffUsersManager() {
  const [staff, setStaff] = useState<StaffRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [query, setQuery] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<CreateStaffInput>(emptyForm);
  const [openMenuId, setOpenMenuId] = useState<number | null>(null);
  const [detailsUser, setDetailsUser] = useState<StaffRecord | null>(null);
  const [roleUser, setRoleUser] = useState<StaffRecord | null>(null);
  const [roleDraft, setRoleDraft] = useState<ManagedRole>("FLEET_MANAGER");
  const [busyKey, setBusyKey] = useState("");
  const [notice, setNotice] = useState<{ kind: "success" | "warning" | "error"; text: string } | null>(null);
  const { confirm, ConfirmModalComponent } = useConfirmModal();

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setLoadError("");
    try {
      const results = await listStaff(signal);
      setStaff(results);
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) {
        setLoadError(errorMessage(reason));
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    listStaff(controller.signal)
      .then(setStaff)
      .catch((reason) => {
        if (!(reason instanceof DOMException && reason.name === "AbortError")) {
          setLoadError(errorMessage(reason));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (openMenuId === null) return;
    const closeOutside = (event: MouseEvent) => {
      if (!(event.target as Element).closest("[data-user-menu]")) setOpenMenuId(null);
    };
    const closeWithEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenMenuId(null);
    };
    document.addEventListener("mousedown", closeOutside);
    document.addEventListener("keydown", closeWithEscape);
    return () => {
      document.removeEventListener("mousedown", closeOutside);
      document.removeEventListener("keydown", closeWithEscape);
    };
  }, [openMenuId]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 10_000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return staff;
    return staff.filter((item) =>
      [item.first_name, item.last_name, item.username, item.email, roleLabels[item.role]]
        .join(" ")
        .toLowerCase()
        .includes(needle),
    );
  }, [query, staff]);

  const replaceRecord = (record: StaffRecord) => {
    setStaff((current) => current.map((item) => (item.id === record.id ? record : item)));
    setDetailsUser((current) => current?.id === record.id ? record : current);
  };

  const submitCreate = async (event: FormEvent) => {
    event.preventDefault();
    setBusyKey("create");
    setNotice(null);
    try {
      const created = await createStaff(form);
      await load();
      setForm(emptyForm);
      setShowCreate(false);
      setNotice(created.invitation_delivery === "SENT"
        ? { kind: "success", text: "Account created and setup invitation sent." }
        : { kind: "warning", text: "Account created, but invitation delivery failed. You can resend the invitation." });
    } catch (reason) {
      setNotice({ kind: "error", text: errorMessage(reason) });
    } finally {
      setBusyKey("");
    }
  };

  const saveRole = async (item: StaffRecord) => {
    setBusyKey(`role-${item.id}`);
    setNotice(null);
    try {
      replaceRecord(await updateStaffRole(item.id, roleDraft));
      setRoleUser(null);
      setNotice({ kind: "success", text: `${item.username}'s role was updated.` });
    } catch (reason) {
      setNotice({ kind: "error", text: errorMessage(reason) });
    } finally {
      setBusyKey("");
    }
  };

  const changeStatus = async (item: StaffRecord) => {
    if (item.is_active) {
      const accepted = await confirm({
        title: `Deactivate ${item.username}?`,
        message: "Deactivated users cannot sign in. Already-issued sessions are not guaranteed to end immediately.",
        variant: "danger",
        confirmText: "Deactivate",
      });
      if (!accepted) return;
    }
    setBusyKey(`status-${item.id}`);
    setNotice(null);
    try {
      replaceRecord(await updateStaffStatus(item.id, !item.is_active));
      setNotice({ kind: "success", text: `${item.username} was ${item.is_active ? "deactivated" : "activated"}.` });
    } catch (reason) {
      setNotice({ kind: "error", text: errorMessage(reason) });
    } finally {
      setBusyKey("");
    }
  };

  const resend = async (item: StaffRecord) => {
    setBusyKey(`resend-${item.id}`);
    setNotice(null);
    try {
      await resendStaffInvitation(item.id);
      setNotice({ kind: "success", text: "Setup invitation sent." });
    } catch (reason) {
      setNotice({ kind: "error", text: reason instanceof ApiError && reason.status === 503
        ? "Invitation could not be delivered. Try again later."
        : errorMessage(reason) });
    } finally {
      setBusyKey("");
    }
  };

  const active = staff.filter((item) => item.is_active).length;
  const pending = staff.filter((item) => item.setup_status === "pending").length;

  return <div className="users-page">
    <header className="users-header">
      <div><h2>Staff Users</h2></div>
      <button className="users-button users-button--primary" type="button" onClick={() => setShowCreate(true)}><Plus size={15} /> Add User</button>
    </header>

    <section className="users-summary" aria-label="Staff account summary">
      <article><span>Total Staff</span><strong>{staff.length}</strong></article>
      <article><span>Active</span><strong>{active}</strong></article>
      <article><span>Inactive</span><strong>{staff.length - active}</strong></article>
      <article><span>Pending Setup</span><strong>{pending}</strong></article>
    </section>

    {notice && <div className={`users-notice users-notice--${notice.kind}`} role={notice.kind === "error" ? "alert" : "status"}>{notice.text}</div>}

    <section className="users-panel" aria-labelledby="staff-table-title">
      <div className="users-toolbar">
        <div><span className="users-kicker">Staff directory</span><h2 id="staff-table-title">Managed accounts</h2></div>
        <label className="users-search"><Search size={15} /><input aria-label="Search staff" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name, username, email, or role" /></label>
      </div>

      {loading ? <div className="users-state" role="status">Loading staff users…</div>
        : loadError ? <div className="users-state users-state--error" role="alert"><p>{loadError}</p><button className="users-button" onClick={() => void load()}><RefreshCw size={14} /> Retry</button></div>
        : filtered.length === 0 ? <div className="users-state">{staff.length ? "No staff match your search." : "No managed staff accounts found."}</div>
        : <div className="users-table-wrap"><table className="users-table">
          <thead><tr><th>User</th><th>Username</th><th>Role</th><th>Status</th><th>Setup</th><th>Last Login</th><th>Actions</th></tr></thead>
          <tbody>{filtered.map((item) => {
            const displayName = [item.first_name, item.last_name].filter(Boolean).join(" ") || item.username;
            return <tr key={item.id}>
              <td><strong>{displayName}</strong><small>{item.email}</small></td>
              <td>{item.username}</td>
              <td><span className="users-role-label">{roleLabels[item.role]}</span></td>
              <td><span className={`users-badge users-badge--${item.is_active ? "active" : "inactive"}`}>{item.is_active ? "Active" : "Inactive"}</span></td>
              <td><span className={`users-badge users-badge--${item.setup_status}`}>{item.setup_status === "pending" ? "Pending Setup" : "Ready"}</span></td>
              <td>{item.last_login ? new Date(item.last_login).toLocaleString() : "Never"}</td>
              <td><div className="users-action-menu" data-user-menu>
                <button type="button" className="users-action-trigger" aria-label={`Actions for ${item.username}`} aria-haspopup="menu" aria-expanded={openMenuId === item.id} onClick={() => setOpenMenuId((current) => current === item.id ? null : item.id)}><MoreVertical size={16} /></button>
                {openMenuId === item.id && <div className="users-action-popover" role="menu">
                  <button role="menuitem" onClick={() => { setDetailsUser(item); setOpenMenuId(null); }}>View Details</button>
                  <button role="menuitem" onClick={() => { setRoleUser(item); setRoleDraft(item.role); setOpenMenuId(null); }}>Change Role</button>
                  {item.setup_status === "pending" && item.is_active && <button role="menuitem" disabled={Boolean(busyKey)} onClick={() => { setOpenMenuId(null); void resend(item); }}>Resend Invitation</button>}
                  <button role="menuitem" className={item.is_active ? "users-danger" : ""} disabled={Boolean(busyKey)} onClick={() => { setOpenMenuId(null); void changeStatus(item); }}>{item.is_active ? "Deactivate" : "Activate"}</button>
                </div>}
              </div></td>
            </tr>;
          })}</tbody>
        </table></div>}
    </section>

    {showCreate && <div className="users-dialog-backdrop" role="presentation"><section className="users-dialog" role="dialog" aria-modal="true" aria-labelledby="add-user-title">
      <header><div><span className="users-kicker">Users &amp; Access</span><h2 id="add-user-title">Add Staff User</h2></div><button type="button" aria-label="Close add user form" onClick={() => setShowCreate(false)}>×</button></header>
      <form onSubmit={submitCreate}>
        <div className="users-form-grid"><label>First Name<input required value={form.first_name} onChange={(event) => setForm({ ...form, first_name: event.target.value })} /></label><label>Last Name<input required value={form.last_name} onChange={(event) => setForm({ ...form, last_name: event.target.value })} /></label></div>
        <label>Username<input required autoComplete="username" value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} /></label>
        <label>Email<input required type="email" autoComplete="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></label>
        <label>Role<select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value as ManagedRole })}><option value="FLEET_MANAGER">Fleet Manager</option><option value="DISPATCHER">Dispatcher</option><option value="FLEET_STAFF">Fleet Staff</option></select></label>
        <p className="users-form-note">The user will choose their password from the emailed one-time setup invitation.</p>
        <footer><button type="button" className="users-button" onClick={() => setShowCreate(false)}>Cancel</button><button className="users-button users-button--primary" disabled={busyKey === "create"}>{busyKey === "create" ? "Creating…" : "Create & Send Invitation"}</button></footer>
      </form>
    </section></div>}
    {detailsUser && <div className="users-dialog-backdrop" role="presentation"><section className="users-dialog users-details-dialog" role="dialog" aria-modal="true" aria-labelledby="user-details-title">
      <header><div><span className="users-kicker">Managed staff</span><h2 id="user-details-title">User Details</h2></div><button type="button" aria-label="Close user details" onClick={() => setDetailsUser(null)}>×</button></header>
      <section><h3>Account</h3><dl>
        <div><dt>Full Name</dt><dd>{[detailsUser.first_name, detailsUser.last_name].filter(Boolean).join(" ") || detailsUser.username}</dd></div>
        <div><dt>Username</dt><dd>{detailsUser.username}</dd></div><div><dt>Email</dt><dd>{detailsUser.email}</dd></div>
        <div><dt>Role</dt><dd>{roleLabels[detailsUser.role]}</dd></div><div><dt>Status</dt><dd>{detailsUser.is_active ? "Active" : "Inactive"}</dd></div>
        <div><dt>Setup Status</dt><dd>{detailsUser.setup_status === "pending" ? "Pending Setup" : "Ready"}</dd></div>
      </dl></section>
      <section><h3>Access / Activity</h3><dl><div><dt>Last Login</dt><dd>{detailsUser.last_login ? new Date(detailsUser.last_login).toLocaleString() : "Never"}</dd></div><div><dt>Date Joined</dt><dd>{new Date(detailsUser.date_joined).toLocaleString()}</dd></div></dl></section>
      <section><h3>Security</h3><div className="users-security-note"><strong>{detailsUser.setup_status === "complete" ? "Password configured" : "Password not set yet"}</strong><p>{detailsUser.setup_status === "complete" ? "Passwords are securely stored and cannot be viewed." : "The user must complete the secure account setup invitation."}</p><p>Password reset is not yet available from Staff Management.</p></div></section>
      <footer><button type="button" className="users-button" onClick={() => setDetailsUser(null)}>Close</button></footer>
    </section></div>}
    {roleUser && <div className="users-dialog-backdrop" role="presentation"><section className="users-dialog users-role-dialog" role="dialog" aria-modal="true" aria-labelledby="change-role-title">
      <header><div><span className="users-kicker">{roleUser.username}</span><h2 id="change-role-title">Change Role</h2></div><button type="button" aria-label="Close role editor" onClick={() => setRoleUser(null)}>×</button></header>
      <label>Role<select aria-label={`New role for ${roleUser.username}`} value={roleDraft} onChange={(event) => setRoleDraft(event.target.value as ManagedRole)}><option value="FLEET_MANAGER">Fleet Manager</option><option value="DISPATCHER">Dispatcher</option><option value="FLEET_STAFF">Fleet Staff</option></select></label>
      <footer><button type="button" className="users-button" onClick={() => setRoleUser(null)}>Cancel</button><button type="button" className="users-button users-button--primary" disabled={roleDraft === roleUser.role || Boolean(busyKey)} onClick={() => void saveRole(roleUser)}>{busyKey === `role-${roleUser.id}` ? "Saving…" : "Save Role"}</button></footer>
    </section></div>}
    {ConfirmModalComponent}
  </div>;
}

export default function UsersPage() {
  const { user } = useAuth();
  if (user?.role !== "FLEET_ADMIN") {
    return <main className="users-page users-access-denied"><ShieldAlert size={28} /><h1>Access denied</h1><p>Only a Fleet Admin can manage staff accounts.</p></main>;
  }
  return <UsersAccessLayout><StaffUsersManager /></UsersAccessLayout>;
}
