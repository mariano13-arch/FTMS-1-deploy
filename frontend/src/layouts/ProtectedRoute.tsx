import { Redirect, useLocation } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import LoadingIndicator from "../components/common/LoadingIndicator";

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth(); const location = useLocation();
  if (loading) return <LoadingIndicator variant="fullpage" message="Restoring session…" />;
  return user ? <>{children}</> : <Redirect to={{ pathname: "/login", state: { from: location.pathname } }} />;
}
