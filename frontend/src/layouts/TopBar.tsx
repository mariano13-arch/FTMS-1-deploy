import { useEffect, useRef, useState } from "react";
import { Bell, LogOut, User, ShieldCheck } from "lucide-react";
import { useHistory } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { roleLabel } from "../services/auth";
import {
  getNotifications,
  getUnreadNotificationCount,
  markAllNotificationsRead,
  markNotificationRead,
  type UserNotification,
} from "../services/notifications";
import oxfordLogo from "../assets/images/oxford-suites-logo.png";

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

const relativeTime = (value: string) => {
  const elapsed = Math.max(0, Date.now() - new Date(value).getTime());
  const minutes = Math.floor(elapsed / 60_000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
};

export default function TopBar({ sidebarOpen, toggleSidebar }: { sidebarOpen: boolean; toggleSidebar: () => void }) {
  const { user, signOut } = useAuth();
  const history = useHistory();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [currentDateTime, setCurrentDateTime] = useState(() => new Date());
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notifications, setNotifications] = useState<UserNotification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [notificationsError, setNotificationsError] = useState("");
  const mounted = useRef(false);
  const inFlight = useRef(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const notificationRef = useRef<HTMLDivElement>(null);

  const displayName = user?.display_name?.trim() || user?.username || "User";
  const initials = user ? getInitials(displayName) : "?";

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setCurrentDateTime(new Date()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
      if (notificationRef.current && !notificationRef.current.contains(event.target as Node)) {
        setNotificationsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const refreshUnreadCount = async () => {
    try {
      const result = await getUnreadNotificationCount();
      if (mounted.current) setUnreadCount(result.unread_count);
    } catch {
      // Keep the last known count; the next poll will retry.
    }
  };

  const refreshNotifications = async () => {
    setNotificationsLoading(true);
    setNotificationsError("");
    try {
      const [page, count] = await Promise.all([
        getNotifications(),
        getUnreadNotificationCount(),
      ]);
      if (mounted.current) {
        setNotifications(page.results);
        setUnreadCount(count.unread_count);
      }
    } catch {
      if (mounted.current) setNotificationsError("Unable to load notifications.");
    } finally {
      if (mounted.current) setNotificationsLoading(false);
    }
  };

  useEffect(() => {
    void refreshUnreadCount();
    const poll = () => {
      if (document.visibilityState === "visible") void refreshUnreadCount();
    };
    const timer = window.setInterval(poll, 30_000);
    document.addEventListener("visibilitychange", poll);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", poll);
    };
  }, []);

  const openNotifications = () => {
    const next = !notificationsOpen;
    setNotificationsOpen(next);
    setIsDropdownOpen(false);
    if (next) void refreshNotifications();
  };

  const selectNotification = async (notification: UserNotification) => {
    if (!notification.is_read) {
      setNotifications((items) => items.map((item) => item.id === notification.id
        ? { ...item, is_read: true, read_at: new Date().toISOString() }
        : item));
      setUnreadCount((count) => Math.max(0, count - 1));
      try {
        await markNotificationRead(notification.id);
        void refreshNotifications();
      } catch {
        void refreshUnreadCount();
      }
    }
    setNotificationsOpen(false);
    if (notification.target_url.startsWith("/") && !notification.target_url.startsWith("//")) {
      history.push(notification.target_url);
    }
  };

  const markAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setNotifications((items) => items.map((item) => ({
        ...item,
        is_read: true,
        read_at: item.read_at ?? new Date().toISOString(),
      })));
      setUnreadCount(0);
      await refreshNotifications();
    } catch {
      setNotificationsError("Unable to mark notifications as read.");
    }
  };

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
            {currentDateTime.toLocaleDateString(undefined, {
              weekday: "short",
              month: "short",
              day: "numeric",
              year: "numeric",
            })}{" · "}{currentDateTime.toLocaleTimeString(undefined, {
              hour: "numeric",
              minute: "2-digit",
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

          <div className="notification-root position-relative" ref={notificationRef}>
            <button
              type="button"
              className="nav-icon-btn notification-bell"
              aria-label="Notifications"
              aria-expanded={notificationsOpen}
              onClick={openNotifications}
            >
              <Bell size={17} />
              {unreadCount > 0 && (
                <span className="notification-badge" aria-label={`${unreadCount} unread notifications`}>
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              )}
            </button>
            {notificationsOpen && (
              <section className="notification-menu position-absolute end-0 mt-2" aria-label="Notification center">
                <header className="notification-menu-header">
                  <strong>Notifications</strong>
                  <button type="button" onClick={() => void markAllRead()} disabled={unreadCount === 0}>
                    Mark all as read
                  </button>
                </header>
                <div className="notification-list">
                  {notificationsLoading && <p role="status" className="notification-state">Loading notifications…</p>}
                  {!notificationsLoading && notificationsError && <p role="alert" className="notification-state">{notificationsError}</p>}
                  {!notificationsLoading && !notificationsError && notifications.length === 0 && (
                    <p className="notification-state">No notifications yet.</p>
                  )}
                  {!notificationsLoading && notifications.map((notification) => (
                    <button
                      type="button"
                      key={notification.id}
                      className={`notification-item${notification.is_read ? "" : " notification-item--unread"}`}
                      onClick={() => void selectNotification(notification)}
                    >
                      <span className="notification-item-title">{notification.title}</span>
                      <span className="notification-item-message">{notification.message}</span>
                      <time dateTime={notification.created_at}>{relativeTime(notification.created_at)}</time>
                    </button>
                  ))}
                </div>
              </section>
            )}
          </div>

          <div className="position-relative" ref={dropdownRef}>
            <button
              type="button"
              className="nav-avatar-btn border-0 ms-1"
              aria-label="User profile"
              onClick={() => { setNotificationsOpen(false); setIsDropdownOpen((prev) => !prev); }}
            >
              {initials}
            </button>

            <div className={`nav-dropdown-menu position-absolute end-0 mt-2${isDropdownOpen ? "" : " d-none"}`}>
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
                      {roleLabel(user?.role)}
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
                    <span>{busy ? "Signing out…" : "Sign out"}</span>
                  </button>
                </div>
              </div>
          </div>
        </div>
      </header>
      {error && <p role="alert" className="top-error">{error}</p>}
    </>
  );
}
