import { useEffect, useMemo, useState } from "react";
import LoadingIndicator from "../../../components/common/LoadingIndicator";
import {
  getOperationalAssignments,
  type OperationalAssignmentPage,
} from "../../../services/dispatch";
import {
  getFleetActiveAssignmentRoute,
  getFleetLiveVehicles,
  type FleetActiveRoute,
  type FleetLiveVehicle,
} from "../../live-fleet/api";
import { humanize as label } from "../../../utils/text";
import type { Summary, TransportRoute } from "../types";
import RequestDetailsDrawer from "./RequestDetailsDrawer";
import RequestMap from "./RequestMap";
import SelectedRequestOverview from "./SelectedRequestOverview";
import WorkflowKpiStrip from "./WorkflowKpiStrip";

type Props = { scope: "active" | "completed"; summary: Summary | null };

export default function ExecutionTripsView({ scope, summary }: Props) {
  const [pageNumber, setPageNumber] = useState(1);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState<OperationalAssignmentPage | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [route, setRoute] = useState<TransportRoute | null>(null);
  const [plannedRoute, setPlannedRoute] = useState<TransportRoute | null>(null);
  const [activeRoute, setActiveRoute] = useState<FleetActiveRoute | null>(null);
  const [routeState, setRouteState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [drawerRequestId, setDrawerRequestId] = useState<string | null>(null);
  const [fleetVehicles, setFleetVehicles] = useState<FleetLiveVehicle[]>([]);

  useEffect(() => {
    setPageNumber(1);
    setSelectedId(null);
  }, [scope, search]);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    void getOperationalAssignments(scope, pageNumber, search, controller.signal)
      .then((result) => {
        setPage(result);
        setSelectedId((current) =>
          result.results.some((item) => item.id === current)
            ? current
            : (result.results[0]?.id ?? null),
        );
        setState("ready");
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError"))
          setState("error");
      });
    return () => controller.abort();
  }, [pageNumber, scope, search]);

  useEffect(() => {
    if (scope !== "active") {
      setFleetVehicles([]);
      return;
    }
    const controller = new AbortController();
    void getFleetLiveVehicles(controller.signal)
      .then((response) =>
        setFleetVehicles(Array.isArray(response.vehicles) ? response.vehicles : []),
      )
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError"))
          setFleetVehicles([]);
      });
    return () => controller.abort();
  }, [scope]);

  const selected = useMemo(
    () => page?.results.find((item) => item.id === selectedId) ?? null,
    [page, selectedId],
  );

  useEffect(() => {
    if (!selected) {
      setRoute(null);
      setPlannedRoute(null);
      setActiveRoute(null);
      setRouteState("idle");
      return;
    }
    if (scope === "completed") {
      setRoute(null);
      setPlannedRoute(null);
      setActiveRoute(null);
      setRouteState("idle");
      return;
    }
    const controller = new AbortController();
    setRoute(null);
    setPlannedRoute(null);
    setActiveRoute(null);
    setRouteState("loading");
    void getFleetActiveAssignmentRoute(selected.id, controller.signal)
      .then(({ route: result }) => {
        setActiveRoute(result);
        setRoute(result.route ? { request_id: selected.transport_request_id, ...result.route } : null);
        setPlannedRoute(result.planned_route ? { request_id: selected.transport_request_id, ...result.planned_route } : null);
        setRouteState(result.route || result.planned_route ? "ready" : result.route_status === "NOT_ACTIVE" ? "idle" : "error");
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError"))
          setRouteState("error");
      });
    return () => controller.abort();
  }, [scope, selected]);

  const totalPages = Math.max(1, Math.ceil((page?.count ?? 0) / 15));
  const title = scope === "active" ? "active trips" : "completed trips";
  const liveVehicle = selected
    ? fleetVehicles.find(
        (vehicle) =>
          vehicle.device_id === selected.vehicle.device_id &&
          vehicle.telemetry?.telemetry_source === "real",
      ) ?? null
    : null;

  return (
    <div className={`execution-workspace execution-workspace--${scope}`}>
      {state === "loading" && !page && (
        <LoadingIndicator variant="card" message={`Loading ${title}…`} />
      )}
      {state === "error" && (
        <div className="state-card" role="alert">Unable to load {title}.</div>
      )}
      {page && (
        <div className={`request-workspace request-workspace--fixed${drawerRequestId ? " request-workspace--drawer-open" : ""}`}>
          <div className="request-picker request-picker--scroll" aria-label={`${scope === "active" ? "Active" : "Completed"} trip queue`}>
            <div className="panel-title">
              <strong>{scope === "active" ? "Active trip queue" : "Completed trip queue"}</strong>
              <span className="queue-count">{page.count} matching {title}</span>
            </div>
            <div className="filter-search-group">
              <label className="visually-hidden" htmlFor={`${scope}-trip-search`}>Search {title}</label>
              <input
                id={`${scope}-trip-search`}
                type="search"
                value={search}
                placeholder={`Search ${title}`}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
            <div className="request-list-scroll">
            {page.results.length === 0 ? (
              <div className="request-picker-empty"><span>No {title} found.</span></div>
            ) : page.results.map((assignment) => {
              const request = assignment.transport_request;
              return (
                <button
                  type="button"
                  className={`execution-trip-row${assignment.id === selectedId ? " selected" : ""}`}
                  key={assignment.id}
                  onClick={() => setSelectedId(assignment.id)}
                >
                  <span className="request-queue-primary">
                    <strong>{request.request_number}</strong>
                    <span>{label(request.request_type)}</span>
                    <span className="request-queue-indicators execution-trip-status">
                      {assignment.execution_status_label}
                    </span>
                  </span>
                  <span className="request-queue-secondary">
                    <span>{assignment.driver.full_name} · {assignment.vehicle.display_name}</span>
                    <span>{request.pickup_name} → {request.destination_name}</span>
                    <time>
                      {scope === "completed" && assignment.completed_at
                        ? `Completed ${new Date(assignment.completed_at).toLocaleString()}`
                        : new Date(request.scheduled_pickup_at).toLocaleString()}
                    </time>
                  </span>
                </button>
              );
            })}
            </div>
            {page.count > 0 && (
            <nav className="request-pagination" aria-label={`${scope === "active" ? "Active" : "Completed"} trip pages`}>
              <span>Showing {(pageNumber - 1) * 15 + 1}–{Math.min(pageNumber * 15, page.count)} of {page.count}</span>
              <div>
                <button type="button" className="btn-filter" disabled={!page.previous} onClick={() => setPageNumber((value) => Math.max(1, value - 1))}>Previous</button>
                <span>Page {pageNumber} of {totalPages}</span>
                <button type="button" className="btn-filter" disabled={!page.next} onClick={() => setPageNumber((value) => value + 1)}>Next</button>
              </div>
            </nav>
            )}
          </div>
          <div className="request-right-workspace" aria-label="Trip workspace">
            <WorkflowKpiStrip summary={summary} />
            <div className="map-side" aria-label="Trip map">
              <RequestMap
                request={selected?.transport_request ?? null}
                route={route}
                plannedRoute={plannedRoute}
                routeState={routeState}
                fleetLocations={
                  liveVehicle?.telemetry
                    ? [{
                        deviceId: liveVehicle.device_id,
                        latitude: liveVehicle.telemetry.latitude,
                        longitude: liveVehicle.telemetry.longitude,
                        label: liveVehicle.display_name,
                        telemetryState: liveVehicle.telemetry_state,
                        positionSource: liveVehicle.telemetry.position_source,
                        selected: true,
                      }]
                    : undefined
                }
                focusedVehicleId={liveVehicle?.device_id}
              />
              {selected && (
                <div className="trip-assignment-overlay">
                  <strong>{selected.execution_status_label}</strong>
                  <span>Driver: {selected.driver.full_name}</span>
                  <span>Vehicle: {selected.vehicle.display_name}</span>
                  <span>
                    {activeRoute?.vehicle_position
                      ? `${activeRoute.position_state === "STALE" ? "Last-known" : "Current"} position: ${activeRoute.vehicle_position.latitude.toFixed(5)}, ${activeRoute.vehicle_position.longitude.toFixed(5)} · ${new Date(activeRoute.vehicle_position.recorded_at).toLocaleString()}`
                      : "Live vehicle position: unavailable"}
                  </span>
                </div>
              )}
            </div>
            <SelectedRequestOverview
              request={selected?.transport_request ?? null}
              route={route}
              routeState={routeState}
              onViewDetails={() => selected && setDrawerRequestId(selected.transport_request_id)}
            />
            {drawerRequestId && (
              <RequestDetailsDrawer
                requestId={drawerRequestId}
                mode="readOnly"
                route={route}
                onClose={() => setDrawerRequestId(null)}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
