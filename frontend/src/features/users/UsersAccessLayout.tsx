import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import "./UsersAccessLayout.css";

export default function UsersAccessLayout({ children }: { children: ReactNode }) {
  return <main className="users-access-layout">
    <div className="users-access-breadcrumb">Administration / Users &amp; Access</div>
    <header className="users-access-header">
      <h1>Users Roles &amp; Audit Logs</h1>
      <p>Manage staff accounts, access roles, and administrative activity.</p>
    </header>
    <nav className="users-access-tabs" aria-label="Users Roles and Audit Logs">
      <NavLink to="/users" exact activeClassName="active">Staff Users</NavLink>
      <NavLink to="/users/roles-permissions" exact activeClassName="active">Roles &amp; Permissions</NavLink>
      <NavLink to="/users/audit-logs" exact activeClassName="active">Audit Logs</NavLink>
    </nav>
    <div className="users-access-content">{children}</div>
  </main>;
}
