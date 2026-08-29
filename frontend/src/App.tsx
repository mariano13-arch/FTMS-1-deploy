import React, { Suspense } from "react";
import { Redirect, Route, Switch } from "react-router-dom";
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
const SetupPasswordPage = React.lazy(
  () => import("./features/driver-account/SetupPasswordPage"),
);
const FuelAnalyticsPage = React.lazy(
  () => import("./features/fuel-analytics/FuelAnalyticsPage"),
);

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
                <Route path="/live-map" exact>
                  <LiveFleetOperationsPage />
                </Route>
                <Route path="/fuel-analytics" exact>
                  <FuelAnalyticsPage />
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
