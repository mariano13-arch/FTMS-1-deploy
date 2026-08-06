import { FormEvent, useEffect, useRef, useState } from "react";
import { Redirect, useHistory, useLocation } from "react-router-dom";
import { useAuth } from "../AuthContext";
import { safeInternalPath } from "../services/navigation";

export default function LoginPage() {
  const { user, signIn } = useAuth(); const history = useHistory(); const location = useLocation();
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const mounted = useRef(false); const inFlight = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  if (user) return <Redirect to="/transport-requests" />;
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); if (inFlight.current) return; inFlight.current = true; setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    try { await signIn(String(data.get("username")), String(data.get("password"))); history.replace(safeInternalPath((location.state as { from?: string } | null)?.from)); }
    catch { if (mounted.current) setError("Unable to sign in with those credentials."); }
    finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  };
  return <main className="login-page"><section className="auth-card"><div className="login-brand"><span className="brand__mark">FT<br />MS</span><div><strong>Fleet & Transport</strong><small>Management System</small></div></div><p className="eyebrow">Secure staff access</p><h1>Sign in to FTMS</h1>
    <form onSubmit={submit}><label>Username<input name="username" required autoComplete="username" /></label><label>Password<input name="password" type="password" required autoComplete="current-password" /></label>{error && <p className="message message--error" role="alert">{error}</p>}<button disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button></form>
  </section></main>;
}
