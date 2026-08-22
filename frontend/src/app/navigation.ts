export type NavigationIcon = "dashboard" | "requests" | "dispatch" | "map" | "drivers" | "vehicles" | "alerts" | "fuel" | "maintenance" | "reports" | "devices" | "users" | "settings";
export type NavigationItem = { label: string; path: string; icon: NavigationIcon };
export type NavigationGroup = { label?: string; items: NavigationItem[] };

export const navigation: NavigationGroup[] = [
  { items: [{ label: "Dashboard", path: "/dashboard", icon: "dashboard" }] },
  { label: "Operations", items: [
    { label: "Transport Requests", path: "/transport-requests", icon: "requests" },
    { label: "Dispatch Board", path: "/dispatch-board", icon: "dispatch" },
    { label: "Live Map", path: "/live-map", icon: "map" },
  ] },
  { label: "Fleet & Safety", items: [
    { label: "Drivers & Safety Scores", path: "/drivers", icon: "drivers" },
    { label: "Vehicles", path: "/vehicles", icon: "vehicles" },
    { label: "Alerts & Incidents", path: "/alerts", icon: "alerts" },
  ] },
  { label: "Intelligence", items: [
    { label: "Fuel Analytics", path: "/fuel-analytics", icon: "fuel" },
    { label: "Maintenance & Predictions", path: "/maintenance", icon: "maintenance" },
    { label: "Reports", path: "/reports", icon: "reports" },
  ] },
  { label: "Administration", items: [
    { label: "Devices", path: "/devices", icon: "devices" },
    { label: "Users, Roles & Audit Logs", path: "/users", icon: "users" },
    { label: "System Rules & Settings", path: "/settings", icon: "settings" },
  ] },
];

export const plannedPaths = navigation.flatMap(group => group.items)
  .filter(item => !["/transport-requests", "/vehicles", "/drivers", "/dispatch-board", "/live-map"].includes(item.path));
