import React, { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  FileText,
  Kanban,
  Map as MapIcon,
  UserCheck,
  ClipboardCheck,
  AlertTriangle,
  Fuel,
  Wrench,
  BarChart3,
  Cpu,
  ShieldCheck,
  Settings,
  Search,
  RefreshCw,
  LucideIcon,
} from "lucide-react";
import {
  fetchSidebarCounts,
  SidebarCounts,
} from "../services/sidebarService";

interface NavItem {
  label: string;
  path: string;
  icon: LucideIcon;
  badge?: string | number;
}

interface NavSection {
  title?: string;
  items: NavItem[];
}

const navSections: NavSection[] = [
  {
    items: [
      {
        label: "Dashboard",
        path: "/dashboard",
        icon: LayoutDashboard,
      },
    ],
  },
  {
    title: "OPERATIONS",
    items: [
      {
        label: "Transport Requests",
        path: "/transport-requests",
        icon: FileText,
      },
      {
        label: "Dispatch Board",
        path: "/dispatch-board",
        icon: Kanban,
      },
      { label: "Live Map", path: "/live-map", icon: MapIcon },
    ],
  },
  {
    title: "FLEET & SAFETY",
    items: [
      { label: "Drivers & Safety Scores", path: "/drivers", icon: UserCheck },
      {
        label: "Vehicles & Inspections",
        path: "/vehicles",
        icon: ClipboardCheck,
      },
      {
        label: "Alerts & Incidents",
        path: "/alerts",
        icon: AlertTriangle,
      },
    ],
  },
  {
    title: "INTELLIGENCE",
    items: [
      { label: "Fuel Analytics", path: "/fuel-analytics", icon: Fuel },
      {
        label: "Maintenance & Predictions",
        path: "/maintenance",
        icon: Wrench,
      },
      { label: "Reports", path: "/reports", icon: BarChart3 },
    ],
  },
  {
    title: "ADMINISTRATION",
    items: [
      { label: "Devices", path: "/devices", icon: Cpu },
      {
        label: "Users Roles & Audit Logs",
        path: "/users",
        icon: ShieldCheck,
      },
      { label: "System Rules & Settings", path: "/settings", icon: Settings },
    ],
  },
];

const COUNTS_POLL_INTERVAL_MS = 30_000;

interface SidebarProps {
  open: boolean;
  collapsed: boolean;
  close: () => void;
  toggleCollapsed: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  open,
  collapsed,
  close,
}) => {
  const location = useLocation();
  const [searchQuery, setSearchQuery] = useState("");
  const [liveCounts, setLiveCounts] = useState<SidebarCounts>({});
  const [countsLoading, setCountsLoading] = useState(false);
  const [countsError, setCountsError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshCounts = useCallback(async () => {
    setCountsLoading(true);
    setCountsError(null);
    try {
      const counts = await fetchSidebarCounts();
      setLiveCounts(counts);
    } catch {
      setCountsError("Unable to refresh sidebar notifications.");
    } finally {
      setCountsLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function initialFetch() {
      setCountsLoading(true);
      setCountsError(null);
      try {
        const counts = await fetchSidebarCounts();
        if (!cancelled) setLiveCounts(counts);
      } catch {
        if (!cancelled) setCountsError("Unable to refresh sidebar notifications.");
      } finally {
        if (!cancelled) setCountsLoading(false);
      }
    }
    initialFetch();
    pollRef.current = setInterval(refreshCounts, COUNTS_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [refreshCounts]);

  const resolveBadge = (item: NavItem): string | number | undefined => {
    const liveValue = liveCounts[item.path];
    if (typeof liveValue === "number" && liveValue > 0) return liveValue;
    if (typeof item.badge === "number" && item.badge > 0) return item.badge;
    return undefined;
  };

  return (
    <aside
      id="primary-sidebar"
      className={`app-sidebar ${open ? "sidebar--open" : ""}`}
      data-collapsed={collapsed}
    >
      <div className="d-flex align-items-center gap-2 px-2 mb-3">
        <div className="sidebar-brand-badge d-flex align-items-center justify-content-center fw-bold">
          FT<br />MS
        </div>
        {!collapsed && (
          <div className="fw-bold text-white lh-sm" style={{ fontSize: "0.85rem" }}>
            Logistics 2 : FTMS
          </div>
        )}
      </div>

      <div className="px-2 mb-3">
        <div className="d-flex align-items-center justify-content-between mb-1">
          <div className="sidebar-section-header">SEARCH</div>
          <button
            type="button"
            className="btn btn-sm p-0 border-0 bg-transparent d-flex align-items-center"
            onClick={refreshCounts}
            disabled={countsLoading}
            title="Refresh notifications"
            aria-label="Refresh sidebar notifications"
          >
            <RefreshCw
              size={11}
              className={countsLoading ? "truck-wheel-spin" : ""}
              style={{ color: "rgba(250, 246, 241, 0.6)" }}
            />
          </button>
        </div>
        {!collapsed && (
          <div className="sidebar-search-box d-flex align-items-center gap-2 px-2 py-1 rounded">
            <Search size={14} className="sidebar-search-icon" />
            <input
              type="text"
              placeholder="Search..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="sidebar-search-input w-100"
            />
          </div>
        )}
        {countsError && (
          <div className="text-danger mt-1" style={{ fontSize: "0.65rem" }} role="alert">
            {countsError}
          </div>
        )}
      </div>

      <nav className="sidebar-nav-scrollable" aria-label="Main navigation">
        {navSections
          .map((section) => {
            const filteredItems = section.items.filter((item) =>
              item.label.toLowerCase().includes(searchQuery.toLowerCase()),
            );
            if (filteredItems.length === 0) return null;
            return { ...section, items: filteredItems };
          })
          .filter((section): section is NonNullable<typeof section> => section !== null)
          .map((section, idx) => (
            <div key={idx} className="sidebar-nav-group">
              {section.title && (
                <div className="sidebar-section-header px-2" aria-hidden={collapsed || undefined}>
                  {section.title}
                </div>
              )}
              {section.items.map((item) => {
                const Icon = item.icon;
                const isActive = location.pathname === item.path;
                const badgeValue = resolveBadge(item);

                return (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    className={`sidebar-nav-item d-flex align-items-center justify-content-between px-2 py-2 rounded text-decoration-none ${isActive ? "active" : ""}`}
                    onClick={close}
                    title={collapsed ? item.label : undefined}
                  >
                    <div className="d-flex align-items-center gap-2">
                      <Icon size={16} className="sidebar-icon" />
                      {!collapsed && (
                        <span className="sidebar-label">{item.label}</span>
                      )}
                    </div>
                    {badgeValue !== undefined && !collapsed && (
                      <span className={`badge rounded-pill sidebar-badge ${isActive ? "active-badge" : ""}`}>
                        {badgeValue}
                      </span>
                    )}
                  </NavLink>
                );
              })}
            </div>
          ))}
      </nav>
    </aside>
  );
};

export default Sidebar;
