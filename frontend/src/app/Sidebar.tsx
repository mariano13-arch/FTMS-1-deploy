import { NavLink } from "react-router-dom";
import { navigation, type NavigationIcon } from "./navigation";

function NavIcon({ name }: { name: NavigationIcon }) {
  const paths: Record<NavigationIcon, React.ReactNode> = {
    dashboard: <><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /></>,
    requests: <><path d="M9 5h6M9 3h6v4H9zM6 5H4v16h16V5h-2M8 12h8M8 16h6" /></>,
    dispatch: <path d="M5 21V4M5 5h12l-2 4 2 4H5" />,
    map: <path d="M4 6l5-2 6 2 5-2v14l-5 2-6-2-5 2zM9 4v14M15 6v14" />,
    geofence: <><circle cx="12" cy="12" r="8" strokeDasharray="3 3" /><circle cx="12" cy="12" r="2" /></>,
    history: <path d="M4 12a8 8 0 1 0 2-5.3L4 9M4 4v5h5M12 7v5l3 2" />,
    drivers: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
    vehicles: <><path d="M3 16V8h12l4 4h2v4M15 8v4h4" /><circle cx="7" cy="17" r="2" /><circle cx="17" cy="17" r="2" /></>,
    alerts: <path d="M12 3L2.8 20h18.4zM12 9v5M12 17h.01" />,
    fuel: <path d="M7 21V4h9v17M5 21h13M7 8h9M16 10h2l2 2v5a2 2 0 0 1-4 0" />,
    maintenance: <path d="M14 6a4 4 0 0 0-5-3l3 3-3 3-3-3a4 4 0 0 0 5 5l8 8 2-2-8-8" />,
    reports: <path d="M5 20V10h4v10M10 20V4h4v16M15 20v-7h4v7M3 20h18" />,
    devices: <><rect x="5" y="5" width="14" height="14" rx="2" /><path d="M9 9h6v6H9zM9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M19 9h3M2 15h3M19 15h3" /></>,
    users: <><circle cx="9" cy="8" r="3" /><circle cx="17" cy="9" r="2" /><path d="M3 20a6 6 0 0 1 12 0M15 15a5 5 0 0 1 6 5" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" /></>,
  };
  return <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{paths[name]}</svg>;
}

export default function Sidebar({ open, collapsed, close, toggleCollapsed }: { open: boolean; collapsed: boolean; close: () => void; toggleCollapsed: () => void }) {
  return <aside id="primary-sidebar" className={`sidebar ${open ? "sidebar--open" : ""}`} data-collapsed={collapsed}>
    <div className="brand"><span className="brand__mark">FT<br />MS</span><strong className="sidebar-label" aria-hidden={collapsed}>Logistics 2 : FTMS</strong><button className="sidebar-collapse-toggle" type="button" onClick={toggleCollapsed} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed} aria-controls="primary-sidebar"><svg viewBox="0 0 24 24" aria-hidden="true"><path d={collapsed ? "M9 5l7 7-7 7" : "M15 5l-7 7 7 7"} /></svg></button></div>
    <nav aria-label="Main navigation">
      {navigation.map((group, index) => <section key={group.label ?? index}>
        {group.label && <h2 className="sidebar-label" aria-hidden={collapsed}>{group.label}</h2>}
        {group.items.map(item => <NavLink key={item.path} to={item.path} activeClassName="active" onClick={close} aria-label={item.label} title={collapsed ? item.label : undefined}>
          <NavIcon name={item.icon} /><span className="sidebar-link-label" aria-hidden={collapsed}>{item.label}</span>
        </NavLink>)}
      </section>)}
    </nav>
  </aside>;
}
