import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../../../contexts/AuthContext";
import { getVehicles, type Vehicle } from "../../../services/vehicles";
import LoadingIndicator from "../../../components/common/LoadingIndicator";
import ActionDialog, {
  type ActionDialogState,
} from "../components/ActionDialog";
import RequestMap from "../components/RequestMap";
import {
  PriorityChip,
  WorkflowStatusBadge,
} from "../components/RequestIndicators";
import { getRequest, mutateRequest } from "../api";
import {
  canCancelRequest,
  canEditRequest,
  canResubmitRequest,
  isRequestManager,
  isRequestOperator,
} from "../requestActionRules";
import { safeError } from "../errors";
import type { TransportRequest } from "../types";
import { humanize as label } from "../../../utils/text";

export default function TransportRequestDetailPage() {
  const { requestId = "" } = useParams<{ requestId: string }>();
  const { user } = useAuth();
  const [request, setRequest] = useState<TransportRequest | null>(null);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error" | "missing">(
    "loading",
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [vehicleId, setVehicleId] = useState("");
  const [dialog, setDialog] = useState<ActionDialogState | null>(null);
  const load = useCallback(
    (signal?: AbortSignal) =>
      Promise.all([
        getRequest(requestId, signal),
        getVehicles("is_active=true&page_size=100", signal),
      ])
        .then(([item, fleet]) => {
          setRequest(item);
          setVehicles(fleet.results);
          setVehicleId(item.assigned_vehicle?.device_id ?? "");
          setState("ready");
        })
        .catch((reason: { status?: number }) =>
          setState(reason.status === 404 ? "missing" : "error"),
        ),
    [requestId],
  );
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);
  const confirm = async (note: string) => {
    if (!request || !dialog || busy) return;
    setBusy(true);
    setError("");
    const body =
      dialog.action === "assign-vehicle"
        ? { vehicle_device_id: vehicleId, note }
        : { note };
    try {
      await mutateRequest(request.id, dialog.action, body);
      await load();
      setDialog(null);
    } catch (reason) {
      setError(safeError(reason));
    } finally {
      setBusy(false);
    }
  };
  const open = (value: ActionDialogState) => {
    setError("");
    setDialog(value);
  };
  if (state === "loading" || (request && request.id !== requestId))
    return (
      <div className="state-card card text-center border-0">
        <LoadingIndicator variant="card" message="Loading request…" />
      </div>
    );
  if (!request)
    return (
      <div
        role={state === "error" ? "alert" : undefined}
        className="state-card card text-center border-0"
      >
        {state === "missing"
          ? "Transport request not found."
          : "Unable to load transport request."}
      </div>
    );
  const manager = isRequestManager(user?.role);
  const operator = isRequestOperator(user?.role);
  const eligible = vehicles.filter(
    (vehicle) =>
      (vehicle.passenger_capacity === null ||
        vehicle.passenger_capacity >= request.passenger_count) &&
      (!request.required_vehicle_type ||
        vehicle.vehicle_type === request.required_vehicle_type),
  );
  const selectedVehicle = vehicles.find(
    (vehicle) => vehicle.device_id === vehicleId,
  );
  const assignedVehicle = request.assigned_vehicle;
  const delivery = request.request_category === "DELIVERY_LOGISTICS";
  return (
    <section className="detail-page">
      <div className="detail-heading d-flex align-items-start justify-content-between ms-3 gap-3">
        <div>
          <p className="breadcrumb text-secondary small mb-1">
            <Link to="/transport-requests">Transport Requests</Link> /{" "}
            {request.request_number}
          </p>
          <h1>{request.request_number}</h1>
          <p className="detail-subtitle">
            {label(request.request_type)} · Created by {request.created_by}
          </p>
        </div>
      </div>
      <div className="detail-layout">
        <div className="detail-main">
          <section className="detail-card detail-card--accent">
            <h2>Locations</h2>
            <dl className="detail-grid detail-grid--locations">
              <div>
                <dt>Pickup</dt>
                <dd>
                  {request.pickup_name}
                  <small>{request.pickup_address}</small>
                </dd>
              </div>
              <div>
                <dt>Destination</dt>
                <dd>
                  {request.destination_name}
                  <small>{request.destination_address}</small>
                </dd>
              </div>
            </dl>
          </section>
          <section className="detail-card detail-card--accent">
            <h2>Schedule</h2>
            <dl className="detail-grid">
              <div>
                <dt>Requester</dt>
                <dd>
                  {request.requester_name}
                  <small>
                    {request.requester_contact || "No contact supplied"}
                  </small>
                </dd>
              </div>
              <div>
                <dt>Scheduled pickup</dt>
                <dd>
                  {new Date(request.scheduled_pickup_at).toLocaleString()}
                </dd>
              </div>
              <div>
                <dt>Planning duration</dt>
                <dd>
                  {request.estimated_duration_minutes} minutes
                  <small>Used for vehicle scheduling, not route ETA</small>
                </dd>
              </div>
              <div>
                <dt>Priority</dt>
                <dd>
                  <PriorityChip value={request.priority} />
                </dd>
              </div>
            </dl>
          </section>
          <section className="detail-card detail-card--accent">
            <h2>Request details</h2>
            <dl className="detail-grid">
              {delivery ? (
                <>
                  <div className="wide">
                    <dt>Load description</dt>
                    <dd>{request.load_description}</dd>
                  </div>
                  <div>
                    <dt>Load quantity</dt>
                    <dd>{request.load_quantity ?? "Not supplied"}</dd>
                  </div>
                  <div>
                    <dt>Estimated weight</dt>
                    <dd>
                      {request.estimated_weight_kg
                        ? `${request.estimated_weight_kg} kg`
                        : "Not supplied"}
                    </dd>
                  </div>
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
                </>
              ) : (
                <>
                  <div>
                    <dt>Passengers</dt>
                    <dd>{request.passenger_count}</dd>
                  </div>
                  <div>
                    <dt>Luggage items</dt>
                    <dd>{request.luggage_count}</dd>
                  </div>
                </>
              )}
              <div>
                <dt>Required vehicle type</dt>
                <dd>
                  {request.required_vehicle_type
                    ? label(request.required_vehicle_type)
                    : "Any suitable vehicle"}
                </dd>
              </div>
              <div>
                <dt>Assigned vehicle</dt>
                <dd>
                  {request.assigned_vehicle
                    ? `${request.assigned_vehicle.display_name} · ${request.assigned_vehicle.plate_number}`
                    : "Unassigned"}
                </dd>
              </div>
              <div>
                <dt>Source</dt>
                <dd>
                  {label(request.source_system)}
                  <small>
                    {request.external_reference || "No external reference"}
                  </small>
                </dd>
              </div>
              {request.notes && (
                <div className="wide">
                  <dt>Notes</dt>
                  <dd>{request.notes}</dd>
                </div>
              )}
            </dl>
          </section>
          <section className="detail-card detail-card--accent">
            <h2>Audit timeline</h2>
            <ol className="audit-timeline">
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
          </section>
        </div>
        <aside>
          <WorkflowStatusBadge value={request.status} />
          <RequestMap request={request} />
          <section className="detail-card actions-card card">
            <h2>Available actions</h2>
            {request.status === "FOR_APPROVAL" && manager && (
              <div className="action-stack d-grid gap-2">
                <button
                  className="btn-confirm"
                  disabled={busy}
                  onClick={() =>
                    open({
                      action: "approve",
                      title: "Approve request",
                      description:
                        "Approve this request for manual vehicle assignment.",
                      confirmLabel: "Approve Request",
                      note: "optional",
                    })
                  }
                >
                  Approve
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
              </div>
            )}
            {canEditRequest(request.status, user?.role) && (
              <Link
                className="button btn-action--filled"
                to={`/transport-requests/${request.id}/edit`}
              >
                Edit request
              </Link>
            )}
            {canResubmitRequest(request.status, user?.role) && (
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
            {request.status === "APPROVED" && operator && (
              <>
                <label>
                  Eligible active vehicle
                  <select
                    className="form-select"
                    value={vehicleId}
                    onChange={(event) => setVehicleId(event.target.value)}
                  >
                    <option value="">Select vehicle</option>
                    {eligible.map((vehicle) => (
                      <option key={vehicle.device_id} value={vehicle.device_id}>
                        {vehicle.display_name} · {vehicle.plate_number} (
                        {vehicle.passenger_capacity ?? "capacity unknown"})
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="btn-confirm"
                  disabled={
                    busy ||
                    !vehicleId ||
                    vehicleId === assignedVehicle?.device_id
                  }
                  onClick={() =>
                    open({
                      action: "assign-vehicle",
                      title: assignedVehicle
                        ? "Reassign vehicle"
                        : "Assign vehicle",
                      description:
                        "Confirm this manual vehicle allocation. Availability is checked again by the server.",
                      confirmLabel: assignedVehicle
                        ? "Reassign Vehicle"
                        : "Assign Vehicle",
                      note: "optional",
                      context: selectedVehicle
                        ? `${selectedVehicle.display_name} · ${selectedVehicle.plate_number} · ${selectedVehicle.vehicle_type}`
                        : "",
                    })
                  }
                >
                  {assignedVehicle ? "Reassign Vehicle" : "Assign Vehicle"}
                </button>
                {assignedVehicle && (
                  <button
                    className="btn-confirm"
                    disabled={busy}
                    onClick={() =>
                      open({
                        action: "prepare-dispatch",
                        title: "Mark ready for dispatch",
                        description:
                          "Revalidate the assigned vehicle and hand this request off to the future Driver Dispatch workflow. No trip will be created.",
                        confirmLabel: "Mark Ready for Dispatch",
                        note: "hidden",
                        context: `${assignedVehicle.display_name} · ${assignedVehicle.plate_number}`,
                      })
                    }
                  >
                    Mark Ready for Dispatch
                  </button>
                )}
              </>
            )}
            {canCancelRequest(request.status, user?.role) && (
              <button
                className="button--danger"
                disabled={busy}
                onClick={() =>
                  open({
                    action: "cancel",
                    title: "Cancel request",
                    description:
                      "Cancel this request and release any planned vehicle allocation.",
                    confirmLabel: "Cancel Request",
                    note: "required",
                  })
                }
              >
                Cancel Request
              </button>
            )}
            {!manager && request.status === "FOR_APPROVAL" && (
              <p className="permission-note">
                Dispatchers may edit requests awaiting approval, but approval
                decisions require a Fleet Manager.
              </p>
            )}
            {["REJECTED", "CANCELLED", "READY_FOR_DISPATCH"].includes(
              request.status,
            ) && (
              <p className="permission-note">
                {request.status === "READY_FOR_DISPATCH"
                  ? "This request has reached the Sprint 4 handoff point. Driver assignment and trip execution are planned."
                  : "No further operational actions are available."}
              </p>
            )}
          </section>
        </aside>
      </div>
      {dialog && (
        <ActionDialog
          dialog={dialog}
          busy={busy}
          error={error}
          close={() => {
            setDialog(null);
            setError("");
          }}
          confirm={confirm}
        />
      )}
    </section>
  );
}
