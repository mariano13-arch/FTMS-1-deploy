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
  ChevronRight,
  PanelLeftClose,
  LucideIcon,
} from "lucide-react";
import {
  fetchSidebarCounts,
  SidebarCounts,
} from "../services/sidebarService";
import { useAuth } from "../contexts/AuthContext";
import { hasCapability } from "../services/auth";

interface NavItem {
  label: string;
  path: string;
  icon: LucideIcon;
  badge?: string | number;
  capability?: [string, string];
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
        icon: FileText, capability: ["TRANSPORT_REQUESTS", "VIEW"],
      },
      {
        label: "Dispatch Board",
        path: "/dispatch-board",
        icon: Kanban, capability: ["DISPATCH_BOARD", "VIEW"],
      },
      { label: "Live Map", path: "/live-map", icon: MapIcon, capability: ["LIVE_MAP", "VIEW"] },
    ],
  },
  {
    title: "FLEET & SAFETY",
    items: [
      { label: "Drivers & Safety Scores", path: "/drivers", icon: UserCheck, capability: ["DRIVERS", "VIEW"] },
      {
        label: "Vehicles & Inspections",
        path: "/vehicles",
        icon: ClipboardCheck, capability: ["VEHICLES", "VIEW"],
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
      { label: "Fuel Analytics", path: "/fuel-analytics", icon: Fuel, capability: ["FUEL_ANALYTICS", "VIEW"] },
      {
        label: "Maintenance & Predictions",
        path: "/maintenance",
        icon: Wrench, capability: ["MAINTENANCE", "VIEW"],
      },
      { label: "Reports", path: "/reports", icon: BarChart3 },
    ],
  },
  {
    title: "ADMINISTRATION",
    items: [
      { label: "Devices", path: "/devices", icon: Cpu, capability: ["VEHICLES", "EDIT"] },
      {
        label: "Users Roles & Audit Logs",
        path: "/users",
        icon: ShieldCheck, capability: ["USERS_ACCESS", "VIEW_USERS"],
      },
      { label: "System Rules & Settings", path: "/settings", icon: Settings, capability: ["SYSTEM_SETTINGS", "VIEW"] },
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
  toggleCollapsed,
}) => {
  const location = useLocation();
  const { user } = useAuth();
  const [liveCounts, setLiveCounts] = useState<SidebarCounts>({});
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshCounts = useCallback(async () => {
    try {
      const counts = await fetchSidebarCounts();
      setLiveCounts(counts);
    } catch {
      // Notification counts are supplementary; retry on the next polling cycle.
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function initialFetch() {
      try {
        const counts = await fetchSidebarCounts();
        if (!cancelled) setLiveCounts(counts);
      } catch {
        // Notification counts are supplementary; retry on the next polling cycle.
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
      <div className="sidebar-brand d-flex align-items-center gap-2 px-2 mb-3">
        <div className="sidebar-brand-badge d-flex align-items-center justify-content-center fw-bold">
          FT<br />MS
        </div>
        {!collapsed && (
          <div className="sidebar-brand-name fw-bold text-white lh-sm">
            Logistics 2 : FTMS
          </div>
        )}
      </div>

      <nav className="sidebar-nav-scrollable" aria-label="Main navigation">
        {navSections.map((section, idx) => (
            <div key={idx} className="sidebar-nav-group">
              {section.title && (
                <div className="sidebar-section-header px-2" aria-hidden={collapsed || undefined}>
                  {section.title}
                </div>
              )}
              {section.items.filter((item) => !item.capability || hasCapability(user, ...item.capability)).map((item) => {
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
                      <Icon size={18} className="sidebar-icon" />
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

      <div className="sidebar-footer-toggle px-2 py-2">
        <button
          type="button"
          className="btn btn-sm d-flex align-items-center justify-content-center border-0 bg-transparent text-white-50"
          onClick={toggleCollapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight size={20} /> : <PanelLeftClose size={16} />}
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;
