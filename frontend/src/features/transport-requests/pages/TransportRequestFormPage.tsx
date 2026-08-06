import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useHistory, useParams } from "react-router-dom";
import { ApiError } from "../../../services/api";
import { createRequest, editRequest, getRequest } from "../api";
import { priorities, requestTypes, sourceSystems, vehicleTypes } from "../types";
import type { TransportRequest } from "../types";

const errorMessages = (value: unknown): string[] => {
  if (typeof value === "string") return [value];
  if (typeof value === "number" || typeof value === "boolean") return [String(value)];
  if (Array.isArray(value)) return value.flatMap(errorMessages);
  if (value && typeof value === "object") return Object.values(value as Record<string, unknown>).flatMap(errorMessages);
  return [];
};

const normalizeErrors = (body: unknown) => {
  if (!body || typeof body !== "object" || Array.isArray(body)) return {};
  return Object.fromEntries(
    Object.entries(body as Record<string, unknown>).map(([field, value]) => [
      field,
      errorMessages(value).join(" ") || "Invalid value.",
    ]),
  );
};

export default function TransportRequestFormPage({ editing = false }: { editing?: boolean }) {
  const { requestId = "" } = useParams<{ requestId: string }>();
  const history = useHistory(); const inFlight = useRef(false); const errorSummaryRef = useRef<HTMLDivElement>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [existing, setExisting] = useState<TransportRequest | null>(null);
  useEffect(() => { if (!editing) return; const controller = new AbortController(); getRequest(requestId, controller.signal).then(setExisting).catch(() => setError("Unable to load the transport request.")); return () => controller.abort(); }, [editing, requestId]);
  if (editing && !existing && !error) return <div className="state-card">Loading request…</div>;
  if (editing && existing && !["FOR_APPROVAL", "NEEDS_MORE_DETAILS"].includes(existing.status)) return <div className="state-card">This request can no longer be edited. <Link to={`/transport-requests/${existing.id}`}>Return to request details</Link>.</div>;
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); if (inFlight.current) return; inFlight.current = true; setBusy(true); setError(""); setFieldErrors({}); const data = new FormData(event.currentTarget);
    const payload = Object.fromEntries(data.entries()) as Record<string, unknown>;
    for (const field of ["passenger_count", "luggage_count", "estimated_duration_minutes"]) payload[field] = Number(payload[field]);
    payload.scheduled_pickup_at = new Date(String(payload.scheduled_pickup_at)).toISOString();
    try { const saved = editing ? await editRequest(requestId, payload) : await createRequest(payload); history.push(`/transport-requests/${saved.id}`); }
    catch (reason) { if (reason instanceof ApiError && reason.body && typeof reason.body === "object") { setFieldErrors(normalizeErrors(reason.body)); setError("Please correct the request information."); } else setError(`Unable to ${editing ? "save" : "create"} the transport request.`); requestAnimationFrame(() => errorSummaryRef.current?.focus()); }
    finally { inFlight.current = false; setBusy(false); }
  };
  const fieldError = (name: string) => fieldErrors[name] && <small id={`${name}-error`} className="field-error" role="alert">{fieldErrors[name]}</small>;
  const controlProps = (name: string, hintId?: string) => ({
    "aria-invalid": Boolean(fieldErrors[name]),
    "aria-describedby": [hintId, fieldErrors[name] ? `${name}-error` : ""].filter(Boolean).join(" ") || undefined,
  });
  const scheduledDate = existing?.scheduled_pickup_at ? new Date(existing.scheduled_pickup_at) : null;
  const scheduled = scheduledDate ? new Date(scheduledDate.getTime() - scheduledDate.getTimezoneOffset() * 60_000).toISOString().slice(0, 16) : "";
  const requestedDetails = existing?.events.filter(event => event.event_type === "REQUESTED_MORE_DETAILS").at(-1);
  return <section className={`form-page${editing ? " form-page--edit-request" : ""}`}><div className="detail-heading"><div><p className="breadcrumb"><Link to="/transport-requests">Transport Requests</Link> / {editing ? existing?.request_number : "New"}</p><h1>{editing ? "Edit Transport Request" : "New Transport Request"}</h1><p>{editing ? "Update this request while it awaits approval." : "Create a PostgreSQL-backed request for review and approval."}</p></div></div><form key={existing?.id ?? "new"} className={`request-form${editing ? " request-form--edit" : ""}`} onSubmit={submit}>
    {existing?.status === "NEEDS_MORE_DETAILS" && requestedDetails && <div className="details-requested"><strong>More details requested</strong><p>{requestedDetails.note}</p><small>{requestedDetails.performed_by} · {new Date(requestedDetails.created_at).toLocaleString()}</small><span>Saving changes does not resubmit the request. Use “Resubmit for Approval” from the request detail page after saving.</span></div>}
    {error && <div ref={errorSummaryRef} className="form-error-summary message message--error" role="alert" tabIndex={-1}><strong>{error}</strong>{Object.entries(fieldErrors).length > 0 && <ul>{Object.entries(fieldErrors).map(([field, message]) => <li key={field}>{field === "non_field_errors" ? message : `${field.replaceAll("_", " ")}: ${message}`}</li>)}</ul>}</div>}
    <fieldset><legend>Request source</legend><label>Source system<select name="source_system" required defaultValue={existing?.source_system} {...controlProps("source_system")}>{sourceSystems.map(value => <option key={value}>{value}</option>)}</select>{fieldError("source_system")}</label><label>External reference<input name="external_reference" maxLength={120} defaultValue={existing?.external_reference} {...controlProps("external_reference")} />{fieldError("external_reference")}</label><label>Request type<select name="request_type" required defaultValue={existing?.request_type} {...controlProps("request_type")}>{requestTypes.map(value => <option key={value}>{value}</option>)}</select>{fieldError("request_type")}</label><label>Priority<select name="priority" defaultValue={existing?.priority} {...controlProps("priority")}>{priorities.map(value => <option key={value}>{value}</option>)}</select>{fieldError("priority")}</label></fieldset>
    <fieldset><legend>Requester and schedule</legend><label>Requester name<input name="requester_name" required defaultValue={existing?.requester_name} {...controlProps("requester_name")} />{fieldError("requester_name")}</label><label>Requester contact<input name="requester_contact" defaultValue={existing?.requester_contact} {...controlProps("requester_contact")} />{fieldError("requester_contact")}</label><label>Scheduled pickup<input name="scheduled_pickup_at" type="datetime-local" required defaultValue={scheduled} {...controlProps("scheduled_pickup_at")} />{fieldError("scheduled_pickup_at")}</label><label>Planning duration (minutes)<input name="estimated_duration_minutes" type="number" min="15" max="1440" defaultValue={existing?.estimated_duration_minutes ?? 60} required {...controlProps("estimated_duration_minutes", "planning-duration-hint")} /><small id="planning-duration-hint">Vehicle allocation window only; not route ETA.</small>{fieldError("estimated_duration_minutes")}</label><label>Required vehicle type<select name="required_vehicle_type" defaultValue={existing?.required_vehicle_type ?? ""} {...controlProps("required_vehicle_type")}><option value="">Any Suitable Vehicle</option>{vehicleTypes.map(value => <option key={value}>{value}</option>)}</select>{fieldError("required_vehicle_type")}</label><label>Passengers<input name="passenger_count" type="number" min="1" max="100" defaultValue={existing?.passenger_count ?? 1} required {...controlProps("passenger_count")} />{fieldError("passenger_count")}</label><label>Luggage items<input name="luggage_count" type="number" min="0" max="100" defaultValue={existing?.luggage_count ?? 0} required {...controlProps("luggage_count")} />{fieldError("luggage_count")}</label></fieldset>
    <fieldset><legend>Pickup</legend><label>Pickup name<input name="pickup_name" required defaultValue={existing?.pickup_name} {...controlProps("pickup_name")} />{fieldError("pickup_name")}</label><label className={editing ? "edit-field--wide" : undefined}>Pickup address<input name="pickup_address" required defaultValue={existing?.pickup_address} {...controlProps("pickup_address")} />{fieldError("pickup_address")}</label><label>Latitude<input name="pickup_latitude" type="number" step="0.000001" min="-90" max="90" required defaultValue={existing?.pickup_latitude} {...controlProps("pickup_latitude")} />{fieldError("pickup_latitude")}</label><label>Longitude<input name="pickup_longitude" type="number" step="0.000001" min="-180" max="180" required defaultValue={existing?.pickup_longitude} {...controlProps("pickup_longitude")} />{fieldError("pickup_longitude")}</label></fieldset>
    <fieldset><legend>Destination</legend><label>Destination name<input name="destination_name" required defaultValue={existing?.destination_name} {...controlProps("destination_name")} />{fieldError("destination_name")}</label><label className={editing ? "edit-field--wide" : undefined}>Destination address<input name="destination_address" required defaultValue={existing?.destination_address} {...controlProps("destination_address")} />{fieldError("destination_address")}</label><label>Latitude<input name="destination_latitude" type="number" step="0.000001" min="-90" max="90" required defaultValue={existing?.destination_latitude} {...controlProps("destination_latitude")} />{fieldError("destination_latitude")}</label><label>Longitude<input name="destination_longitude" type="number" step="0.000001" min="-180" max="180" required defaultValue={existing?.destination_longitude} {...controlProps("destination_longitude")} />{fieldError("destination_longitude")}</label></fieldset>
    <label className={`full-field${editing ? " edit-field--long" : ""}`}>Notes<textarea name="notes" rows={4} defaultValue={existing?.notes} {...controlProps("notes")} />{fieldError("notes")}</label><div className="form-actions"><Link className="button button--secondary" to={existing ? `/transport-requests/${existing.id}` : "/transport-requests"}>Cancel</Link><button disabled={busy}>{busy ? "Saving…" : editing ? "Save Changes" : "Create Request"}</button></div>
  </form></section>;
}
