import { ShieldAlert } from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";
import UsersAccessLayout from "./UsersAccessLayout";

export default function AuditLogsPage() {
  const { user } = useAuth();
  if (user?.role !== "SUPER_ADMIN") return <main className="users-page users-access-denied"><ShieldAlert size={28} /><h1>Access denied</h1><p>Only a Super Admin can access administrative activity.</p></main>;
  return <UsersAccessLayout><section className="users-audit-placeholder">
    <h2>Audit Logs</h2>
    <p>Centralized administrative audit logging is not available yet.</p>
  </section></UsersAccessLayout>;
}
