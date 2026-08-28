import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useHistory, useParams } from "react-router-dom";
import { ApiError } from "../../../services/api";
import { createRequest, editRequest, getRequest } from "../api";
import LocationAutocomplete from "../components/LocationAutocomplete";
import LoadingIndicator from "../../../components/common/LoadingIndicator";
import { priorities, requestTypes, vehicleTypes } from "../types";
import type { TransportRequest } from "../types";

const passengerTypes = new Set([
  "AIRPORT_PICKUP",
  "AIRPORT_DROPOFF",
  "GUEST_TRANSFER",
  "VIP_TRANSPORT",
  "STAFF_SHUTTLE",
]);
const deliveryTypes = new Set([
  "SUPPLIER_PICKUP",
  "FOOD_DELIVERY",
  "CATERING_DELIVERY",
  "BANQUET_LOGISTICS",
]);

const errorMessages = (value: unknown): string[] => {
  if (typeof value === "string") return [value];
  if (typeof value === "number" || typeof value === "boolean")
    return [String(value)];
  if (Array.isArray(value)) return value.flatMap(errorMessages);
  if (value && typeof value === "object")
    return Object.values(value as Record<string, unknown>).flatMap(
      errorMessages,
    );
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

export default function TransportRequestFormPage({
  editing = false,
  embedded = false,
  onClose,
  onSaved,
}: {
  editing?: boolean;
  embedded?: boolean;
  onClose?: () => void;
  onSaved?: (request: TransportRequest) => void;
}) {
  const { requestId = "" } = useParams<{ requestId: string }>();
  const history = useHistory();
  const inFlight = useRef(false);
  const errorSummaryRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [existing, setExisting] = useState<TransportRequest | null>(null);
  const [selectedType, setSelectedType] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<
    "PASSENGER_TRANSPORT" | "DELIVERY_LOGISTICS"
  >("PASSENGER_TRANSPORT");
  useEffect(() => {
    if (!editing) return;
    const controller = new AbortController();
    getRequest(requestId, controller.signal)
      .then(setExisting)
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError("Unable to load the transport request.");
      });
    return () => controller.abort();
  }, [editing, requestId]);
  if (editing && !existing && !error)
    return (
      <div className="state-card card text-center border-0">
        <LoadingIndicator variant="card" message="Loading request…" />
      </div>
    );
  if (
    editing &&
    existing &&
    !["FOR_APPROVAL", "NEEDS_MORE_DETAILS"].includes(existing.status)
  )
    return (
      <div className="state-card card text-center border-0">
        This request can no longer be edited.{" "}
        <Link to={`/transport-requests/${existing.id}`}>
          Return to request details
        </Link>
        .
      </div>
    );
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    setFieldErrors({});
    const data = new FormData(event.currentTarget);
    const payload = Object.fromEntries(data.entries()) as Record<
      string,
      unknown
    >;
    for (const field of [
      "passenger_count",
      "luggage_count",
      "estimated_duration_minutes",
    ])
      payload[field] = Number(payload[field]);
    if (payload.load_quantity === "") delete payload.load_quantity;
    else if (payload.load_quantity !== undefined)
      payload.load_quantity = Number(payload.load_quantity);
    if (payload.estimated_weight_kg === "") delete payload.estimated_weight_kg;
    payload.scheduled_pickup_at = new Date(
      String(payload.scheduled_pickup_at),
    ).toISOString();
    try {
      const saved = editing
        ? await editRequest(requestId, payload)
        : await createRequest(payload);
      if (embedded) onSaved?.(saved);
      else history.push(`/transport-requests/${saved.id}`);
    } catch (reason) {
      if (
        reason instanceof ApiError &&
        reason.body &&
        typeof reason.body === "object"
      ) {
        setFieldErrors(normalizeErrors(reason.body));
        setError("Please correct the request information.");
      } else
        setError(
          `Unable to ${editing ? "save" : "create"} the transport request.`,
        );
      requestAnimationFrame(() => errorSummaryRef.current?.focus());
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };
  const fieldError = (name: string) =>
    fieldErrors[name] && (
      <small id={`${name}-error`} className="field-error" role="alert">
        {fieldErrors[name]}
      </small>
    );
  const controlProps = (name: string, hintId?: string) => ({
    "aria-invalid": Boolean(fieldErrors[name]),
    "aria-describedby":
      [hintId, fieldErrors[name] ? `${name}-error` : ""]
        .filter(Boolean)
        .join(" ") || undefined,
  });
  const scheduledDate = existing?.scheduled_pickup_at
    ? new Date(existing.scheduled_pickup_at)
    : null;
  const scheduled = scheduledDate
    ? new Date(
        scheduledDate.getTime() - scheduledDate.getTimezoneOffset() * 60_000,
      )
        .toISOString()
        .slice(0, 16)
    : "";
  const requestedDetails = existing?.events
    .filter((event) => event.event_type === "REQUESTED_MORE_DETAILS")
    .at(-1);
  const requestType = selectedType || existing?.request_type || requestTypes[0];
  const derivedCategory = passengerTypes.has(requestType)
    ? "PASSENGER_TRANSPORT"
    : deliveryTypes.has(requestType)
      ? "DELIVERY_LOGISTICS"
      : null;
  const requestCategory =
    derivedCategory ??
    (selectedType
      ? selectedCategory
      : (existing?.request_category ?? selectedCategory));
  const delivery = requestCategory === "DELIVERY_LOGISTICS";
  return (
    <section
      className={`form-page${editing ? " form-page--edit-request" : ""}${embedded ? " form-page--embedded-request" : ""}`}
    >
      {!embedded && (
        <div className="detail-heading">
          <div>
            <p className="breadcrumb">
              <Link to="/transport-requests">Transport Requests</Link> /{" "}
              {editing ? existing?.request_number : "Add"}
            </p>
            <h1>
              {editing ? "Edit Transport Request" : "Add Transport Request"}
            </h1>
            <p>
              {editing
                ? "Update this request while it awaits approval."
                : "Development intake — production requests are normally received from connected hotel and restaurant systems."}
            </p>
          </div>
        </div>
      )}
      <form
        key={existing?.id ?? "new"}
        className={`request-form${editing ? " request-form--edit" : ""}${embedded ? " request-form--embedded" : ""}`}
        onSubmit={submit}
      >
        {existing?.status === "NEEDS_MORE_DETAILS" && requestedDetails && (
          <div className="details-requested alert alert-warning">
            <strong>More details requested</strong>
            <p>{requestedDetails.note}</p>
            <small>
              {requestedDetails.performed_by} ·{" "}
              {new Date(requestedDetails.created_at).toLocaleString()}
            </small>
            <span>
              Saving changes does not resubmit the request. Use “Resubmit for
              Approval” from the request detail page after saving.
            </span>
          </div>
        )}
        {error && (
          <div
            ref={errorSummaryRef}
            className="form-error-summary message message--error alert alert-danger"
            role="alert"
            tabIndex={-1}
          >
            <strong>{error}</strong>
            {Object.entries(fieldErrors).length > 0 && (
              <ul>
                {Object.entries(fieldErrors).map(([field, message]) => (
                  <li key={field}>
                    {field === "non_field_errors"
                      ? message
                      : `${field.replaceAll("_", " ")}: ${message}`}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        <fieldset className="form-section form-section--compact">
          <legend>Request Details</legend>
          <div className="form-inline-fields">
            <label>
              Request type
              <select
                name="request_type"
                required
                value={requestType}
                onChange={(event) => setSelectedType(event.target.value)}
                {...controlProps("request_type")}
              >
                {requestTypes.map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
              {fieldError("request_type")}
            </label>
            {!derivedCategory && (
              <label>
                Category
                <select
                  name="request_category"
                  value={requestCategory}
                  onChange={(event) =>
                    setSelectedCategory(
                      event.target.value as
                        | "PASSENGER_TRANSPORT"
                        | "DELIVERY_LOGISTICS",
                    )
                  }
                  {...controlProps("request_category")}
                >
                  <option value="PASSENGER_TRANSPORT">
                    Passenger transport
                  </option>
                  <option value="DELIVERY_LOGISTICS">
                    Delivery / logistics
                  </option>
                </select>
                {fieldError("request_category")}
              </label>
            )}
            {derivedCategory && (
              <input
                type="hidden"
                name="request_category"
                value={requestCategory}
              />
            )}
            <label>
              Priority
              <select
                name="priority"
                defaultValue={existing?.priority}
                {...controlProps("priority")}
              >
                {priorities.map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
              {fieldError("priority")}
            </label>
            <label>
              {editing ? "External reference" : "Development reference"}
              <input
                name="external_reference"
                maxLength={120}
                defaultValue={existing?.external_reference}
                {...controlProps("external_reference")}
              />
              {fieldError("external_reference")}
            </label>
          </div>
          {editing ? (
            <input
              type="hidden"
              name="source_system"
              defaultValue={existing?.source_system}
            />
          ) : (
            <input
              type="hidden"
              name="source_system"
              value="MANUAL_STAFF_ENTRY"
            />
          )}
        </fieldset>
        <fieldset className="form-section form-section--details">
          <legend>Requester & Schedule</legend>
          <label>
            Requester name
            <input
              name="requester_name"
              required
              defaultValue={existing?.requester_name}
              {...controlProps("requester_name")}
            />
            {fieldError("requester_name")}
          </label>
          <label>
            Requester contact
            <input
              name="requester_contact"
              defaultValue={existing?.requester_contact}
              {...controlProps("requester_contact")}
            />
            {fieldError("requester_contact")}
          </label>
          <label>
            Scheduled pickup
            <input
              name="scheduled_pickup_at"
              type="datetime-local"
              required
              defaultValue={scheduled}
              {...controlProps("scheduled_pickup_at")}
            />
            {fieldError("scheduled_pickup_at")}
          </label>
          <label>
            Planning duration (minutes)
            <input
              name="estimated_duration_minutes"
              type="number"
              min="15"
              max="1440"
              defaultValue={existing?.estimated_duration_minutes ?? 60}
              required
              {...controlProps(
                "estimated_duration_minutes",
                "planning-duration-hint",
              )}
            />
            <small id="planning-duration-hint">
              Vehicle allocation window only; not route ETA.
            </small>
            {fieldError("estimated_duration_minutes")}
          </label>
          <label>
            Required vehicle type
            <select
              name="required_vehicle_type"
              defaultValue={existing?.required_vehicle_type ?? ""}
              {...controlProps("required_vehicle_type")}
            >
              <option value="">Any Suitable Vehicle</option>
              {vehicleTypes.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
            {fieldError("required_vehicle_type")}
          </label>
          {delivery ? (
            <>
              <input type="hidden" name="passenger_count" value="0" />
              <input type="hidden" name="luggage_count" value="0" />
              <label className="full-field">
                Load description
                <textarea
                  name="load_description"
                  required
                  rows={2}
                  defaultValue={existing?.load_description}
                  {...controlProps("load_description")}
                />
                {fieldError("load_description")}
              </label>
              <label>
                Load quantity
                <input
                  name="load_quantity"
                  type="number"
                  min="1"
                  defaultValue={existing?.load_quantity ?? ""}
                  {...controlProps("load_quantity")}
                />
                {fieldError("load_quantity")}
              </label>
              <label>
                Estimated weight (kg)
                <input
                  name="estimated_weight_kg"
                  type="number"
                  min="0.01"
                  step="0.01"
                  defaultValue={existing?.estimated_weight_kg ?? ""}
                  {...controlProps("estimated_weight_kg")}
                />
                {fieldError("estimated_weight_kg")}
              </label>
              <label className="full-field">
                Handling instructions
                <textarea
                  name="handling_instructions"
                  rows={2}
                  defaultValue={existing?.handling_instructions}
                  {...controlProps("handling_instructions")}
                />
                {fieldError("handling_instructions")}
              </label>
              <label>
                Temperature requirement
                <input
                  name="temperature_requirement"
                  defaultValue={existing?.temperature_requirement}
                  {...controlProps("temperature_requirement")}
                />
                {fieldError("temperature_requirement")}
              </label>
            </>
          ) : (
            <>
              <label>
                Passengers
                <input
                  name="passenger_count"
                  type="number"
                  min="1"
                  max="100"
                  defaultValue={existing?.passenger_count || 1}
                  required
                  {...controlProps("passenger_count")}
                />
                {fieldError("passenger_count")}
              </label>
              <label>
                Luggage items
                <input
                  name="luggage_count"
                  type="number"
                  min="0"
                  max="100"
                  defaultValue={existing?.luggage_count ?? 0}
                  required
                  {...controlProps("luggage_count")}
                />
                {fieldError("luggage_count")}
              </label>
            </>
          )}
        </fieldset>

        <div className="form-section form-section--locations">
          <LocationAutocomplete
            kind="pickup"
            initialName={existing?.pickup_name}
            initialAddress={existing?.pickup_address}
            initialLatitude={existing?.pickup_latitude}
            initialLongitude={existing?.pickup_longitude}
            errors={fieldErrors}
          />
          <LocationAutocomplete
            kind="destination"
            initialName={existing?.destination_name}
            initialAddress={existing?.destination_address}
            initialLatitude={existing?.destination_latitude}
            initialLongitude={existing?.destination_longitude}
            errors={fieldErrors}
          />
        </div>

        <label className="form-section form-section--notes">
          Notes
          <textarea
            name="notes"
            rows={4}
            defaultValue={existing?.notes}
            {...controlProps("notes")}
          />
          {fieldError("notes")}
        </label>
        <div className="form-actions d-flex align-items-center gap-2">
          {embedded ? (
            <button
              type="button"
              className="btn-cancel"
              onClick={onClose}
            >
              Cancel
            </button>
          ) : (
            <Link
              className="button btn-cancel"
              to={
                existing
                  ? `/transport-requests/${existing.id}`
                  : "/transport-requests"
              }
            >
              Cancel
            </Link>
          )}
          <button className="btn-confirm" disabled={busy}>
            {busy ? "Saving…" : editing ? "Save Changes" : "Create Request"}
          </button>
        </div>
      </form>
    </section>
  );
}
