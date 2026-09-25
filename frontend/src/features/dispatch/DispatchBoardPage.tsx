import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import LoadingIndicator from "../../components/common/LoadingIndicator";
import {
  StatusBadge,
  dispatchStatusTone,
} from "../../components/common/StatusBadge";
import CandidateTable, { ExclusionsPanel, FuelAdvisory } from "./CandidateTable";
import GisPreview from "./GisPreview";
import SmartConsolidation from "./SmartConsolidation";
import type {
  TransportRequestListItem,
  TransportRoute,
} from "../transport-requests/types";
import {
  analyzeConsolidation,
  confirmConsolidation,
  confirmDispatchAssignment,
  getRecommendationRoute,
  getDispatchBoard,
  prepareConsolidation,
  runDispatchOptimization,
  type DispatchAssignment,
  type DispatchBoardData,
  type ConsolidationResponse,
  type DispatchPlan,
  type Recommendation,
  type RecommendationResponse,
} from "../../services/dispatch";
import { humanize as label } from "../../utils/text";

const duration = (seconds: number | null) =>
  seconds === null ? "Unavailable" : `${Math.ceil(seconds / 60)} min`;
const distance = (meters: number | null) =>
  meters === null
    ? "Unavailable"
    : meters >= 1000
      ? `${(meters / 1000).toFixed(1)} km`
      : `${meters} m`;
const dateTime = (value: string) => new Date(value).toLocaleString();
const CONFIRMED_ASSIGNMENTS_PAGE_SIZE = 15;
const codingLabels = {
  CLEAR: "Clear", RESTRICTED: "Number Coding", EXEMPT: "Verified Exempt",
  SUSPENDED: "Coding Suspended", UNKNOWN: "Needs Verification",
} as const;

function Metric({
  name,
  value,
  detail,
}: {
  name: string;
  value: string;
  detail?: string;
}) {
  return (
    <div>
      <dt>{name}</dt>
      <dd>
        {value}
        {detail && <small>{detail}</small>}
      </dd>
    </div>
  );
}

export default function DispatchBoardPage() {
  const [boardView, setBoardView] = useState<"queue" | "confirmed">("queue");
  const [data, setData] = useState<DispatchBoardData | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [selectedId, setSelectedId] = useState("");
  const [optimization, setOptimization] =
    useState<RecommendationResponse | null>(null);
  const [optimizing, setOptimizing] = useState(false);
  const [error, setError] = useState("");
  const [manual, setManual] = useState(false);
  const [driverId, setDriverId] = useState("");
  const [vehicleId, setVehicleId] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [workspaceTab, setWorkspaceTab] = useState<
    "recommendation" | "candidates" | "exclusions"
  >("recommendation");
  const [confirmationOpen, setConfirmationOpen] = useState(false);
  const [confirmationToken, setConfirmationToken] = useState("");
  const [selectedAssignmentId, setSelectedAssignmentId] = useState<
    number | null
  >(null);
  const [confirmedPage, setConfirmedPage] = useState(1);
  const [route, setRoute] = useState<TransportRoute | null>(null);
  const [plannedRoute, setPlannedRoute] = useState<TransportRoute | null>(null);
  const [recommendedVehiclePosition, setRecommendedVehiclePosition] = useState<{
    latitude: number;
    longitude: number;
    positionStatus: "CURRENT" | "STALE";
  } | null>(null);
  const [routeState, setRouteState] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [consolidation, setConsolidation] =
    useState<ConsolidationResponse | null>(null);
  const [consolidationPlan, setConsolidationPlan] =
    useState<DispatchPlan | null>(null);
  const [analyzingConsolidation, setAnalyzingConsolidation] = useState(false);
  const optimizationSequence = useRef(0);
  const consolidationSequence = useRef(0);
  const confirmTriggerRef = useRef<HTMLButtonElement>(null);
  const confirmCloseRef = useRef<HTMLButtonElement>(null);
  const attemptedAutomatic = useRef(new Set<string>());
  const accept = useCallback((result: DispatchBoardData) => {
    const assignedIds = new Set(
      result.assignments.map((item) => item.transport_request_id),
    );
    const requests = result.requests.filter(
      (item) =>
        item.status === "READY_FOR_DISPATCH" && !assignedIds.has(item.id),
    );
    setData({ ...result, requests });
    setSelectedId((current) =>
      requests.some((item) => item.id === current)
        ? current
        : (requests[0]?.id ?? ""),
    );
    setSelectedAssignmentId((current) =>
      result.assignments.some((item) => item.id === current) ? current : null,
    );
    setState("ready");
  }, []);
  const reload = async () => {
    setState("loading");
    try {
      accept(await getDispatchBoard());
    } catch {
      setState("error");
    }
  };
  useEffect(() => {
    const controller = new AbortController();
    getDispatchBoard(controller.signal)
      .then(accept)
      .catch((cause) => {
        if (!(cause instanceof DOMException && cause.name === "AbortError"))
          setState("error");
      });
    return () => controller.abort();
  }, [accept]);
  useEffect(() => {
    const timer = window.setInterval(() => {
      void getDispatchBoard()
        .then(accept)
        .catch(() => undefined);
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [accept]);
  const selected = useMemo(
    () => data?.requests.find((item) => item.id === selectedId) ?? null,
    [data, selectedId],
  );
  const assignment = useMemo(
    () =>
      data?.assignments.find(
        (item) => item.transport_request_id === selectedId,
      ),
    [data, selectedId],
  );
  const selectedConfirmedAssignment = useMemo(
    () => data?.assignments.find((item) => item.id === selectedAssignmentId),
    [data, selectedAssignmentId],
  );
  const confirmedPageCount = Math.max(
    1,
    Math.ceil(
      (data?.assignments.length ?? 0) / CONFIRMED_ASSIGNMENTS_PAGE_SIZE,
    ),
  );
  const confirmedAssignments = useMemo(() => {
    const start = (confirmedPage - 1) * CONFIRMED_ASSIGNMENTS_PAGE_SIZE;
    return (
      data?.assignments.slice(start, start + CONFIRMED_ASSIGNMENTS_PAGE_SIZE) ??
      []
    );
  }, [confirmedPage, data]);
  useEffect(() => {
    setConfirmedPage((current) => Math.min(current, confirmedPageCount));
  }, [confirmedPageCount]);
  const recommendation = useMemo(() => {
    const item = optimization?.recommendations.find(
      (item) => item.transport_request_id === selectedId,
    );
    const fingerprint = data?.recommendation_fingerprints?.[selectedId];
    return item && item.planning_fingerprint === fingerprint ? item : undefined;
  }, [data, optimization, selectedId]);
  useEffect(() => {
    if (!confirmationOpen) return;
    confirmCloseRef.current?.focus();
    const trigger = confirmTriggerRef.current;
    return () => {
      if (trigger?.isConnected) trigger.focus();
    };
  }, [confirmationOpen]);
  useEffect(() => {
    if (!confirmationOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) setConfirmationOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [busy, confirmationOpen]);
  const attention = useMemo(
    () =>
      optimization?.unassigned.find(
        (item) => item.transport_request_id === selectedId,
      ),
    [optimization, selectedId],
  );
  const comparisons = useMemo(
    () => optimization?.candidate_comparison?.[selectedId] ?? [],
    [optimization, selectedId],
  );
  const exclusions = useMemo(
    () => optimization?.excluded_candidates?.[selectedId] ?? [],
    [optimization, selectedId],
  );
  useEffect(() => setWorkspaceTab("recommendation"), [selectedId]);
  const optimizeRequest = useCallback(
    async (requestId: string, signal?: AbortSignal) => {
      const sequence = ++optimizationSequence.current;
      setOptimizing(true);
      setOptimization(null);
      setError("");
      try {
        const result = await runDispatchOptimization(requestId, signal);
        if (sequence === optimizationSequence.current && !signal?.aborted)
          setOptimization(result);
      } catch (cause) {
        if (
          sequence === optimizationSequence.current &&
          !(cause instanceof DOMException && cause.name === "AbortError")
        )
          setError("Unable to compute recommendation.");
      } finally {
        if (sequence === optimizationSequence.current && !signal?.aborted)
          setOptimizing(false);
      }
    },
    [],
  );
  useEffect(() => {
    const fingerprint = selected
      ? data?.recommendation_fingerprints?.[selected.id]
      : undefined;
    if (
      !selected ||
      selected.status !== "READY_FOR_DISPATCH" ||
      assignment ||
      !fingerprint
    )
      return;
    const attemptKey = `${selected.id}:${fingerprint}`;
    if (attemptedAutomatic.current.has(attemptKey)) return;
    attemptedAutomatic.current.add(attemptKey);
    const controller = new AbortController();
    const timer = window.setTimeout(
      () => void optimizeRequest(selected.id, controller.signal),
      0,
    );
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [assignment, data, selected, optimizeRequest]);
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      if (!selected || !recommendation) {
        setRoute(null);
        setPlannedRoute(null);
        setRecommendedVehiclePosition(null);
        setRouteState("idle");
        return;
      }
      setRouteState("loading");
      getRecommendationRoute(recommendation, controller.signal)
        .then(({ route: value }) => {
          setRoute(value.route ? { request_id: selected.id, ...value.route } : null);
          setPlannedRoute(value.planned_route ? { request_id: selected.id, ...value.planned_route } : null);
          setRecommendedVehiclePosition(
            value.vehicle_position && value.position_state !== "UNAVAILABLE"
              ? {
                  latitude: value.vehicle_position.latitude,
                  longitude: value.vehicle_position.longitude,
                  positionStatus: value.position_state,
                }
              : null,
          );
          setRouteState(value.route && value.planned_route ? "ready" : "error");
        })
        .catch((cause) => {
          if (!(cause instanceof DOMException && cause.name === "AbortError")) {
            setRoute(null);
            setPlannedRoute(null);
            setRecommendedVehiclePosition(null);
            setRouteState("error");
          }
        });
    }, 0);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [recommendation, selected]);
  const analyze = useCallback(
    async (requestId: string, signal?: AbortSignal) => {
      const sequence = ++consolidationSequence.current;
      setAnalyzingConsolidation(true);
      setConsolidation(null);
      try {
        const result = await analyzeConsolidation(requestId, signal);
        if (sequence === consolidationSequence.current && !signal?.aborted)
          setConsolidation(result);
      } catch (cause) {
        if (
          sequence === consolidationSequence.current &&
          !(cause instanceof DOMException && cause.name === "AbortError")
        )
          setConsolidation(null);
      } finally {
        if (sequence === consolidationSequence.current && !signal?.aborted)
          setAnalyzingConsolidation(false);
      }
    },
    [],
  );
  useEffect(() => {
    if (
      !selected ||
      selected.request_category !== "DELIVERY_LOGISTICS" ||
      !recommendation ||
      assignment
    )
      return;
    const controller = new AbortController();
    const timer = window.setTimeout(
      () => void analyze(selected.id, controller.signal),
      0,
    );
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [analyze, assignment, recommendation, selected]);
  const visibleRequests = data?.requests ?? [];
  const optimize = () => {
    if (selected && !assignment && selected.status === "READY_FOR_DISPATCH")
      void optimizeRequest(selected.id);
  };
  const confirm = async () => {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      let saved: DispatchAssignment;
      if (manual) {
        saved = await confirmDispatchAssignment({
          transport_request_id: selected.id,
          vehicle_id: Number(vehicleId),
          driver_id: Number(driverId),
          selection_mode: "MANUAL",
          override_reason: reason,
        });
      } else if (recommendation) {
        saved = await confirmDispatchAssignment({
          transport_request_id: selected.id,
          vehicle_id: recommendation.recommended_vehicle.id,
          driver_id: recommendation.recommended_driver.id,
          selection_mode: "OPTIMIZED",
          recommendation_token: recommendation.recommendation_token,
        });
      } else {
        return;
      }
      optimizationSequence.current += 1;
      setOptimizing(false);
      setOptimization(null);
      setSelectedAssignmentId(saved.id);
      setData((current) =>
        current
          ? {
              ...current,
              requests: current.requests.filter(
                (item) => item.id !== saved.transport_request_id,
              ),
              assignments: [
                saved,
                ...current.assignments.filter(
                  (item) =>
                    item.transport_request_id !== saved.transport_request_id,
                ),
              ],
            }
          : current,
      );
      setSelectedId("");
      setManual(false);
      setConfirmationOpen(false);
      await reload();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Unable to confirm assignment.",
      );
    } finally {
      setBusy(false);
    }
  };
  const acceptConsolidation = async () => {
    const suggestion = consolidation?.recommendation;
    if (!suggestion) return;
    setBusy(true);
    setError("");
    try {
      setConsolidationPlan(
        await confirmConsolidation(suggestion.recommendation_token),
      );
      setConsolidation(null);
      await reload();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Unable to confirm consolidation.",
      );
    } finally {
      setBusy(false);
    }
  };
  const preparePlan = async () => {
    if (!consolidationPlan) return;
    setBusy(true);
    setError("");
    try {
      setConsolidationPlan(await prepareConsolidation(consolidationPlan.id));
      await reload();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Unable to prepare consolidation.",
      );
    } finally {
      setBusy(false);
    }
  };
  const cards = data
    ? ([
        ["UNASSIGNED", "Ready / Unassigned", data.summary.awaiting_assignment],
        ["ELIGIBLE", "Optimizer Eligible", data.summary.optimizer_eligible],
        ["ATTENTION", "Needs Attention", data.summary.needs_attention],
        ["CONFIRMED", "Confirmed", data.summary.confirmed_assignments],
        ["NO_DRIVER", "No Eligible Driver", data.summary.no_eligible_driver],
        ["NO_GIS", "No GIS Vehicle", data.summary.no_gis_vehicle],
        ["CONFLICT", "Schedule Conflict", data.summary.schedule_conflict],
      ] as const)
    : [];
  return (
    <section className="dispatch-page">
      <div className="dispatch-header d-flex align-items-start justify-content-between gap-3">
        <div>
          <p className="breadcrumb text-secondary small mb-1">
            Operations / Dispatch Board
          </p>
          <h1 className="mb-1">Dispatch Board</h1>
        </div>
      </div>
      {data && (
        <div className="request-toolbar dispatch-view-toolbar">
          <div
            className="nav nav-pills transport-tabs"
            role="tablist"
            aria-label="Dispatch Board views"
          >
            <button
              type="button"
              role="tab"
              aria-selected={boardView === "queue"}
              className={`nav-link${boardView === "queue" ? " active" : ""}`}
              onClick={() => setBoardView("queue")}
            >
              Dispatch Queue{" "}
              <span className="tab-count">
                {data.summary.awaiting_assignment}
              </span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={boardView === "confirmed"}
              className={`nav-link${boardView === "confirmed" ? " active" : ""}`}
              onClick={() => setBoardView("confirmed")}
            >
              Confirmed Assignments{" "}
              <span className="tab-count">
                {data.summary.confirmed_assignments}
              </span>
            </button>
          </div>
        </div>
      )}
      {data && boardView === "queue" && (
        <div className="dispatch-kpis" aria-label="Dispatch attention summary">
          {cards.map(([key, name, value]) => (
            <article
              key={key}
              data-kpi={key}
              data-testid={`dispatch-kpi-${key.toLowerCase()}`}
            >
              <strong>{value}</strong>
              <span>{name}</span>
            </article>
          ))}
        </div>
      )}
      {state === "loading" && (
        <LoadingIndicator variant="card" message="Loading dispatch board…" />
      )}
      {state === "error" && <p role="alert">Unable to load Dispatch Board.</p>}
      {state === "ready" && data && boardView === "queue" && (
        <div className="dispatch-workspace">
          <section className="dispatch-queue">
            <header>
              <strong>Dispatch Request Queue</strong>
              <span>{visibleRequests.length} requests</span>
            </header>
            <div
              className="dispatch-queue-list"
              data-testid="dispatch-request-scroll"
              role="region"
              aria-label="Dispatch requests"
              tabIndex={0}
            >
              {visibleRequests.length === 0 ? (
                <p className="dispatch-empty">
                  No requests in this operational bucket.
                </p>
              ) : (
                visibleRequests.map((item) => (
                  <RequestRow
                    key={item.id}
                    item={item}
                    selected={item.id === selectedId}
                    assigned={data.assignments.some(
                      (entry) => entry.transport_request_id === item.id,
                    )}
                    executionStatus={
                      data.assignments.find(
                        (entry) => entry.transport_request_id === item.id,
                      )?.execution_status
                    }
                    attention={
                      optimization?.unassigned.find(
                        (entry) => entry.transport_request_id === item.id,
                      )?.reason
                    }
                    onClick={() => {
                      optimizationSequence.current += 1;
                      consolidationSequence.current += 1;
                      setOptimizing(false);
                      setAnalyzingConsolidation(false);
                      setOptimization(null);
                      setConsolidation(null);
                      setConsolidationPlan(null);
                      setSelectedAssignmentId(null);
                      setSelectedId(item.id);
                      setConfirmationOpen(false);
                      setManual(false);
                      setError("");
                    }}
                  />
                ))
              )}
            </div>
          </section>
          <section className="dispatch-detail dispatch-recommendation-workspace">
            <header className="dispatch-panel-header">
              <div>
                <strong>Recommendation Workspace</strong>
                <small>Google OR-Tools · TomTom</small>
              </div>
              <button
                type="button"
                className="btn-filter"
                onClick={optimize}
                disabled={
                  optimizing ||
                  !selected ||
                  selected.status !== "READY_FOR_DISPATCH" ||
                  Boolean(assignment)
                }
              >
                {optimizing ? "Calculating…" : "Recompute Recommendation"}
              </button>
            </header>
            <div className="dispatch-detail-body">
              <nav
                className="dispatch-workspace-tabs"
                aria-label="Recommendation workspace views"
              >
                {(
                  [
                    ["recommendation", "Recommendation"],
                    ["candidates", `Candidates (${comparisons.length})`],
                    ["exclusions", `Exclusions (${exclusions.length})`],
                  ] as const
                ).map(([tab, text]) => (
                  <button
                    type="button"
                    role="tab"
                    aria-selected={workspaceTab === tab}
                    className={workspaceTab === tab ? "active" : ""}
                    key={tab}
                    onClick={() => setWorkspaceTab(tab)}
                  >
                    {text}
                  </button>
                ))}
              </nav>
              <div className="dispatch-center-scroll">
                {selected && (
                  <section
                    className="dispatch-request-context"
                    aria-label="Selected Request Context"
                  >
                    <strong>Selected Request Context</strong>
                    <span>
                      {selected.request_number} · {label(selected.request_type)}
                    </span>
                    <span>
                      {selected.pickup_name} → {selected.destination_name}
                    </span>
                    <small>{dateTime(selected.scheduled_pickup_at)}</small>
                  </section>
                )}
                {!selected ? (
                  <p className="dispatch-empty">Select a ready request.</p>
                ) : optimizing ? (
                  <LoadingIndicator
                    variant="card"
                    message="Calculating recommendation…"
                  />
                ) : recommendation && workspaceTab === "candidates" ? (
                  <CandidateTable
                    items={comparisons}
                    limited={optimization?.comparison_scope?.limited ?? false}
                  />
                ) : recommendation && workspaceTab === "exclusions" ? (
                  <ExclusionsPanel items={exclusions} />
                ) : recommendation ? (
                  <>
                    <p className="dispatch-state-note">
                      Recommendation ready
                      {optimization?.generated_at
                        ? ` · updated ${dateTime(optimization.generated_at)}`
                        : ""}
                    </p>
                    <h2>{recommendation.request_number}</h2>
                    <p className="dispatch-explanation">
                      Selected by Google OR-Tools from feasible Driver/Vehicle
                      candidates using TomTom traffic-aware travel time.
                    </p>
                    <p className="dispatch-recommendation-only">
                      Recommendation only — requires dispatcher confirmation.
                    </p>
                    <dl>
                      <Metric
                        name="Recommended Driver"
                        value={recommendation.recommended_driver.full_name}
                        detail={`${recommendation.recommended_driver.driver_code} · ELIGIBLE`}
                      />
                      <Metric
                        name="Recommended Vehicle"
                        value={recommendation.recommended_vehicle.display_name}
                        detail={recommendation.recommended_vehicle.plate_number}
                      />
                      <Metric
                        name="Travel time"
                        value={duration(recommendation.travel_time_seconds)}
                      />
                      <Metric
                        name="Distance"
                        value={distance(recommendation.distance_meters)}
                      />
                    </dl>
                    <FuelAdvisory estimate={recommendation.fuel_estimate} />
                    {recommendation.airport_pickup_timing && (
                      <section className="dispatch-why">
                        <h3>Airport pickup timing</h3>
                        <p>{recommendation.airport_pickup_timing.message}</p>
                        {recommendation.airport_pickup_timing
                          .recommended_departure_at && (
                          <p>
                            Recommended departure:{" "}
                            {dateTime(
                              recommendation.airport_pickup_timing
                                .recommended_departure_at,
                            )}
                            {recommendation.airport_pickup_timing.arrival_basis
                              ? ` · ${label(recommendation.airport_pickup_timing.arrival_basis)} arrival basis`
                              : ""}
                          </p>
                        )}
                      </section>
                    )}
                    <section className="dispatch-why">
                      <h3>Why recommended</h3>
                      <ul>
                        {(recommendation.explanation ?? []).map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </section>
                    <DispatchChecks summary={data.summary} />
                    {recommendation.gis_preview && (
                      <GisPreview
                        recommendation={recommendation}
                        request={selected}
                        route={consolidation?.recommendation ? null : route}
                        plannedRoute={consolidation?.recommendation ? null : plannedRoute}
                        vehiclePosition={
                          consolidation?.recommendation ? null : recommendedVehiclePosition
                        }
                        routeState={routeState}
                        stops={consolidation?.recommendation?.route.stops}
                      />
                    )}
                    <SmartConsolidation
                      currentRequestNumber={selected.request_number}
                      loading={analyzingConsolidation}
                      result={consolidation}
                      plan={consolidationPlan}
                      busy={busy}
                      onKeepSeparate={() => setConsolidation(null)}
                      onConfirm={() => void acceptConsolidation()}
                      onPrepare={() => void preparePlan()}
                    />
                  </>
                ) : attention ? (
                  <>
                    <div className="dispatch-attention">
                      <strong>Needs Attention</strong>
                      <p>No valid recommendation is currently available.</p>
                      <small>{attention.reason}</small>
                    </div>
                    <DispatchChecks summary={data.summary} />
                  </>
                ) : (
                  <>
                    <div className="dispatch-attention dispatch-attention--neutral">
                      <strong>Recommendation Unavailable</strong>
                      <p>No valid recommendation is currently available.</p>
                      <small>Use Recompute Recommendation to retry.</small>
                    </div>
                    <DispatchChecks summary={data.summary} />
                  </>
                )}
              </div>
            </div>
            {selected && (
              <div className="dispatch-actions-bar">
                {!assignment && recommendation && !manual && (
                  <button
                    ref={confirmTriggerRef}
                    className="btn-confirm"
                    onClick={() => {
                      setError("");
                      setConfirmationToken(recommendation.recommendation_token);
                      setConfirmationOpen(true);
                    }}
                    disabled={busy}
                  >
                    Confirm Recommendation
                  </button>
                )}
                {selected.status === "READY_FOR_DISPATCH" && !assignment && (
                  <button
                    className="btn-action--filled"
                    onClick={() => setManual((value) => !value)}
                  >
                    {manual ? "Cancel Manual Override" : "Manual Override"}
                  </button>
                )}
                {manual &&
                  selected.status === "READY_FOR_DISPATCH" &&
                  !assignment && (
                    <div className="dispatch-manual">
                      <label>
                        Eligible Driver
                        <select
                          value={driverId}
                          onChange={(event) => setDriverId(event.target.value)}
                        >
                          <option value="">Select driver</option>
                          {(
                            data.manual_candidates?.[selected.id]?.drivers ??
                            data.eligible_drivers
                          ).map((driver) => (
                            <option value={driver.id} key={driver.id}>
                              {driver.full_name} · {driver.driver_code} ·
                              ELIGIBLE
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Valid Vehicle
                        <select
                          value={vehicleId}
                          onChange={(event) => setVehicleId(event.target.value)}
                        >
                          <option value="">Select vehicle</option>
                          {(
                            data.manual_candidates?.[selected.id]?.vehicles ??
                            data.active_vehicles
                          ).map((vehicle) => (
                            <option
                              value={vehicle.id}
                              key={vehicle.id}
                              disabled={vehicle.number_coding?.status === "RESTRICTED" || vehicle.number_coding?.status === "UNKNOWN"}
                            >
                              {vehicle.display_name} · {vehicle.plate_number}
                              {vehicle.number_coding ? ` · ${codingLabels[vehicle.number_coding.status]} · ${vehicle.number_coding.reason}` : ""}
                              {vehicle.current_location_available
                                ? ""
                                : " · Current location unavailable — manual assignment only"}
                            </option>
                          ))}
                        </select>
                        {vehicleId && (() => {
                          const vehicle = (data.manual_candidates?.[selected.id]?.vehicles ?? []).find((item) => String(item.id) === vehicleId);
                          return vehicle?.number_coding ? <small className={`dispatch-coding dispatch-coding--${vehicle.number_coding.status.toLowerCase()}`}>{codingLabels[vehicle.number_coding.status]} · {vehicle.number_coding.reason}</small> : null;
                        })()}
                      </label>
                      <label>
                        Override reason
                        <textarea
                          value={reason}
                          onChange={(event) => setReason(event.target.value)}
                          placeholder="Explain why another valid Driver/Vehicle pair is being selected."
                        />
                      </label>
                      <button
                        className="btn-confirm"
                        disabled={
                          busy || !driverId || !vehicleId || !reason.trim()
                        }
                        onClick={confirm}
                      >
                        Confirm Manual Assignment
                      </button>
                    </div>
                  )}
              </div>
            )}
          </section>
          <section className="dispatch-review" aria-label="Assignment Review">
            <header className="dispatch-panel-header">
              <strong>Assignment Review</strong>
            </header>
            <div className="dispatch-review-scroll">
              {!selected ? (
                <p className="dispatch-empty">Waiting for request selection.</p>
              ) : assignment ? (
                <>
                  <Confirmed assignment={assignment} />
                  <Audit events={data.assignment_audit?.[selected.id] ?? []} />
                </>
              ) : recommendation ? (
                <>
                  <p className="dispatch-state-note">
                    Pending dispatcher confirmation
                  </p>
                  <div className="dispatch-confirmed">
                    <h2>Proposed Assignment</h2>
                    <dl>
                      <Metric
                        name="Request"
                        value={selected.request_number}
                        detail={`${selected.pickup_name} → ${selected.destination_name}`}
                      />
                      <Metric
                        name="Driver"
                        value={recommendation.recommended_driver.full_name}
                        detail={recommendation.recommended_driver.driver_code}
                      />
                      <Metric
                        name="Vehicle"
                        value={recommendation.recommended_vehicle.display_name}
                        detail={recommendation.recommended_vehicle.plate_number}
                      />
                      <Metric
                        name="Schedule"
                        value={dateTime(selected.scheduled_pickup_at)}
                      />
                    </dl>
                  </div>
                  <Schedule context={recommendation.schedule_context} />
                </>
              ) : (
                <div className="dispatch-review-empty">
                  <strong>No assignment selected</strong>
                  <p>
                    Review a valid optimizer recommendation or manual override
                    before confirming the assignment.
                  </p>
                </div>
              )}
            </div>
          </section>
        </div>
      )}
      {state === "ready" &&
        data &&
        boardView === "confirmed" &&
        (data.assignments.length === 0 ? (
          <div className="dispatch-confirmed-empty">
            No confirmed assignments yet.
          </div>
        ) : (
          <div
            className={`dispatch-confirmed-view${selectedConfirmedAssignment ? " has-selection" : ""}`}
          >
            <ConfirmedAssignmentsList
              assignments={confirmedAssignments}
              page={confirmedPage}
              pageCount={confirmedPageCount}
              total={data.assignments.length}
              selectedId={selectedAssignmentId}
              onPageChange={setConfirmedPage}
              onSelect={(item) => setSelectedAssignmentId(item.id)}
            />
            {selectedConfirmedAssignment && (
              <aside
                className="dispatch-confirmed-detail"
                aria-label="Confirmed Assignment Details"
              >
                <Confirmed assignment={selectedConfirmedAssignment} />
                <Audit
                  events={
                    data.assignment_audit?.[
                      selectedConfirmedAssignment.transport_request_id
                    ] ?? []
                  }
                />
              </aside>
            )}
          </div>
        ))}
      {confirmationOpen &&
        selected &&
        recommendation &&
        confirmationToken === recommendation.recommendation_token &&
        !manual &&
        !assignment && (
          <div
            className="dispatch-confirm-backdrop"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget && !busy)
                setConfirmationOpen(false);
            }}
          >
            <aside
              className="dispatch-confirm-drawer"
              role="dialog"
              aria-modal="true"
              aria-labelledby="dispatch-confirm-title"
            >
              <header>
                <div>
                  <small>Dispatch recommendation</small>
                  <h2 id="dispatch-confirm-title">Confirm assignment</h2>
                  <span>{selected.request_number}</span>
                </div>
                <button
                  ref={confirmCloseRef}
                  type="button"
                  className="btn-close"
                  aria-label="Close confirmation drawer"
                  onClick={() => setConfirmationOpen(false)}
                  disabled={busy}
                >
                  ×
                </button>
              </header>
              <div className="dispatch-confirm-body">
                <p>
                  Review this recommendation before assigning the driver and
                  vehicle.
                </p>
                <section>
                  <h3>Transport request</h3>
                  <dl>
                    <Metric name="Pickup" value={selected.pickup_name} />
                    <Metric
                      name="Destination"
                      value={selected.destination_name}
                    />
                    <Metric
                      name="Scheduled pickup"
                      value={dateTime(selected.scheduled_pickup_at)}
                    />
                  </dl>
                </section>
                <section>
                  <h3>Recommended assignment</h3>
                  <dl>
                    <Metric
                      name="Driver"
                      value={recommendation.recommended_driver.full_name}
                      detail={recommendation.recommended_driver.driver_code}
                    />
                    <Metric
                      name="Vehicle"
                      value={recommendation.recommended_vehicle.display_name}
                      detail={recommendation.recommended_vehicle.plate_number}
                    />
                    <Metric
                      name="Travel time"
                      value={duration(recommendation.travel_time_seconds)}
                    />
                    <Metric
                      name="Distance"
                      value={distance(recommendation.distance_meters)}
                    />
                  </dl>
                </section>
                <FuelAdvisory estimate={recommendation.fuel_estimate} />
                {error && (
                  <p className="form-error" role="alert">
                    {error}
                  </p>
                )}
              </div>
              <footer>
                <button
                  type="button"
                  className="btn-filter"
                  onClick={() => setConfirmationOpen(false)}
                  disabled={busy}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn-confirm"
                  onClick={() => void confirm()}
                  disabled={busy}
                >
                  {busy ? "Confirming…" : "Confirm Assignment"}
                </button>
              </footer>
            </aside>
          </div>
        )}
    </section>
  );
}
function DispatchChecks({
  summary,
}: {
  summary: DispatchBoardData["summary"];
}) {
  return (
    <section className="dispatch-checks" aria-label="Dispatch Checks">
      <h3>Dispatch Checks</h3>
      <dl>
        <Metric
          name="Driver eligibility"
          value={`${summary.no_eligible_driver} blocked`}
        />
        <Metric
          name="GIS vehicle"
          value={`${summary.no_gis_vehicle} blocked`}
        />
        <Metric
          name="Schedule conflict"
          value={`${summary.schedule_conflict} blocked`}
        />
        <Metric
          name="Number Coding"
          value={`${summary.number_coding_blocked ?? 0} restricted`}
        />
        <Metric
          name="Route feasibility"
          value="Awaiting valid recommendation"
        />
      </dl>
    </section>
  );
}
function RequestRow({
  item,
  selected,
  assigned,
  executionStatus,
  attention,
  onClick,
}: {
  item: TransportRequestListItem;
  selected: boolean;
  assigned: boolean;
  executionStatus?: DispatchAssignment["execution_status"];
  attention?: string;
  onClick: () => void;
}) {
  const statusText =
    executionStatus === "COMPLETED"
      ? "Completed"
      : item.status === "READY_FOR_DISPATCH"
        ? "Ready for Dispatch"
        : assigned
          ? "Confirmed"
          : attention || "Awaiting Assignment";
  return (
    <button
      className={`dispatch-row${selected ? " selected" : ""}`}
      onClick={onClick}
    >
      <div className="dispatch-row-primary">
        <strong>{item.request_number}</strong>
        <span className="dispatch-row-type">{label(item.request_type)}</span>
        <StatusBadge
          status={
            statusText === "Completed"
              ? "completed"
              : statusText === "Confirmed"
                ? "confirmed"
                : statusText === "Ready for Dispatch"
                  ? "ready"
                  : "pending"
          }
          tone={
            statusText === "Completed"
              ? "success"
              : dispatchStatusTone[
                  statusText === "Confirmed"
                    ? "confirmed"
                    : statusText === "Ready for Dispatch"
                      ? "ready"
                      : "pending"
                ]
          }
          label={statusText}
        />
      </div>
      <div className="dispatch-row-secondary">
        <span className="dispatch-row-route">
          {item.pickup_name} → {item.destination_name}
        </span>
        <span className="dispatch-row-time">
          {dateTime(item.scheduled_pickup_at)}
        </span>
      </div>
      <div className="dispatch-row-meta">
        <span>{item.source_system && label(item.source_system)}</span>
        <span>
          {item.request_category === "PASSENGER_TRANSPORT"
            ? `${item.passenger_count} passengers${item.required_vehicle_type ? ` · ${label(item.required_vehicle_type)}` : ""}`
            : ["SUPPLIER_PICKUP", "BRANCH_TRANSFER"].includes(item.request_type)
              ? `${item.load_description || "Supply load"}${item.estimated_weight_kg ? ` · ${item.estimated_weight_kg} kg` : " · weight not recorded"}`
              : item.load_description || "Delivery logistics"}
        </span>
      </div>
    </button>
  );
}
function Schedule({
  context,
}: {
  context: Recommendation["schedule_context"];
}) {
  return (
    <section className="dispatch-schedule">
      <h3>Resource Schedule</h3>
      <p>
        <b>Selected request</b>
        <span>
          {dateTime(context.selected.start)} → {dateTime(context.selected.end)}
        </span>
      </p>
      {(["driver", "vehicle"] as const).map((kind) => (
        <div key={kind}>
          <strong>
            {label(kind)} timeline · {context[kind].status}
          </strong>
          {context[kind].windows.length === 0 ? (
            <small>No overlapping confirmed assignments.</small>
          ) : (
            context[kind].windows.map((window) => (
              <small key={`${kind}-${window.request_number}`}>
                {window.request_number}: {dateTime(window.start)} →{" "}
                {dateTime(window.end)}
              </small>
            ))
          )}
        </div>
      ))}
    </section>
  );
}
function ConfirmedAssignmentsList({
  assignments,
  page,
  pageCount,
  total,
  selectedId,
  onPageChange,
  onSelect,
}: {
  assignments: DispatchAssignment[];
  page: number;
  pageCount: number;
  total: number;
  selectedId: number | null;
  onPageChange: (page: number) => void;
  onSelect: (assignment: DispatchAssignment) => void;
}) {
  const first = (page - 1) * CONFIRMED_ASSIGNMENTS_PAGE_SIZE + 1;
  const last = Math.min(page * CONFIRMED_ASSIGNMENTS_PAGE_SIZE, total);
  return (
    <section
      className="dispatch-confirmed-list"
      aria-label="Confirmed Assignments"
    >
      <header>
        <strong>Confirmed Assignments ({total})</strong>
      </header>
      <div className="dispatch-confirmed-table-wrap">
        <table>
          <thead>
            <tr>
              <th>Request</th>
              <th>Driver</th>
              <th>Vehicle</th>
              <th>Driver Acknowledgement</th>
              <th>Execution Status</th>
              <th>Confirmed At</th>
              <th>
                <span className="visually-hidden">View</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {assignments.map((assignment) => (
              <tr
                key={assignment.id}
                className={assignment.id === selectedId ? "selected" : ""}
                onClick={() => onSelect(assignment)}
              >
                <td>
                  <strong>{assignment.request_number}</strong>
                </td>
                <td>{assignment.driver.full_name}</td>
                <td>{assignment.vehicle.display_name}</td>
                <td>
                  <StatusBadge
                    status={assignment.is_accepted ? "accepted" : "awaiting"}
                    label={
                      assignment.is_accepted
                        ? "Accepted"
                        : "Awaiting Driver Acceptance"
                    }
                    tone={assignment.is_accepted ? "success" : "warning"}
                  />
                </td>
                <td>
                  <StatusBadge
                    status={assignment.execution_status}
                    label={assignment.execution_status_label}
                    tone={
                      assignment.execution_status === "COMPLETED"
                        ? "success"
                        : "info"
                    }
                  />
                </td>
                <td>
                  <time dateTime={assignment.confirmed_at}>
                    {dateTime(assignment.confirmed_at)}
                  </time>
                </td>
                <td>
                  <button type="button" onClick={() => onSelect(assignment)}>
                    View
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pageCount > 1 && (
        <nav
          className="dispatch-pagination"
          aria-label="Confirmed assignments pagination"
        >
          <span>
            Showing {first}–{last} of {total}
          </span>
          <div>
            <button
              type="button"
              disabled={page === 1}
              onClick={() => onPageChange(page - 1)}
            >
              Previous
            </button>
            <span>
              Page {page} of {pageCount}
            </span>
            <button
              type="button"
              disabled={page === pageCount}
              onClick={() => onPageChange(page + 1)}
            >
              Next
            </button>
          </div>
        </nav>
      )}
    </section>
  );
}

function Audit({
  events,
}: {
  events: DispatchBoardData["assignment_audit"][string];
}) {
  return (
    <section className="dispatch-audit">
      <h3>Assignment Audit</h3>
      {events.length === 0 ? (
        <p>No persisted assignment events.</p>
      ) : (
        events.map((event, index) => (
          <article key={`${event.timestamp}-${index}`}>
            <time>{dateTime(event.timestamp)}</time>
            <strong>{label(event.kind)}</strong>
            {event.driver && event.vehicle && (
              <span>
                {event.driver.full_name} + {event.vehicle.display_name}
              </span>
            )}
            <small>
              {event.selection_mode && `${label(event.selection_mode)} · `}by{" "}
              {event.operator}
            </small>
            {event.reason && <small>Reason: {event.reason}</small>}
          </article>
        ))
      )}
    </section>
  );
}
function Confirmed({ assignment }: { assignment: DispatchAssignment }) {
  return (
    <div className="dispatch-confirmed">
      <h2>Confirmed Assignment</h2>
      <dl>
        <Metric name="Request" value={assignment.request_number} />
        <Metric
          name="Driver"
          value={assignment.driver.full_name}
          detail={assignment.driver.driver_code}
        />
        <Metric
          name="Vehicle"
          value={assignment.vehicle.display_name}
          detail={assignment.vehicle.plate_number}
        />
        <Metric name="Confirmed by" value={assignment.confirmed_by} />
        <Metric
          name="Selection source"
          value={label(assignment.selection_mode)}
        />
        <Metric
          name="Driver acknowledgement"
          value={
            assignment.is_accepted
              ? `Accepted${assignment.accepted_at ? ` · ${dateTime(assignment.accepted_at)}` : ""}`
              : "Awaiting Driver Acceptance"
          }
        />
        <Metric
          name="Execution"
          value={
            assignment.execution_status === "COMPLETED" &&
            assignment.completed_at
              ? `Completed · ${dateTime(assignment.completed_at)}`
              : assignment.execution_status_label
          }
        />
        <Metric name="Confirmed at" value={dateTime(assignment.confirmed_at)} />
        {assignment.accepted_at && (
          <Metric name="Accepted at" value={dateTime(assignment.accepted_at)} />
        )}
        <Metric name="Last updated" value={dateTime(assignment.updated_at)} />
      </dl>
      <section className="dispatch-confirmed-schedule">
        <h3>Resource Schedule</h3>
        <p>
          {assignment.driver.full_name} and {assignment.vehicle.display_name}{" "}
          are reserved for {assignment.request_number}.
        </p>
      </section>
    </div>
  );
}
