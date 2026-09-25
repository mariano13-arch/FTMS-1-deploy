import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../../contexts/AuthContext";
import CalendarView from "../components/CalendarView";
import RequestMap from "../components/RequestMap";
import RequestDetailsDrawer from "../components/RequestDetailsDrawer";
import LoadingIndicator from "../../../components/common/LoadingIndicator";
import {
  PriorityChip,
  WorkflowStatusBadge,
} from "../components/RequestIndicators";
import SelectedRequestOverview from "../components/SelectedRequestOverview";
import ExecutionTripsView from "../components/ExecutionTripsView";
import WorkflowKpiStrip from "../components/WorkflowKpiStrip";
import { humanize as label } from "../../../utils/text";
import { getRequestRoute, getRequests, getSummary } from "../api";
import {
  requestTypes,
  type RequestPage,
  type Summary,
  type TransportRequestListItem,
  type TransportRoute,
} from "../types";
import { distanceLabel, durationLabel, delayLabel } from "../routeFormat";

type Tab =
  | "All Requests"
  | "For Approval"
  | "Dispatch Queue"
  | "Active Trips"
  | "Completed"
  | "Calendar";
type AdvancedFilters = {
  priority: string;
  source_system: string;
  request_type: string;
  assignment: string;
  scheduled_date: string;
};
const emptyFilters: AdvancedFilters = {
  priority: "",
  source_system: "",
  request_type: "",
  assignment: "all",
  scheduled_date: "",
};
const tabs: Tab[] = [
  "All Requests",
  "For Approval",
  "Dispatch Queue",
  "Active Trips",
  "Completed",
  "Calendar",
];
const tabStatus: Partial<Record<Tab, string>> = {
  "For Approval": "FOR_APPROVAL,NEEDS_MORE_DETAILS",
  "Dispatch Queue": "APPROVED",
};
const tabCount = (tab: Tab, summary: Summary | null) =>
  tab === "All Requests"
    ? summary?.total
    : tab === "For Approval"
      ? summary?.approval_queue
      : tab === "Dispatch Queue"
        ? summary?.dispatch_queue
        : tab === "Active Trips"
          ? summary?.active_trips
          : tab === "Completed"
            ? summary?.completed_trips
        : undefined;
type RouteEntry = {
  state: "loading" | "ready" | "error";
  data: TransportRoute | null;
};
const isTransportRoute = (value: TransportRoute) =>
  value?.geometry?.type === "LineString" &&
  Array.isArray(value.geometry.coordinates) &&
  Number.isFinite(value.distance_meters) &&
  Number.isFinite(value.duration_seconds) &&
  Number.isFinite(value.traffic_delay_seconds);

export default function TransportRequestsPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>("All Requests");
  const [pageNumber, setPageNumber] = useState(1);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState<RequestPage | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selectedIdRef = useRef<string | null>(null);
  const filterPanelRef = useRef<HTMLDivElement>(null);
  const [searchValue, setSearchValue] = useState("");
  const [filters, setFilters] = useState<AdvancedFilters>(emptyFilters);
  const [filterPanelOpen, setFilterPanelOpen] = useState(false);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [routes, setRoutes] = useState<Record<string, RouteEntry>>({});
  const routeControllers = useRef(new Map<string, AbortController>());
  const [summaryVisible, setSummaryVisible] = useState(true);
  const [drawerRequestId, setDrawerRequestId] = useState<string | null>(null);
  const [queueMenuId, setQueueMenuId] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState("");
  const load = useCallback(
    (signal?: AbortSignal) => {
      const values = new URLSearchParams(query);
      const requestedStatus = tabStatus[tab];
      values.set("page", String(pageNumber));
      values.set("page_size", "15");
      if (requestedStatus) values.set("status", requestedStatus);
      else values.delete("status");
      const listRequired = !["Active Trips", "Completed", "Calendar"].includes(tab);
      return Promise.all([
        listRequired
          ? getRequests(values.toString(), signal)
          : Promise.resolve(null),
        getSummary(signal),
      ])
        .then(([requests, counts]) => {
          setSummary(counts);
          if (requests) {
            if (requests.count > 0 && requests.results.length === 0 && pageNumber > 1) {
              setPageNumber((current) => Math.max(1, current - 1));
              return;
            }
            const previousId = selectedIdRef.current;
            const selected =
              requests.results.find((item) => item.id === previousId) ??
              requests.results[0] ??
              null;
            if (selected?.id && selected.id !== previousId)
              setSummaryVisible(true);
            selectedIdRef.current = selected?.id ?? null;
            setPage(requests);
            setSelectedId(selectedIdRef.current);
          } else {
            selectedIdRef.current = null;
            setPage(null);
            setSelectedId(null);
          }
          setState("ready");
        })
        .catch((error: unknown) => {
          if (!(error instanceof DOMException && error.name === "AbortError"))
            setState("error");
        });
    },
    [pageNumber, query, tab],
  );
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);
  const buildQuery = useCallback(
    (search: string, advanced: AdvancedFilters) => {
      const values = new URLSearchParams();
      if (search.trim()) values.set("search", search.trim());
      for (const [key, value] of Object.entries(advanced))
        if (value && !(key === "assignment" && value === "all"))
          values.set(key, value);
      values.set("ordering", "scheduled_pickup_at");
      return values.toString();
    },
    [],
  );
  const updateQuery = useCallback(
    (search: string, advanced: AdvancedFilters) => {
      const nextQuery = buildQuery(search, advanced);
      setPageNumber(1);
      setState("loading");
      setQuery((current) => (current === nextQuery ? current : nextQuery));
    },
    [buildQuery],
  );
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      updateQuery(searchValue, filters);
    }, 400);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [searchValue, filters, updateQuery]);
  useEffect(() => {
    const closeOnOutsideClick = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!filterPanelRef.current?.contains(target)) setFilterPanelOpen(false);
      if (
        !(target instanceof Element) ||
        !target.closest(".request-queue-actions")
      )
        setQueueMenuId(null);
    };
    document.addEventListener("pointerdown", closeOnOutsideClick);
    return () =>
      document.removeEventListener("pointerdown", closeOnOutsideClick);
  }, []);

  const updateSearch = (value: string) => {
    setSearchValue(value);
  };
  const changeFilter = (key: keyof AdvancedFilters, value: string) => {
    const next = { ...filters, [key]: value };
    setFilters(next);
    updateQuery(searchValue, next);
  };
  const resetFilters = () => {
    setSearchValue("");
    setFilters(emptyFilters);
    setFilterPanelOpen(false);
    selectedIdRef.current = null;
    setSelectedId(null);
    setState("loading");
    updateQuery("", emptyFilters);
  };
  const selected = page?.results.find((item) => item.id === selectedId) ?? null;
  const selectedRoute = selected ? routes[selected.id] : undefined;
  useEffect(() => {
    if (
      !selectedId ||
      routes[selectedId] ||
      routeControllers.current.has(selectedId)
    )
      return;
    const controller = new AbortController();
    routeControllers.current.set(selectedId, controller);
    setRoutes((current) => ({
      ...current,
      [selectedId]: { state: "loading", data: null },
    }));
    void getRequestRoute(selectedId, controller.signal)
      .then((data) =>
        setRoutes((current) => ({
          ...current,
          [selectedId]: isTransportRoute(data)
            ? { state: "ready", data }
            : { state: "error", data: null },
        })),
      )
      .catch((error) => {
        if (!(error instanceof DOMException && error.name === "AbortError"))
          setRoutes((current) => ({
            ...current,
            [selectedId]: { state: "error", data: null },
          }));
      })
      .finally(() => routeControllers.current.delete(selectedId));
  }, [routes, selectedId]);
  useEffect(
    () => () => {
      routeControllers.current.forEach((controller) => controller.abort());
      routeControllers.current.clear();
    },
    [],
  );
  const choose = (item: TransportRequestListItem) => {
    if (item.id !== selectedIdRef.current) setSummaryVisible(true);
    selectedIdRef.current = item.id;
    setSelectedId(item.id);
  };
  const viewDetails = (item: TransportRequestListItem) => {
    choose(item);
    setQueueMenuId(null);
    setDrawerRequestId(item.id);
  };
  const selectedAssignedVehicle = selected?.assigned_vehicle ?? null;
  const activeFilterCount = Object.entries(filters).filter(
    ([key, value]) => value && !(key === "assignment" && value === "all"),
  ).length;
  const queueFilter = (
    <div
      ref={filterPanelRef}
      className="advanced-filter-root queue-filter-root"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          setFilterPanelOpen(false);
          (
            event.currentTarget.querySelector(
              "button",
            ) as HTMLButtonElement | null
          )?.focus();
        }
      }}
    >
      <button
        type="button"
        className="filter-toggle btn-filter"
        aria-expanded={filterPanelOpen}
        aria-controls="transport-advanced-filters"
        onClick={() => setFilterPanelOpen((value) => !value)}
      >
        Filters
        {activeFilterCount > 0 && (
          <span
            className="active-filter-count"
            aria-label={`${activeFilterCount} active filters`}
          >
            {activeFilterCount}
          </span>
        )}
      </button>
      {filterPanelOpen && (
        <div id="transport-advanced-filters" className="advanced-filter-panel">
          <label>
            Priority
            <select
              value={filters.priority}
              onChange={(event) => changeFilter("priority", event.target.value)}
            >
              <option value="">All priorities</option>
              <option>LOW</option>
              <option>NORMAL</option>
              <option>HIGH</option>
              <option>URGENT</option>
            </select>
          </label>
          <label>
            Source
            <select
              value={filters.source_system}
              onChange={(event) =>
                changeFilter("source_system", event.target.value)
              }
            >
              <option value="">All sources</option>
              <option>HOTEL_MANAGEMENT_SYSTEM</option>
              <option>SUPPLY_CHAIN_MANAGEMENT_SYSTEM</option>
            </select>
          </label>
          <label>
            Type
            <select
              value={filters.request_type}
              onChange={(event) =>
                changeFilter("request_type", event.target.value)
              }
            >
              <option value="">All types</option>
              {requestTypes.filter((value) => ["AIRPORT_PICKUP", "AIRPORT_DROPOFF", "GUEST_TRANSFER", "SUPPLIER_PICKUP", "BRANCH_TRANSFER"].includes(value)).map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label>
            Assignment
            <select
              value={filters.assignment}
              onChange={(event) =>
                changeFilter("assignment", event.target.value)
              }
            >
              <option value="all">All assignments</option>
              <option value="unassigned">Unassigned</option>
              <option value="assigned">Assigned</option>
            </select>
          </label>
          <label>
            Scheduled date
            <input
              value={filters.scheduled_date}
              onChange={(event) =>
                changeFilter("scheduled_date", event.target.value)
              }
              type="date"
            />
          </label>
          <button
            type="button"
            className="reset-filter-button btn-filter"
            onClick={resetFilters}
          >
            Reset Filters
          </button>
        </div>
      )}
    </div>
  );
  return (
    <section
      className={`transport-page transport-page--workspace${tab === "Calendar" ? " transport-page--calendar" : " transport-page--operational"}`}
    >
      <div className="transport-header d-flex align-items-start justify-content-between gap-3">
        <div>
          <p className="breadcrumb text-secondary small mb-1">
            Operations / Transport Requests
          </p>
          <h1 className="mb-1">Transport Requests</h1>
        </div>
      </div>
      <div className="request-toolbar d-flex align-items-end justify-content-between">
        <div
          className="nav nav-pills transport-tabs"
          role="tablist"
          aria-label="Transport request views"
        >
          {tabs.map((item) => {
            const count = tabCount(item, summary);
            return (
              <button
                role="tab"
                aria-selected={tab === item}
                className={`nav-link${tab === item ? " active" : ""}`}
                key={item}
                onClick={() => {
                  setTab(item);
                  setPageNumber(1);
                  setPage(null);
                  setState("loading");
                }}
              >
                {item}
                {typeof count === "number" && (
                  <span className="tab-count">{count}</span>
                )}
              </button>
            );
          })}
        </div>
      </div>
      <div
        className={`transport-tab-panel d-flex flex-column w-100 transport-tab-panel--${tab.toLowerCase().replaceAll(" ", "-")}`}
        role="tabpanel"
      >
        {tab === "Calendar" ? (
          <>
            <CalendarView onViewRequest={setDrawerRequestId} />
            {drawerRequestId && (
              <RequestDetailsDrawer
                requestId={drawerRequestId}
                mode="readOnly"
                onClose={() => setDrawerRequestId(null)}
              />
            )}
          </>
        ) : tab === "Active Trips" || tab === "Completed" ? (
          <ExecutionTripsView
            scope={tab === "Active Trips" ? "active" : "completed"}
            summary={summary}
          />
        ) : (
          <>
            {state === "loading" && !page && (
              <div className="state-card card text-center border-0">
                <LoadingIndicator
                  variant="card"
                  message="Loading transport requests…"
                />
              </div>
            )}
            {state === "error" && (
              <div
                role="alert"
                className="state-card card text-center border-0 text-danger"
              >
                Unable to load transport requests. Try refreshing.
              </div>
            )}
            {successMessage && (
              <div className="message message--success" role="status">
                <span>{successMessage}</span>{" "}
                <Link to="/dispatch-board">Open Dispatch Board</Link>
              </div>
            )}
            {page && (
              <div
                className={`request-workspace request-workspace--fixed${drawerRequestId ? " request-workspace--drawer-open" : ""}`}
              >
                <div
                  className="request-picker request-picker--scroll"
                  aria-label="Request queue"
                >
                  <div className="panel-title">
                    <strong>
                      {tab === "For Approval"
                        ? "Approval queue"
                        : tab === "Dispatch Queue"
                          ? "Approved dispatch queue"
                          : "Request queue"}
                    </strong>
                    <div className="queue-header-controls d-flex align-items-center gap-2">
                      <span className="queue-count">
                        {page.count} matching request{page.count === 1 ? "" : "s"}
                      </span>
                      {queueFilter}
                    </div>
                  </div>
                  <div className="filter-search-group">
                    <label
                      className="visually-hidden"
                      htmlFor="transport-request-search"
                    >
                      Search requests
                    </label>
                    <input
                      id="transport-request-search"
                      name="search"
                      placeholder="Search requests"
                      value={searchValue}
                      onChange={(event) => updateSearch(event.target.value)}
                    />
                  </div>
                  <div className="request-list-scroll">
                  {page.results.length === 0 ? (
                    <div className="request-picker-empty">
                      <span>No transport requests match your filters.</span>
                      <button
                        type="button"
                        className="btn-filter"
                        onClick={resetFilters}
                      >
                        Reset Filters
                      </button>
                    </div>
                  ) : (
                    page.results.map((item) => (
                      <div
                        key={item.id}
                        className={`request-queue-row${selected?.id === item.id ? " selected" : ""}`}
                      >
                        <button
                          type="button"
                          className={`request-queue-select${selected?.id === item.id ? " selected" : ""}`}
                          onClick={() => choose(item)}
                        >
                          <span className="request-queue-primary">
                            <strong id={`request-reference-${item.id}`}>
                              {item.request_number}
                            </strong>
                            <span>{label(item.request_type)}</span>
                            <span className="request-queue-indicators">
                              <WorkflowStatusBadge value={item.status} />
                            </span>
                          </span>
                          <span className="request-queue-secondary">
                            <span>
                              {item.requester_name} ·{" "}
                              {label(item.source_system)}
                            </span>
                            <span>
                              {item.pickup_name} → {item.destination_name}
                            </span>
                            <time>
                              {new Date(
                                item.scheduled_pickup_at,
                              ).toLocaleString()}
                            </time>
                          </span>
                        </button>
                        <div className="request-queue-actions">
                          <button
                            type="button"
                            className="request-queue-menu-toggle"
                            aria-label="More options"
                            aria-describedby={`request-reference-${item.id}`}
                            aria-haspopup="menu"
                            aria-expanded={queueMenuId === item.id}
                            onClick={() =>
                              setQueueMenuId((current) =>
                                current === item.id ? null : item.id,
                              )
                            }
                            onKeyDown={(event) => {
                              if (event.key === "Escape") setQueueMenuId(null);
                            }}
                          >
                            ⋮
                          </button>
                          {queueMenuId === item.id && (
                            <div
                              className="request-queue-menu dropdown-menu show"
                              role="menu"
                            >
                              <button
                                type="button"
                                className="dropdown-item"
                                role="menuitem"
                                onClick={() => viewDetails(item)}
                              >
                                View details
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                  </div>
                  {page.count > 0 && (
                    <nav className="request-pagination" aria-label="Request pages">
                      <span>
                        Showing {(pageNumber - 1) * 15 + 1}–
                        {Math.min(pageNumber * 15, page.count)} of {page.count}
                      </span>
                      <div>
                        <button
                          type="button"
                          className="btn-filter"
                          disabled={!page.previous}
                          onClick={() =>
                            setPageNumber((current) => Math.max(1, current - 1))
                          }
                        >
                          Previous
                        </button>
                        <span>
                          Page {pageNumber} of {Math.max(1, Math.ceil(page.count / 15))}
                        </span>
                        <button
                          type="button"
                          className="btn-filter"
                          disabled={!page.next}
                          onClick={() => setPageNumber((current) => current + 1)}
                        >
                          Next
                        </button>
                      </div>
                    </nav>
                  )}
                </div>
                <div
                  className="request-right-workspace"
                  aria-label="Request workspace"
                >
                  <WorkflowKpiStrip summary={summary} />
                  <div className="map-side" aria-label="Request map">
                    <RequestMap
                      request={selected}
                      route={selectedRoute?.data}
                      routeState={selectedRoute?.state ?? "idle"}
                    />
                    {selected && !summaryVisible && (
                      <button
                        type="button"
                        className="selected-summary-restore btn btn-sm"
                        onClick={() => setSummaryVisible(true)}
                      >
                        Request info
                      </button>
                    )}
                    {selected && summaryVisible && (
                      <article className="selected-summary">
                        <button
                          type="button"
                          className="selected-summary-close btn-close"
                          aria-label="Close request information"
                          onClick={() => setSummaryVisible(false)}
                        >
                          ×
                        </button>
                        <header>
                          <div>
                            <strong>{selected.requester_name}</strong>
                            <small>{selected.request_number}</small>
                          </div>
                          <PriorityChip value={selected.priority} />
                        </header>
                        <dl>
                          <div>
                            <dt>Schedule</dt>
                            <dd>
                              {new Date(
                                selected.scheduled_pickup_at,
                              ).toLocaleString()}
                            </dd>
                          </div>
                          <div>
                            <dt>
                              {selected.request_category ===
                              "DELIVERY_LOGISTICS"
                                ? "Load"
                                : "Passengers"}
                            </dt>
                            <dd>
                              {selected.request_category ===
                              "DELIVERY_LOGISTICS"
                                ? selected.load_description
                                : selected.passenger_count}
                            </dd>
                          </div>
                          <div>
                            <dt>Status</dt>
                            <dd>
                              <WorkflowStatusBadge value={selected.status} />
                            </dd>
                          </div>
                          <div>
                            <dt>Vehicle</dt>
                            <dd>
                              {selectedAssignedVehicle?.display_name ??
                                "Unassigned"}
                            </dd>
                          </div>
                          <div>
                            <dt>Distance / ETA</dt>
                            <dd>
                              {selectedRoute?.state === "ready" &&
                              selectedRoute.data
                                ? distanceLabel(selectedRoute.data) +
                                  " · " +
                                  durationLabel(selectedRoute.data)
                                : selectedRoute?.state === "loading"
                                  ? "Calculating route…"
                                  : selectedRoute?.state === "error"
                                    ? "Route unavailable"
                                    : "—"}
                            </dd>
                          </div>
                          <div>
                            <dt>Traffic delay</dt>
                            <dd>
                              {selectedRoute?.state === "ready" &&
                              selectedRoute.data ? (
                                <>
                                  {selectedRoute.data.traffic_delay_seconds >
                                    0 && (
                                    <span>
                                      {delayLabel(selectedRoute.data)}
                                    </span>
                                  )}
                                  <small className="live-traffic-context">
                                    Live traffic
                                  </small>
                                </>
                              ) : (
                                "—"
                              )}
                            </dd>
                          </div>
                        </dl>
                      </article>
                    )}
                  </div>
                  <SelectedRequestOverview
                    request={selected}
                    route={selectedRoute?.data}
                    routeState={selectedRoute?.state ?? "idle"}
                    onViewDetails={() => {
                      if (selected) viewDetails(selected);
                    }}
                  />
                  {drawerRequestId && (
                    <RequestDetailsDrawer
                      requestId={drawerRequestId}
                      mode={
                        tab === "For Approval"
                          ? "review"
                          : tab === "Dispatch Queue"
                            ? "dispatchPreparation"
                            : "readOnly"
                      }
                      route={
                        drawerRequestId === selected?.id
                          ? selectedRoute?.data
                          : null
                      }
                      onRequestChanged={(updated) => {
                        if (
                          tab === "For Approval" &&
                          updated.status !== "FOR_APPROVAL"
                        ) {
                          setDrawerRequestId(null);
                        }
                        if (updated.status === "READY_FOR_DISPATCH") {
                          setSuccessMessage(
                            "Request prepared for dispatch and is now available on the Dispatch Board.",
                          );
                          if (tab === "Dispatch Queue") setDrawerRequestId(null);
                        }
                        void load();
                      }}
                      onClose={() => setDrawerRequestId(null)}
                    />
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
