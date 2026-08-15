import { Redirect, Route, Switch } from "react-router-dom";
import AppShell from "./app/AppShell";
import LoginPage from "./app/LoginPage";
import PlannedModule from "./app/PlannedModule";
import ProtectedRoute from "./app/ProtectedRoute";
import { plannedPaths } from "./app/navigation";
import TransportRequestDetailPage from "./features/transport-requests/pages/TransportRequestDetailPage";
import TransportRequestFormPage from "./features/transport-requests/pages/TransportRequestFormPage";
import TransportRequestsPage from "./features/transport-requests/pages/TransportRequestsPage";
import VehicleRoutes from "./features/vehicles/VehicleRoutes";
import DriversPage from "./features/drivers/DriversPage";
import DispatchBoardPage from "./features/dispatch/DispatchBoardPage";
import "./styles.css";

export default function App() {
  return <Switch><Route path="/login" exact><LoginPage /></Route><Route path="/"><ProtectedRoute><AppShell><Switch>
    <Route path="/transport-requests/new" exact><TransportRequestFormPage /></Route>
    <Route path="/transport-requests/:requestId/edit" exact><TransportRequestFormPage editing /></Route>
    <Route path="/transport-requests/:requestId" exact><TransportRequestDetailPage /></Route>
    <Route path="/transport-requests" exact><TransportRequestsPage /></Route>
    <Route path="/active-trips" exact><Redirect to="/transport-requests" /></Route>
    <Route path="/vehicles"><VehicleRoutes /></Route>
    <Route path="/drivers" exact><DriversPage /></Route>
    <Route path="/dispatch-board" exact><DispatchBoardPage /></Route>
    {plannedPaths.map(item => <Route path={item.path} exact key={item.path}><PlannedModule title={item.label} /></Route>)}
    <Redirect to="/transport-requests" />
  </Switch></AppShell></ProtectedRoute></Route></Switch>;
}
