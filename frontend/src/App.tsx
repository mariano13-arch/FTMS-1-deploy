import React, { Suspense } from "react";
import { Redirect, Route, Switch, useParams } from "react-router-dom";
import AppShell from "./layouts/AppShell";
import LoginPage from "./features/auth/LoginPage";
import PlannedModule from "./features/auth/PlannedModule";
import ProtectedRoute from "./layouts/ProtectedRoute";
import { plannedPaths } from "./utils/navigation";
import LoadingIndicator from "./components/common/LoadingIndicator";
import "./styles.css";
import { useAuth } from "./contexts/AuthContext";
import { hasCapability } from "./services/auth";

function CapabilityPage({ module, action = "VIEW", fallback = "/dashboard", children }: { module: string; action?: string; fallback?: string | null; children: React.ReactNode }) {
  const { user } = useAuth();
  if (hasCapability(user, module, action)) return <>{children}</>;
  return fallback ? <Redirect to={fallback} /> : <p role="alert">You do not have permission to view this page.</p>;
}

const TransportRequestsPage = React.lazy(
  () => import("./features/transport-requests/pages/TransportRequestsPage"),
);
const TransportRequestDetailPage = React.lazy(
  () =>
    import("./features/transport-requests/pages/TransportRequestDetailPage"),
);
const TransportRequestFormPage = React.lazy(
  () => import("./features/transport-requests/pages/TransportRequestFormPage"),
);
const DispatchBoardPage = React.lazy(
  () => import("./features/dispatch/DispatchBoardPage"),
);
const VehicleRoutes = React.lazy(
  () => import("./features/vehicles/VehicleRoutes"),
);
const DriversPage = React.lazy(() => import("./features/drivers/DriversPage"));
const LiveFleetOperationsPage = React.lazy(
  () => import("./features/live-fleet/LiveFleetOperationsPage"),
);
const VehicleStatusPage = React.lazy(
  () => import("./features/live-fleet/VehicleStatusPage"),
);
const SetupPasswordPage = React.lazy(
  () => import("./features/driver-account/SetupPasswordPage"),
);
const StaffSetupPasswordPage = React.lazy(
  () => import("./features/staff-account/StaffSetupPasswordPage"),
);
const ForgotPasswordPage = React.lazy(() => import("./features/auth/ForgotPasswordPage"));
const ResetPasswordPage = React.lazy(() => import("./features/auth/ResetPasswordPage"));
const FuelAnalyticsPage = React.lazy(
  () => import("./features/fuel-analytics/FuelAnalyticsPage"),
);
const MaintenancePage = React.lazy(
  () => import("./features/maintenance/MaintenancePage"),
);
const DevicesPage = React.lazy(() => import("./features/devices/DevicesPage"));
const AlertsPage = React.lazy(() => import("./features/alerts/AlertsPage"));
const SettingsPage = React.lazy(() => import("./features/settings/SettingsPage"));
const SecuritySettingsPage = React.lazy(() => import("./features/settings/SettingsStaticPages").then((module) => ({ default: module.SecuritySettingsPage })));
const OperationalRulesSettingsPage = React.lazy(() => import("./features/settings/SettingsStaticPages").then((module) => ({ default: module.OperationalRulesSettingsPage })));
const IntegrationsSettingsPage = React.lazy(() => import("./features/settings/SettingsStaticPages").then((module) => ({ default: module.IntegrationsSettingsPage })));
const AiModelsSettingsPage = React.lazy(() => import("./features/settings/AiModelsSettingsPage"));
const RolesPermissionsPage = React.lazy(
  () => import("./features/settings/RolesPermissionsPage"),
);
const UsersPage = React.lazy(() => import("./features/users/UsersPage"));
const AuditLogsPage = React.lazy(() => import("./features/users/AuditLogsPage"));
const ReportsPage = React.lazy(() => import("./features/reports/ReportsPage"));
const TransportRequestReportPage = React.lazy(
  () => import("./features/reports/TransportRequestReportPage"),
);
const DispatchTripReportPage = React.lazy(() => import("./features/reports/DispatchTripReportPage"));
const FleetAssignmentReportPage = React.lazy(() => import("./features/reports/FleetAssignmentReportPage"));
const SafetyGeofenceReportPage = React.lazy(() => import("./features/reports/SafetyGeofenceReportPage"));
const DeviceTelemetryReportPage = React.lazy(() => import("./features/reports/DeviceTelemetryReportPage"));
const InspectionMaintenanceReportPage = React.lazy(() => import("./features/reports/InspectionMaintenanceReportPage"));
const FuelReferenceReportPage = React.lazy(() => import("./features/reports/FuelReferenceReportPage"));
const DashboardPage = React.lazy(() => import("./features/dashboard/DashboardPage"));

function LiveFleetVehicleStatusRoute() {
  const { deviceId = "" } = useParams<{ deviceId: string }>();
  return (
    <>
      <LiveFleetOperationsPage key={`live-map-${deviceId}`} focusedVehicleId={deviceId} />
      <VehicleStatusPage key={`vehicle-status-${deviceId}`} />
    </>
  );
}

export default function App() {
  return (
    <Switch>
      <Route path="/setup-password" exact>
        <Suspense
          fallback={<LoadingIndicator variant="card" message="Loading…" />}
        >
          <SetupPasswordPage />
        </Suspense>
      </Route>
      <Route path="/setup-staff-password" exact>
        <Suspense fallback={<LoadingIndicator variant="card" message="Loading…" />}>
          <StaffSetupPasswordPage />
        </Suspense>
      </Route>
      <Route path="/login" exact>
        <LoginPage />
      </Route>
      <Route path="/forgot-password" exact>
        <ForgotPasswordPage />
      </Route>
      <Route path="/reset-password" exact>
        <ResetPasswordPage />
      </Route>
      <Route path="/">
        <ProtectedRoute>
          <AppShell>
            <Suspense
              fallback={<LoadingIndicator variant="card" message="Loading…" />}
            >
              <Switch>
                <Route path="/dashboard" exact>
                  <CapabilityPage module="DASHBOARD" fallback={null}><DashboardPage /></CapabilityPage>
                </Route>
                <Route path="/transport-requests/new" exact>
                  <CapabilityPage module="TRANSPORT_REQUESTS" action="EDIT"><TransportRequestFormPage /></CapabilityPage>
                </Route>
                <Route path="/transport-requests/:requestId/edit" exact>
                  <CapabilityPage module="TRANSPORT_REQUESTS" action="EDIT"><TransportRequestFormPage editing /></CapabilityPage>
                </Route>
                <Route path="/transport-requests/:requestId" exact>
                  <CapabilityPage module="TRANSPORT_REQUESTS"><TransportRequestDetailPage /></CapabilityPage>
                </Route>
                <Route path="/transport-requests" exact>
                  <CapabilityPage module="TRANSPORT_REQUESTS"><TransportRequestsPage /></CapabilityPage>
                </Route>
                <Route path="/active-trips" exact>
                  <Redirect to="/transport-requests" />
                </Route>
                <Route path="/vehicles">
                  <CapabilityPage module="VEHICLES"><VehicleRoutes /></CapabilityPage>
                </Route>
                <Route path="/drivers" exact>
                  <CapabilityPage module="DRIVERS"><DriversPage /></CapabilityPage>
                </Route>
                <Route path="/dispatch-board" exact>
                  <CapabilityPage module="DISPATCH_BOARD"><DispatchBoardPage /></CapabilityPage>
                </Route>
                <Route path="/live-map/vehicles/:deviceId/status" exact>
                  <CapabilityPage module="LIVE_MAP"><LiveFleetVehicleStatusRoute /></CapabilityPage>
                </Route>
                <Route path="/live-map" exact>
                  <CapabilityPage module="LIVE_MAP"><LiveFleetOperationsPage /></CapabilityPage>
                </Route>
                <Route path="/fuel-analytics" exact>
                  <CapabilityPage module="FUEL_ANALYTICS"><FuelAnalyticsPage /></CapabilityPage>
                </Route>
                <Route path="/maintenance" exact>
                  <CapabilityPage module="MAINTENANCE"><MaintenancePage /></CapabilityPage>
                </Route>
                <Route path="/devices" exact>
                  <CapabilityPage module="DEVICES"><DevicesPage /></CapabilityPage>
                </Route>
                <Route path="/alerts" exact>
                  <CapabilityPage module="ALERTS_SOS"><AlertsPage /></CapabilityPage>
                </Route>
                <Route path="/reports/transport-requests" exact>
                  <CapabilityPage module="REPORTS"><TransportRequestReportPage /></CapabilityPage>
                </Route>
                <Route path="/reports/dispatch-trips" exact>
                  <CapabilityPage module="REPORTS"><DispatchTripReportPage /></CapabilityPage>
                </Route>
                <Route path="/reports/fleet-assignments" exact>
                  <CapabilityPage module="REPORTS"><FleetAssignmentReportPage /></CapabilityPage>
                </Route>
                <Route path="/reports/safety-geofence" exact>
                  <CapabilityPage module="REPORTS"><SafetyGeofenceReportPage /></CapabilityPage>
                </Route>
                <Route path="/reports/device-telemetry" exact>
                  <CapabilityPage module="REPORTS"><DeviceTelemetryReportPage /></CapabilityPage>
                </Route>
                <Route path="/reports/inspection-maintenance" exact>
                  <CapabilityPage module="REPORTS"><InspectionMaintenanceReportPage /></CapabilityPage>
                </Route>
                <Route path="/reports/fuel-reference" exact>
                  <CapabilityPage module="REPORTS"><FuelReferenceReportPage /></CapabilityPage>
                </Route>
                <Route path="/reports" exact>
                  <CapabilityPage module="REPORTS"><ReportsPage /></CapabilityPage>
                </Route>
                <Route path="/settings/roles-permissions" exact>
                  <Redirect to="/users/roles-permissions" />
                </Route>
                <Route path="/settings/security" exact>
                  <CapabilityPage module="SYSTEM_SETTINGS"><SecuritySettingsPage /></CapabilityPage>
                </Route>
                <Route path="/settings/operational-rules" exact>
                  <CapabilityPage module="SYSTEM_SETTINGS"><OperationalRulesSettingsPage /></CapabilityPage>
                </Route>
                <Route path="/settings/integrations" exact>
                  <CapabilityPage module="SYSTEM_SETTINGS"><IntegrationsSettingsPage /></CapabilityPage>
                </Route>
                <Route path="/settings/ai-models" exact>
                  <CapabilityPage module="SYSTEM_SETTINGS"><AiModelsSettingsPage /></CapabilityPage>
                </Route>
                <Route path="/settings" exact>
                  <CapabilityPage module="SYSTEM_SETTINGS"><SettingsPage /></CapabilityPage>
                </Route>
                <Route path="/users/roles-permissions" exact>
                  <RolesPermissionsPage />
                </Route>
                <Route path="/users/audit-logs" exact>
                  <AuditLogsPage />
                </Route>
                <Route path="/users" exact>
                  <UsersPage />
                </Route>
                {plannedPaths.map((item) => (
                  <Route path={item.path} exact key={item.path}>
                    <PlannedModule title={item.label} />
                  </Route>
                ))}
                <Redirect to="/transport-requests" />
              </Switch>
            </Suspense>
          </AppShell>
        </ProtectedRoute>
      </Route>
    </Switch>
  );
}
