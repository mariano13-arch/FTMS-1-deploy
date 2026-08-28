import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { getRequestRoute, mutateRequest } from "../transport-requests/api";
import LoadingIndicator from "../../components/common/LoadingIndicator";
import {
  StatusBadge,
  dispatchStatusTone,
} from "../../components/common/StatusBadge";
import CandidateTable from "./CandidateTable";
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
  const [filter, setFilter] = useState("ALL");
  const [tab, setTab] = useState<"recommendation" | "review">("recommendation");
  const [route, setRoute] = useState<TransportRoute | null>(null);
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
  const accept = useCallback((result: DispatchBoardData) => {
    setData(result);
    setSelectedId((current) =>
      result.requests.some((item) => item.id === current)
        ? current
        : (result.requests[0]?.id ?? ""),
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
  const recommendation = useMemo(
    () =>
      optimization?.recommendations.find(
        (item) => item.transport_request_id === selectedId,
      ),
    [optimization, selectedId],
  );
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
          setError(
            cause instanceof Error
              ? cause.message
              : "Unable to run optimization.",
          );
      } finally {
        if (sequence === optimizationSequence.current && !signal?.aborted)
          setOptimizing(false);
      }
    },
    [],
  );
  useEffect(() => {
    if (!selected || selected.status !== "APPROVED" || assignment) return;
    const controller = new AbortController();
    const timer = window.setTimeout(
      () => void optimizeRequest(selected.id, controller.signal),
      0,
    );
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [assignment, selected, optimizeRequest]);
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      if (!selected || !recommendation) {
        setRoute(null);
        setRouteState("idle");
        return;
      }
      setRouteState("loading");
      getRequestRoute(selected.id, controller.signal)
        .then((value) => {
          setRoute(value);
          setRouteState("ready");
        })
        .catch((cause) => {
          if (!(cause instanceof DOMException && cause.name === "AbortError")) {
            setRoute(null);
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
          setError(
            cause instanceof Error
              ? cause.message
              : "Unable to analyze consolidation.",
          );
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
  const visibleRequests = useMemo(
    () =>
      (data?.requests ?? []).filter(
        (item) =>
          filter === "ALL" ||
          (filter === "UNASSIGNED" &&
            !data?.assignments.some(
              (entry) => entry.transport_request_id === item.id,
            )) ||
          (filter === "CONFIRMED" &&
            data?.assignments.some(
              (entry) => entry.transport_request_id === item.id,
            ) &&
            item.status === "APPROVED") ||
          (filter === "READY" && item.status === "READY_FOR_DISPATCH") ||
          (filter === "ATTENTION" &&
            optimization?.unassigned.some(
              (entry) => entry.transport_request_id === item.id,
            )),
      ),
    [data, filter, optimization],
  );
  const optimize = () => {
    if (selected && !assignment && selected.status === "APPROVED")
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
      setData((current) =>
        current
          ? {
              ...current,
              assignments: [
                ...current.assignments.filter(
                  (item) =>
                    item.transport_request_id !== saved.transport_request_id,
                ),
                saved,
              ],
            }
          : current,
      );
      setManual(false);
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
  const prepare = async () => {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      await mutateRequest(selected.id, "prepare-dispatch");
      await reload();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Unable to prepare dispatch.",
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
        [
          "UNASSIGNED",
          "Approved / Unassigned",
          data.summary.awaiting_assignment,
        ],
        ["ELIGIBLE", "Optimizer Eligible", data.summary.optimizer_eligible],
        ["NO_DRIVER", "No Eligible Driver", data.summary.no_eligible_driver],
        ["NO_GIS", "No GIS Vehicle", data.summary.no_gis_vehicle],
        ["CONFLICT", "Schedule Conflict", data.summary.schedule_conflict],
        ["CONFIRMED", "Confirmed", data.summary.confirmed_assignments],
        ["READY", "Ready for Dispatch", data.summary.ready_for_dispatch],
        ["ATTENTION", "Needs Attention", data.summary.needs_attention],
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
        <div className="header-actions d-flex align-items-center gap-2 mt-4">
          <button
            type="button"
            className="btn-filter"
            onClick={optimize}
            disabled={
              optimizing ||
              !selected ||
              selected.status !== "APPROVED" ||
              Boolean(assignment)
            }
          >
            {optimizing ? "Optimizing…" : "Refresh Optimization"}
          </button>
        </div>
      </div>
      {data && (
        <div className="dispatch-kpis" aria-label="Dispatch attention summary">
          {cards.map(([key, name, value]) => (
            <button
              key={key}
              data-filter={key}
              className={`btn-filter${filter === key ? " selected" : ""}`}
              onClick={() =>
                setFilter(
                  key === "UNASSIGNED" ||
                    key === "CONFIRMED" ||
                    key === "READY" ||
                    key === "ATTENTION"
                    ? key
                    : "ALL",
                )
              }
            >
              <strong>{value}</strong>
              <span>{name}</span>
            </button>
          ))}
        </div>
      )}
      {state === "loading" && (
        <LoadingIndicator variant="card" message="Loading dispatch board…" />
      )}
      {state === "error" && <p role="alert">Unable to load Dispatch Board.</p>}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {state === "ready" && data && (
        <div className="dispatch-workspace">
          <section className="dispatch-queue">
            <header>
              <strong>Dispatch Request Queue</strong>
              <span>{visibleRequests.length} requests</span>
            </header>
            <div className="dispatch-queue-list">
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
                      setSelectedId(item.id);
                      setManual(false);
                      setError("");
                    }}
                  />
                ))
              )}
            </div>
          </section>
          <section className="dispatch-detail">
            <nav className="nav nav-pills dispatch-tabs">
              <button
                className={`nav-link${tab === "recommendation" ? " active" : ""}`}
                onClick={() => setTab("recommendation")}
              >
                Recommendation
                <small>Google OR-Tools · TomTom</small>
              </button>
              <button
                className={`nav-link${tab === "review" ? " active" : ""}`}
                onClick={() => setTab("review")}
              >
                Assignment Review
              </button>
            </nav>
            <div className="dispatch-detail-body">
              {tab === "recommendation" ? (
                <div className="dispatch-center-scroll">
                  {!selected ? (
                    <p className="dispatch-empty">
                      Select an approved request.
                    </p>
                  ) : optimizing ? (
                    <LoadingIndicator
                      variant="card"
                      message="Optimizing assignment…"
                    />
                  ) : recommendation ? (
                    <>
                      <h2>{recommendation.request_number}</h2>
                      <p className="dispatch-explanation">
                        Selected by Google OR-Tools from feasible Driver/Vehicle
                        candidates using TomTom traffic-aware travel time.
                      </p>
                      <dl>
                        <Metric
                          name="Recommended Driver"
                          value={recommendation.recommended_driver.full_name}
                          detail={`${recommendation.recommended_driver.driver_code} · ELIGIBLE`}
                        />
                        <Metric
                          name="Recommended Vehicle"
                          value={
                            recommendation.recommended_vehicle.display_name
                          }
                          detail={
                            recommendation.recommended_vehicle.plate_number
                          }
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
                      <section className="dispatch-why">
                        <h3>Why recommended</h3>
                        <ul>
                          {(recommendation.explanation ?? []).map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </section>
                      {recommendation.gis_preview && (
                        <GisPreview
                          recommendation={recommendation}
                          request={selected}
                          route={consolidation?.recommendation ? null : route}
                          routeState={routeState}
                          stops={consolidation?.recommendation?.route.stops}
                        />
                      )}
                      <CandidateTable
                        items={comparisons}
                        exclusions={exclusions}
                        limited={
                          optimization?.comparison_scope?.limited ?? false
                        }
                      />
                      <SmartConsolidation
                        loading={analyzingConsolidation}
                        result={consolidation}
                        plan={consolidationPlan}
                        busy={busy}
                        onAnalyze={() => void analyze(selected.id)}
                        onKeepSeparate={() => setConsolidation(null)}
                        onConfirm={() => void acceptConsolidation()}
                        onPrepare={() => void preparePlan()}
                      />
                    </>
                  ) : attention ? (
                    <div className="dispatch-attention">
                      <strong>Needs attention</strong>
                      <p>{attention.reason}</p>
                    </div>
                  ) : (
                    <p className="dispatch-empty">
                      No current recommendation. Use Refresh Optimization to
                      retry.
                    </p>
                  )}
                </div>
              ) : (
                <div className="dispatch-review-scroll">
                  {selected && (
                    <>
                      {assignment ? (
                        <Confirmed assignment={assignment} />
                      ) : (
                        <p className="dispatch-empty">
                          No confirmed Driver/Vehicle assignment.
                        </p>
                      )}
                      {recommendation?.schedule_context && (
                        <Schedule context={recommendation.schedule_context} />
                      )}
                      <Audit
                        events={data.assignment_audit?.[selected.id] ?? []}
                      />
                    </>
                  )}
                </div>
              )}
              {tab === "recommendation" && selected && (assignment || recommendation?.schedule_context) && (
                <div className="dispatch-review-scroll">
                  {assignment && <Confirmed assignment={assignment} />}
                  {recommendation?.schedule_context && (
                    <Schedule context={recommendation.schedule_context} />
                  )}
                  <Audit events={data.assignment_audit?.[selected.id] ?? []} />
                </div>
              )}
            </div>
            {selected && (
              <div className="dispatch-actions-bar">
                {!assignment &&
                  recommendation &&
                  !manual && (
                    <button
                      className="btn-confirm"
                      onClick={confirm}
                      disabled={busy}
                    >
                      Confirm Recommendation
                    </button>
                  )}
                <button
                  className="btn-action--filled"
                  onClick={() => setManual((value) => !value)}
                >
                  {manual ? "Cancel Modification" : "Modify Assignment"}
                </button>
                {manual && (
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
                            {driver.full_name} · {driver.driver_code} · ELIGIBLE
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
                          <option value={vehicle.id} key={vehicle.id}>
                            {vehicle.display_name} · {vehicle.plate_number}
                            {vehicle.current_location_available
                              ? ""
                              : " · Current location unavailable — manual assignment only"}
                          </option>
                        ))}
                      </select>
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
                {assignment && selected.status === "APPROVED" && (
                  <>
                    <p className="dispatch-state-note">
                      Confirmed Assignment ≠ Ready for Dispatch
                    </p>
                    <button
                      className="btn-confirm"
                      disabled={busy}
                      onClick={prepare}
                    >
                      Prepare for Dispatch
                    </button>
                  </>
                )}
              </div>
            )}
          </section>
        </div>
      )}
    </section>
  );
}
function RequestRow({
  item,
  selected,
  assigned,
  attention,
  onClick,
}: {
  item: TransportRequestListItem;
  selected: boolean;
  assigned: boolean;
  attention?: string;
  onClick: () => void;
}) {
  const statusText =
    item.status === "READY_FOR_DISPATCH"
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
            statusText === "Confirmed"
              ? "confirmed"
              : statusText === "Ready for Dispatch"
                ? "ready"
                : "pending"
          }
          tone={
            dispatchStatusTone[
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
      </dl>
    </div>
  );
}
