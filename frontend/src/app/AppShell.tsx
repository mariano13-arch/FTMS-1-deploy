import { useEffect, useState } from "react";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";

const preferenceKey = "ftms.sidebar.collapsed";
const storedCollapsedPreference = () => {
  try { return window.localStorage.getItem(preferenceKey) === "true"; }
  catch { return false; }
};

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(storedCollapsedPreference);
  useEffect(() => {
    try { window.localStorage.setItem(preferenceKey, String(sidebarCollapsed)); } catch { /* Optional UI preference. */ }
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const timer = window.setTimeout(() => window.dispatchEvent(new Event("resize")), reducedMotion ? 0 : 220);
    return () => window.clearTimeout(timer);
  }, [sidebarCollapsed]);
  return <div className="app-layout" data-sidebar-collapsed={sidebarCollapsed}><Sidebar open={sidebarOpen} collapsed={sidebarCollapsed} close={() => setSidebarOpen(false)} toggleCollapsed={() => setSidebarCollapsed(value => !value)} />
    {sidebarOpen && <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} />}
    <div className="app-main"><TopBar sidebarOpen={sidebarOpen} toggleSidebar={() => setSidebarOpen(value => !value)} /><main className="content">{children}</main></div>
  </div>;
}
