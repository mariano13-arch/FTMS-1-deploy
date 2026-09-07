import React, { Suspense } from "react";
import { Redirect, Route, Switch, useParams } from "react-router-dom";
import AppShell from "./layouts/AppShell";
import LoginPage from "./features/auth/LoginPage";
import PlannedModule from "./features/auth/PlannedModule";
import ProtectedRoute from "./layouts/ProtectedRoute";
import { plannedPaths } from "./utils/navigation";
import LoadingIndicator from "./components/common/LoadingIndicator";
import "./styles.css";

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
const FuelAnalyticsPage = React.lazy(
  () => import("./features/fuel-analytics/FuelAnalyticsPage"),
);
const MaintenancePage = React.lazy(
  () => import("./features/maintenance/MaintenancePage"),
);
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
      <Route path="/">
        <ProtectedRoute>
          <AppShell>
            <Suspense
              fallback={<LoadingIndicator variant="card" message="Loading…" />}
            >
              <Switch>
                <Route path="/transport-requests/new" exact>
                  <TransportRequestFormPage />
                </Route>
                <Route path="/transport-requests/:requestId/edit" exact>
                  <TransportRequestFormPage editing />
                </Route>
                <Route path="/transport-requests/:requestId" exact>
                  <TransportRequestDetailPage />
                </Route>
                <Route path="/transport-requests" exact>
                  <TransportRequestsPage />
                </Route>
                <Route path="/active-trips" exact>
                  <Redirect to="/transport-requests" />
                </Route>
                <Route path="/vehicles">
                  <VehicleRoutes />
                </Route>
                <Route path="/drivers" exact>
                  <DriversPage />
                </Route>
                <Route path="/dispatch-board" exact>
                  <DispatchBoardPage />
                </Route>
                <Route path="/live-map/vehicles/:deviceId/status" exact>
                  <LiveFleetVehicleStatusRoute />
                </Route>
                <Route path="/live-map" exact>
                  <LiveFleetOperationsPage />
                </Route>
                <Route path="/fuel-analytics" exact>
                  <FuelAnalyticsPage />
                </Route>
                <Route path="/maintenance" exact>
                  <MaintenancePage />
                </Route>
                <Route path="/settings/roles-permissions" exact>
                  <Redirect to="/users/roles-permissions" />
                </Route>
                <Route path="/settings/security" exact>
                  <SecuritySettingsPage />
                </Route>
                <Route path="/settings/operational-rules" exact>
                  <OperationalRulesSettingsPage />
                </Route>
                <Route path="/settings/integrations" exact>
                  <IntegrationsSettingsPage />
                </Route>
                <Route path="/settings/ai-models" exact>
                  <AiModelsSettingsPage />
                </Route>
                <Route path="/settings" exact>
                  <SettingsPage />
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
