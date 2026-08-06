import { Redirect, useLocation } from "react-router-dom";
import { useAuth } from "../AuthContext";

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth(); const location = useLocation();
  if (loading) return <main className="session-loading">Restoring session…</main>;
  return user ? <>{children}</> : <Redirect to={{ pathname: "/login", state: { from: location.pathname } }} />;
}
