import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../../contexts/AuthContext";
import { getRequest, mutateRequest } from "../api";
import LoadingIndicator from "../../../components/common/LoadingIndicator";
import {
  canCancelRequest,
  canEditRequest,
  canResubmitRequest,
  isRequestManager,
} from "../requestActionRules";
import { safeError } from "../errors";
import { distanceLabel, durationLabel, delayLabel } from "../routeFormat";
import type { TransportRequest, TransportRoute } from "../types";
import ActionDialog, { type ActionDialogState } from "./ActionDialog";
import { PriorityChip, WorkflowStatusBadge } from "./RequestIndicators";
import { humanize as label } from "../../../utils/text";

type Props = {
  requestId: string;
  route?: TransportRoute | null;
  allowReviewActions?: boolean;
  onRequestChanged?: (request: TransportRequest) => void;
  onClose: () => void;
};

export default function RequestDetailsDrawer({
  requestId,
  route,
  allowReviewActions = false,
  onRequestChanged,
  onClose,
}: Props) {
  const { user } = useAuth();
  const [request, setRequest] = useState<TransportRequest | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [dialog, setDialog] = useState<ActionDialogState | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const dialogRef = useRef<ActionDialogState | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
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
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !dialogRef.current) onClose();
    };
    document.addEventListener("keydown", closeOnEscape);
    closeRef.current?.focus();
    return () => {
      controller.abort();
      document.removeEventListener("keydown", closeOnEscape);
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
  const role = user?.role;
  const manager = isRequestManager(role);
  const hasActions =
    request &&
    (canEditRequest(request.status, role) ||
      canResubmitRequest(request.status, role) ||
      canCancelRequest(request.status, role) ||
      (allowReviewActions && manager && request.status === "FOR_APPROVAL"));
  return (
    <div
      className="request-drawer-backdrop"
      data-testid="request-workspace-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside
        className="request-details-drawer"
        role="dialog"
        aria-labelledby="request-drawer-title"
      >
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
                <h3>{delivery ? "Delivery details" : "Passenger details"}</h3>
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
              {allowReviewActions &&
                manager &&
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
              {canEditRequest(request.status, role) && (
                <Link
                  className="button btn-action--filled"
                  to={`/transport-requests/${request.id}/edit`}
                >
                  Edit request
                </Link>
              )}
              {canResubmitRequest(request.status, role) && (
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
                    })
                  }
                >
                  Cancel Request
                </button>
              )}
            </div>
          </footer>
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
