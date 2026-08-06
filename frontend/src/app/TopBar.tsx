import { useEffect, useRef, useState } from "react";
import { useAuth } from "../AuthContext";

export default function TopBar({ sidebarOpen, toggleSidebar }: { sidebarOpen: boolean; toggleSidebar: () => void }) {
  const { user, signOut } = useAuth(); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const mounted = useRef(false); const inFlight = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const submit = async () => {
    if (inFlight.current) return; inFlight.current = true; setBusy(true); setError("");
    try { await signOut(); } catch { if (mounted.current) setError("Unable to sign out. Please try again."); }
    finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  };
  return <><header className="topbar">
    <button className="sidebar-toggle" onClick={toggleSidebar} aria-label={sidebarOpen ? "Close navigation" : "Open navigation"} aria-expanded={sidebarOpen} aria-controls="primary-sidebar"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" /></svg></button>
    <strong className="hotel-brand">◉ Oxford Suites Makati</strong>
    <div className="user-menu"><span className="avatar">{user?.display_name.slice(0, 2).toUpperCase()}</span><span><strong>{user?.display_name}</strong><small>{user?.role.replaceAll("_", " ")}</small></span><button onClick={() => void submit()} disabled={busy}>{busy ? "Signing out…" : "Sign out"}</button></div>
  </header>{error && <p role="alert" className="top-error">{error}</p>}</>;
}
