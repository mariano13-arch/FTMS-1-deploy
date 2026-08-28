import { useEffect, useRef, useState } from "react";
import { RefreshCw, HelpCircle, LogOut, User, ShieldCheck } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import oxfordLogo from "../assets/images/oxford-suites-logo.png";

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function TopBar({ sidebarOpen, toggleSidebar }: { sidebarOpen: boolean; toggleSidebar: () => void }) {
  const { user, signOut } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const mounted = useRef(false);
  const inFlight = useRef(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const displayName = user?.display_name?.trim() || user?.username || "User";
  const initials = user ? getInitials(displayName) : "?";

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleLogout = async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    setIsDropdownOpen(false);
    try { await signOut(); }
    catch { if (mounted.current) setError("Unable to sign out. Please try again."); }
    finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  };

  return (
    <>
      <header className="app-navbar d-flex align-items-center justify-content-between px-3">
        <div className="d-flex align-items-center" style={{ minWidth: "120px" }}>
          <span className="text-muted extra-small">
            {new Date().toLocaleDateString(undefined, {
              weekday: "short",
              month: "short",
              day: "numeric",
              year: "numeric",
            })}
          </span>
        </div>

        <div className="nav-center-pill d-flex align-items-center justify-content-center gap-2">
          <img src={oxfordLogo} alt="Oxford Suites Makati" className="nav-center-logo" />
          <span className="fw-semibold text-dark extra-small">
            Oxford Suites Makati
          </span>
        </div>

        <div className="d-flex align-items-center gap-2">
          <button
            className="sidebar-toggle"
            onClick={toggleSidebar}
            aria-label={sidebarOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={sidebarOpen}
            aria-controls="primary-sidebar"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 7h16M4 12h16M4 17h16" />
            </svg>
          </button>

          <button type="button" className="nav-icon-btn" aria-label="Refresh">
            <RefreshCw size={14} />
          </button>

          <button type="button" className="nav-icon-btn" aria-label="Help">
            <HelpCircle size={14} />
          </button>

          <div className="position-relative" ref={dropdownRef}>
            <button
              type="button"
              className="nav-avatar-btn border-0 ms-1"
              aria-label="User profile"
              onClick={() => setIsDropdownOpen((prev) => !prev)}
            >
              {initials}
            </button>

            {isDropdownOpen && (
              <div className="nav-dropdown-menu position-absolute end-0 mt-2">
                <div className="nav-dropdown-header">
                  <div className="d-flex align-items-center gap-2 mb-1">
                    <User size={14} className="text-muted" />
                    <span className="fw-bold text-dark extra-small text-truncate">
                      {displayName}
                    </span>
                  </div>
                  <div className="d-flex align-items-center gap-2">
                    <ShieldCheck size={14} className="text-muted" />
                    <span className="text-muted extra-small text-truncate">
                      {user?.role?.replaceAll("_", " ") || "User"}
                    </span>
                  </div>
                </div>
                <div className="p-1">
                  <button
                    type="button"
                    className="nav-dropdown-logout w-100 d-flex align-items-center gap-2 px-3 py-2 border-0 text-start extra-small fw-semibold"
                    onClick={handleLogout}
                    disabled={busy}
                  >
                    <LogOut size={14} />
                    <span>{busy ? "Signing out…" : "Log out"}</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>
      {error && <p role="alert" className="top-error">{error}</p>}
    </>
  );
}
