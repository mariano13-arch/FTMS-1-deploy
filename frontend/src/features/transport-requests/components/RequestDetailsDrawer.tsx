import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useAuth } from "../../../contexts/AuthContext";
import { getRequest, mutateRequest, refreshRequestFlight } from "../api";
import LoadingIndicator from "../../../components/common/LoadingIndicator";
import {
  canCancelRequest,
  canEditRequest,
  canPrepareRequest,
  canResubmitRequest,
  isRequestManager,
} from "../requestActionRules";
import { safeError } from "../errors";
import { distanceLabel, durationLabel, delayLabel } from "../routeFormat";
import type { TransportRequest, TransportRoute } from "../types";
import ActionDialog, { type ActionDialogState } from "./ActionDialog";
import { PriorityChip, WorkflowStatusBadge } from "./RequestIndicators";
import { humanize as label } from "../../../utils/text";
import TransportRequestFormPage from "../pages/TransportRequestFormPage";

type Props = {
  requestId: string;
  route?: TransportRoute | null;
  standalone?: boolean;
  mode?: "readOnly" | "review" | "dispatchPreparation";
  onRequestChanged?: (request: TransportRequest) => void;
  onClose: () => void;
};

export default function RequestDetailsDrawer({
  requestId,
  route,
  standalone = false,
  mode = "readOnly",
  onRequestChanged,
  onClose,
}: Props) {
  const { user } = useAuth();
  const [request, setRequest] = useState<TransportRequest | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [dialog, setDialog] = useState<ActionDialogState | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [flightBusy, setFlightBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const dialogRef = useRef<ActionDialogState | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const backdropRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (standalone) return;
    const backdrop = backdropRef.current;
    const workspace = backdrop?.closest(".request-right-workspace");
    const requestWorkspace = workspace?.closest(".request-workspace");
    const queue = requestWorkspace?.querySelector(".request-picker");
    if (
      !backdrop ||
      !(workspace instanceof HTMLElement) ||
      !(queue instanceof HTMLElement)
    ) return;
    const alignToWorkspace = () => {
      const queueClearance = Math.min(
        170,
        Math.max(120, window.innerWidth * 0.09),
      );
      const left = window.innerWidth <= 760
        ? 0
        : queue.getBoundingClientRect().right + queueClearance;
      backdrop.style.setProperty("--request-drawer-left", `${Math.max(0, left)}px`);
    };
    alignToWorkspace();
    const observer = typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(alignToWorkspace);
    observer?.observe(workspace);
    observer?.observe(queue);
    window.addEventListener("resize", alignToWorkspace);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", alignToWorkspace);
    };
  }, [standalone]);
  useEffect(() => {
    const controller = new AbortController();
    void getRequest(requestId, controller.signal)
      .then((item) => {
        if (!item?.id || !item.request_number) {
          setState("error");
          return;
        }
        setRequest(item);
        setState("ready");
      })
      .catch((error) => {
        if (!(error instanceof DOMException && error.name === "AbortError"))
          setState("error");
      });
    closeRef.current?.focus();
    return () => {
      controller.abort();
    };
  }, [onClose, requestId]);
  useEffect(() => {
    dialogRef.current = dialog;
  }, [dialog]);
  const open = (value: ActionDialogState) => {
    setActionError("");
    setDialog(value);
  };
  const confirm = async (note: string) => {
    if (!request || !dialog || busy) return;
    setBusy(true);
    setActionError("");
    try {
      const updated = await mutateRequest(request.id, dialog.action, { note });
      setRequest(updated);
      onRequestChanged?.(updated);
      setDialog(null);
    } catch (reason) {
      setActionError(safeError(reason));
    } finally {
      setBusy(false);
    }
  };
  const delivery = request?.request_category === "DELIVERY_LOGISTICS";
  const supply = delivery && ["SUPPLIER_PICKUP", "BRANCH_TRANSFER"].includes(request?.request_type ?? "");
  const role = user?.role;
  const manager = isRequestManager(role);
  const hasActions =
    request &&
    ((mode === "review" &&
      (canEditRequest(request.status, role) ||
        canResubmitRequest(request.status, role) ||
        canCancelRequest(request.status, role) ||
        (manager && request.status === "FOR_APPROVAL"))) ||
      (mode === "dispatchPreparation" &&
        (canPrepareRequest(request.status, role) ||
          canCancelRequest(request.status, role))));
  const refreshFlight = async () => {
    if (!request || flightBusy) return;
    setFlightBusy(true);
    setActionError("");
    try {
      const updated = await refreshRequestFlight(request.id);
      setRequest(updated);
      onRequestChanged?.(updated);
    } catch (reason) {
      setActionError(safeError(reason));
    } finally {
      setFlightBusy(false);
    }
  };
  return (
    <div
      ref={backdropRef}
      className={`request-drawer-backdrop${standalone ? " request-drawer-backdrop--standalone" : " request-drawer-backdrop--workspace"}`}
      data-testid="request-workspace-backdrop"
    >
      <aside
        className="request-details-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="request-drawer-title"
      >
        {editing ? (
          <TransportRequestFormPage
            editing
            embedded
            requestId={requestId}
            onClose={() => setEditing(false)}
            onSaved={(updated) => {
              setRequest(updated);
              onRequestChanged?.(updated);
              setEditing(false);
            }}
          />
        ) : (
          <>
        <header className="d-flex align-items-start justify-content-between">
          <div>
            <small>
              {request
                ? label(request.request_category ?? request.request_type)
                : "Transport request"}
            </small>
            <h2 id="request-drawer-title">
              {request?.request_number ?? "Request details"}
            </h2>
            {request && <span>{label(request.request_type)}</span>}
          </div>
          {request && <WorkflowStatusBadge value={request.status} />}
          <button
            ref={closeRef}
            type="button"
            className="btn-close"
            aria-label="Close request details"
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <div className="request-drawer-body">
          {state === "loading" && (
            <div className="request-drawer-state" role="status">
              <LoadingIndicator variant="card" message="Loading request details…" />
            </div>
          )}
          {state === "error" && (
            <div
              className="request-drawer-state request-drawer-state--error"
              role="alert"
            >
              Unable to load request details.
            </div>
          )}
          {state === "ready" && request && (
            <>
              <section>
                <h3>Request summary</h3>
                <dl>
                  <div>
                    <dt>Requester</dt>
                    <dd>
                      {request.requester_name}
                      {request.requester_contact && (
                        <small>{request.requester_contact}</small>
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt>Priority</dt>
                    <dd>
                      <PriorityChip value={request.priority} />
                    </dd>
                  </div>
                  <div>
                    <dt>Type</dt>
                    <dd>{label(request.request_type)}</dd>
                  </div>
                  <div>
                    <dt>Category</dt>
                    <dd>
                      {label(request.request_category ?? request.request_type)}
                    </dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd>
                      <WorkflowStatusBadge value={request.status} />
                    </dd>
                  </div>
                  <div>
                    <dt>Source system</dt>
                    <dd>
                      {label(request.source_system)}
                      {request.external_reference && (
                        <small>{request.external_reference}</small>
                      )}
                    </dd>
                  </div>
                </dl>
              </section>
              <section>
                <h3>Schedule</h3>
                <dl>
                  <div className="wide">
                    <dt>Scheduled pickup</dt>
                    <dd>
                      {new Date(request.scheduled_pickup_at).toLocaleString()}
                      <small>
                        {request.estimated_duration_minutes} minute planning
                        window
                      </small>
                    </dd>
                  </div>
                </dl>
              </section>
              <section>
                <h3>Route / location</h3>
                <div className="request-drawer-location">
                  <strong>{request.pickup_name}</strong>
                  <p>{request.pickup_address}</p>
                </div>
                <div className="request-drawer-route-arrow">to</div>
                <div className="request-drawer-location">
                  <strong>{request.destination_name}</strong>
                  <p>{request.destination_address}</p>
                </div>
                {route && (
                  <dl>
                    <div>
                      <dt>Distance</dt>
                      <dd>{distanceLabel(route)}</dd>
                    </div>
                    <div>
                      <dt>Traffic-aware ETA</dt>
                      <dd>{durationLabel(route)}</dd>
                    </div>
                    {route.traffic_delay_seconds > 0 && (
                      <div>
                        <dt>Traffic delay</dt>
                        <dd>{delayLabel(route)}</dd>
                      </div>
                    )}
                  </dl>
                )}
              </section>
              <section>
                <h3>{supply ? "Supply / load context" : delivery ? "Delivery details" : "Passenger details"}</h3>
                {delivery ? (
                  <dl>
                    <div className="wide">
                      <dt>Load description</dt>
                      <dd>{request.load_description}</dd>
                    </div>
                    {request.load_quantity !== null && (
                      <div>
                        <dt>Quantity</dt>
                        <dd>{request.load_quantity}</dd>
                      </div>
                    )}
                    {request.estimated_weight_kg && (
                      <div>
                        <dt>Estimated weight</dt>
                        <dd>{request.estimated_weight_kg} kg</dd>
                      </div>
                    )}
                    {request.handling_instructions && (
                      <div className="wide">
                        <dt>Handling instructions</dt>
                        <dd>{request.handling_instructions}</dd>
                      </div>
                    )}
                    {request.temperature_requirement && (
                      <div className="wide">
                        <dt>Temperature requirement</dt>
                        <dd>{request.temperature_requirement}</dd>
                      </div>
                    )}
                  </dl>
                ) : (
                  <dl>
                    <div>
                      <dt>Passengers</dt>
                      <dd>{request.passenger_count}</dd>
                    </div>
                    <div>
                      <dt>Luggage items</dt>
                      <dd>{request.luggage_count}</dd>
                    </div>
                  </dl>
                )}
              </section>
              {request.request_type === "AIRPORT_PICKUP" && (
                <section>
                  <h3>Passenger / flight context</h3>
                  {request.flight_context ? (
                    <dl>
                      <div><dt>Flight</dt><dd>{request.flight_context.flight_number}</dd></div>
                      <div><dt>Flight status</dt><dd>{request.flight_context.provider_flight_status || label(request.flight_context.refresh_status)}</dd></div>
                      <div><dt>Arrival</dt><dd>{request.flight_context.actual_arrival_at ? new Date(request.flight_context.actual_arrival_at).toLocaleString() : request.flight_context.estimated_arrival_at ? new Date(request.flight_context.estimated_arrival_at).toLocaleString() : request.flight_context.scheduled_arrival_at ? new Date(request.flight_context.scheduled_arrival_at).toLocaleString() : "Unavailable"}</dd></div>
                      <div><dt>Terminal</dt><dd>{request.flight_context.terminal || "Unavailable"}</dd></div>
                      <div className="wide"><dt>Provider</dt><dd>Flightradar24 · {request.flight_context.refresh_message || "Not refreshed"}</dd></div>
                    </dl>
                  ) : (
                    <p>Flight data unavailable. No flight reference was supplied.</p>
                  )}
                  {request.flight_context && (
                    <button
                      type="button"
                      className="button btn-action--outline"
                      disabled={flightBusy}
                      onClick={() => void refreshFlight()}
                    >
                      {flightBusy ? "Refreshing…" : "Refresh flight data"}
                    </button>
                  )}
                  {actionError && !dialog && <p role="alert">{actionError}</p>}
                </section>
              )}
              {request.notes && (
                <section>
                  <h3>Notes / special requirements</h3>
                  <p>{request.notes}</p>
                </section>
              )}
              <section>
                <h3>Audit timeline</h3>
                {request.events.length > 0 ? (
                  <ol className="audit-timeline request-drawer-timeline">
                    {request.events.map((event) => (
                      <li key={event.id}>
                        <span />
                        <div>
                          <strong>{label(event.event_type)}</strong>
                          <p>
                            {event.performed_by} ·{" "}
                            {new Date(event.created_at).toLocaleString()}
                          </p>
                          {event.previous_status && (
                            <small>
                              {label(event.previous_status)} →{" "}
                              {label(event.new_status)}
                            </small>
                          )}
                          {event.note && <p>{event.note}</p>}
                        </div>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p>No recorded request activity is available.</p>
                )}
              </section>
            </>
          )}
        </div>
        {state === "ready" && request && hasActions && (
          <footer className="request-drawer-actions">
            <div className="d-flex flex-wrap align-items-center gap-2">
              {mode === "review" && manager &&
                request.status === "FOR_APPROVAL" && (
                  <>
                    <button
                      className="btn-confirm"
                      disabled={busy}
                      onClick={() =>
                        open({
                          action: "approve",
                          title: "Approve request",
                          description:
                            "Approve this request for dispatch planning.",
                          confirmLabel: "Approve Request",
                          note: "optional",
                        })
                      }
                    >
                      Approve Request
                    </button>
                    <button
                      className="btn-cancel"
                      disabled={busy}
                      onClick={() =>
                        open({
                          action: "request-more-details",
                          title: "Request more details",
                          description:
                            "Return this request for corrections before a decision is made.",
                          confirmLabel: "Request Details",
                          note: "required",
                        })
                      }
                    >
                      Request More Details
                    </button>
                    <button
                      className="button--danger"
                      disabled={busy}
                      onClick={() =>
                        open({
                          action: "reject",
                          title: "Reject request",
                          description:
                            "Reject this request. Rejected requests are terminal.",
                          confirmLabel: "Reject Request",
                          note: "required",
                        })
                      }
                    >
                      Reject
                    </button>
                  </>
                )}
              {mode === "review" && canEditRequest(request.status, role) && (
                <button
                  type="button"
                  className="button btn-action--filled"
                  onClick={() => setEditing(true)}
                >
                  Edit request
                </button>
              )}
              {mode === "review" && canResubmitRequest(request.status, role) && (
                <button
                  className="btn-confirm"
                  disabled={busy}
                  onClick={() =>
                    open({
                      action: "resubmit",
                      title: "Resubmit for approval",
                      description:
                        "Confirm that the requested corrections are ready for another review.",
                      confirmLabel: "Resubmit for Approval",
                      note: "hidden",
                    })
                  }
                >
                  Resubmit for Approval
                </button>
              )}
              {mode === "dispatchPreparation" && canPrepareRequest(request.status, role) && (
                <button
                  className="btn-confirm"
                  disabled={busy}
                  onClick={() =>
                    open({
                      action: "prepare-dispatch",
                      title: "Prepare for Dispatch",
                      description:
                        "Release this approved request to the Dispatch Board. No vehicle or driver will be assigned by this action.",
                      confirmLabel: "Prepare for Dispatch",
                      note: "hidden",
                    })
                  }
                >
                  Prepare for Dispatch
                </button>
              )}
              {canCancelRequest(request.status, role) && (
                <button
                  className="button--danger"
                  disabled={busy}
                  onClick={() =>
                    open({
                      action: "cancel",
                      title: "Cancel request",
                      description:
                        "Cancel this request and preserve its recorded history.",
                      confirmLabel: "Cancel Request",
                      note: "required",
                      dismissLabel: "Keep Request",
                    })
                  }
                >
                  Cancel Request
                </button>
              )}
            </div>
          </footer>
        )}
          </>
        )}
      </aside>
      {dialog && (
        <ActionDialog
          dialog={dialog}
          busy={busy}
          error={actionError}
          close={() => {
            setDialog(null);
            setActionError("");
          }}
          confirm={confirm}
        />
      )}
    </div>
  );
}
