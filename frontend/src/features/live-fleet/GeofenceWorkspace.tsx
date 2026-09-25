import { useEffect, useState } from "react";

import {
  getGeofenceActivity,
  type FleetLiveVehicle,
  type Geofence,
  type GeofenceActivityResponse,
  type GeofenceEvent,
  type GeofenceWrite,
} from "./api";

type GeofenceDraft = GeofenceWrite & { id?: string };

type Props = {
  open: boolean;
  loadState: "idle" | "loading" | "ready" | "error";
  saveState: "idle" | "loading" | "ready" | "error";
  geofences: Geofence[];
  selectedId: string;
  selected: Geofence | null;
  draft: GeofenceDraft | null;
  vehicles: FleetLiveVehicle[];
  onClose: () => void;
  onPlaceNew: () => void;
  onSelect: (id: string) => void;
  onEdit: () => void;
  onDraftChange: (draft: GeofenceDraft) => void;
  onShapeChange: (shape: GeofenceWrite["shape_type"]) => void;
  onRadiusChange: (radius: number) => void;
  onRedraw: () => void;
  onFinishDrawing: () => void;
  onCancelDraft: () => void;
  onSave: () => void;
  onViewActivity: (event: GeofenceEvent) => void;
};

const words = (value: string) =>
  value
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());

function GeofenceMonitoring({
  geofence,
  vehicles,
  onViewActivity,
}: {
  geofence: Geofence;
  vehicles: FleetLiveVehicle[];
  onViewActivity: (event: GeofenceEvent) => void;
}) {
  const [eventType, setEventType] = useState<
    "" | GeofenceEvent["event_type"]
  >("");
  const [vehicle, setVehicle] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);

  const [activity, setActivity] =
    useState<GeofenceActivityResponse | null>(null);

  const [activityState, setActivityState] = useState<
    "loading" | "ready" | "error"
  >("loading");

  useEffect(() => {
    const controller = new AbortController();

    getGeofenceActivity(
      {
        geofence: geofence.id,
        event_type: eventType || undefined,
        vehicle: vehicle ? Number(vehicle) : undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        page,
        page_size: 20,
      },
      controller.signal,
    )
      .then((response) => {
        setActivity(response);
        setActivityState("ready");
      })
      .catch((reason) => {
        if (
          !(
            reason instanceof DOMException &&
            reason.name === "AbortError"
          )
        ) {
          setActivityState("error");
        }
      });

    return () => controller.abort();
  }, [dateFrom, dateTo, eventType, geofence.id, page, vehicle]);

  const changeFilter = (change: () => void) => {
    setActivityState("loading");
    setPage(1);
    change();
  };

  const changePage = (nextPage: number) => {
    setActivityState("loading");
    setPage(nextPage);
  };

  return (
    <section
      className="live-fleet-geofence-monitoring"
      aria-label={`${geofence.name} geofence monitoring`}
    >
      <div className="live-fleet-geofence-section-heading">
        <span>Monitoring</span>
      </div>
      <div className="live-fleet-geofence-summary">
        <span>
          <strong>{geofence.current_vehicle_count}</strong>
          Assets inside
        </span>

        <span>
          <strong>{geofence.entries_today}</strong>
          Entries today
        </span>

        <span>
          <strong>{geofence.exits_today}</strong>
          Exits today
        </span>

        <span>
          <strong>
            {geofence.latest_event
              ? new Date(
                  geofence.latest_event.occurred_at,
                ).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })
              : "—"}
          </strong>
          Latest activity
        </span>
      </div>

      <div className="live-fleet-geofence-section-heading">
        <span>Vehicles Inside</span>
        <small>{geofence.current_vehicle_count}</small>
      </div>

      {geofence.current_vehicles?.length ? (
        <ul>
          {geofence.current_vehicles.map((item) => (
            <li key={item.vehicle_id}>
              <strong>{item.vehicle_name}</strong>
              <span>
                {item.plate_number} · seen{" "}
                {new Date(item.recorded_at).toLocaleTimeString()}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p>No vehicles currently inside.</p>
      )}

      <div className="live-fleet-geofence-activity-heading">
        <h3>Activity History</h3>
        <small>{activity?.count ?? 0} records</small>
      </div>

      <div className="live-fleet-geofence-activity-filters">
        <label>
          Event
          <select
            aria-label="Filter geofence activity by event type"
            value={eventType}
            onChange={(event) =>
              changeFilter(() =>
                setEventType(
                  event.target.value as
                    | ""
                    | GeofenceEvent["event_type"],
                ),
              )
            }
          >
            <option value="">All</option>
            <option value="ENTER">ENTER</option>
            <option value="EXIT">EXIT</option>
          </select>
        </label>

        <label>
          Asset
          <select
            aria-label="Filter geofence activity by vehicle"
            value={vehicle}
            onChange={(event) =>
              changeFilter(() => setVehicle(event.target.value))
            }
          >
            <option value="">All assets</option>

            {vehicles.map((item) => (
              <option value={item.vehicle_id} key={item.vehicle_id}>
                {item.display_name} · {item.plate_number}
              </option>
            ))}
          </select>
        </label>

        <label>
          From
          <input
            aria-label="Geofence activity date from"
            type="date"
            value={dateFrom}
            max={dateTo || undefined}
            onChange={(event) =>
              changeFilter(() => setDateFrom(event.target.value))
            }
          />
        </label>

        <label>
          To
          <input
            aria-label="Geofence activity date to"
            type="date"
            value={dateTo}
            min={dateFrom || undefined}
            onChange={(event) =>
              changeFilter(() => setDateTo(event.target.value))
            }
          />
        </label>
      </div>

      {activityState === "loading" ? (
        <p role="status">Loading geofence activity…</p>
      ) : activityState === "error" ? (
        <p role="alert">Unable to load geofence activity.</p>
      ) : !activity?.results.length ? (
        <p>No persisted activity matches these filters.</p>
      ) : (
        <div className="live-fleet-geofence-activity-table-wrap">
          <table className="live-fleet-geofence-activity-table">
            <thead>
              <tr>
                <th>Date &amp; time</th>
                <th>Asset / vehicle</th>
                <th>Plate</th>
                <th>Event</th>
                <th>Geofence</th>
                <th>Location</th>
              </tr>
            </thead>

            <tbody>
              {activity.results.map((item) => {
                const restrictedEntry =
                  item.event_type === "ENTER" &&
                  item.geofence_category === "RESTRICTED";

                return (
                  <tr key={item.id}>
                    <td>
                      {new Date(item.occurred_at).toLocaleString()}
                    </td>

                    <td>{item.vehicle_name}</td>

                    <td>{item.plate_number}</td>

                    <td>
                      <span
                        className={[
                          "live-fleet-geofence-event",
                          `live-fleet-geofence-event--${item.event_type.toLowerCase()}`,
                          restrictedEntry
                            ? "live-fleet-geofence-event--restricted"
                            : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                      >
                        {restrictedEntry
                          ? "Restricted Entry"
                          : item.event_type}
                      </span>
                    </td>

                    <td>{item.geofence_name}</td>

                    <td>
                      <button
                        type="button"
                        onClick={() => onViewActivity(item)}
                      >
                        View on map
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {activityState === "ready" &&
        activity &&
        activity.count > 0 && (
          <div className="live-fleet-geofence-activity-pages">
            <span>Page {page}</span>

            <div>
              <button
                type="button"
                disabled={!activity.previous}
                onClick={() =>
                  changePage(Math.max(1, page - 1))
                }
              >
                Previous
              </button>

              <button
                type="button"
                disabled={!activity.next}
                onClick={() => changePage(page + 1)}
              >
                Next
              </button>
            </div>
          </div>
        )}

      <small className="live-fleet-geofence-source-note">
        Activity uses persisted real telemetry. Historical markers are
        distinct from current live positions.
      </small>
    </section>
  );
}

export default function GeofenceWorkspace({
  open,
  loadState,
  saveState,
  geofences,
  selectedId,
  selected,
  draft,
  vehicles,
  onClose,
  onPlaceNew,
  onSelect,
  onEdit,
  onDraftChange,
  onShapeChange,
  onRadiusChange,
  onRedraw,
  onFinishDrawing,
  onCancelDraft,
  onSave,
  onViewActivity,
}: Props) {
  if (!open) return null;

  const change = <K extends keyof GeofenceDraft>(
    field: K,
    value: GeofenceDraft[K],
  ) => draft && onDraftChange({ ...draft, [field]: value });

  return (
    <aside
      id="live-fleet-geofence-panel"
      className={`live-fleet-geofence-panel ${draft ? "live-fleet-geofence-panel--editor" : "live-fleet-geofence-panel--browser"}`}
      aria-label="Geofence workspace"
    >
      <header>
        <span>
          <small>Location intelligence</small>
          <strong>
            {draft
              ? draft.id
                ? "Edit geofence"
                : "New geofence"
              : "Geofences"}
          </strong>
        </span>

        <button
          type="button"
          aria-label="Close geofence workspace"
          onClick={onClose}
        >
          ×
        </button>
      </header>

      {draft ? (
        <div className="live-fleet-geofence-editor">
          <section className="live-fleet-geofence-form-section" aria-labelledby="geofence-details-heading">
            <h3 id="geofence-details-heading">Geofence Details</h3>
            <label>
              Name
              <input
                aria-label="Geofence name"
                value={draft.name}
                maxLength={120}
                onChange={(event) =>
                  change("name", event.target.value)
                }
                placeholder="e.g. Oxford loading zone"
              />
            </label>

            <div className="live-fleet-geofence-two">
              <label>
                Category
                <select
                  aria-label="Geofence category"
                  value={draft.category}
                  onChange={(event) =>
                    change("category", event.target.value as GeofenceWrite["category"])
                  }
                >
                  <option value="DEPOT">Depot</option>
                  <option value="CUSTOMER">Customer site</option>
                  <option value="HOTEL">Hotel property</option>
                  <option value="RESTRICTED">Restricted area</option>
                  <option value="CUSTOM">Custom</option>
                </select>
              </label>

              <label>
                Boundary
                <select
                  aria-label="Geofence boundary shape"
                  value={draft.shape_type}
                  onChange={(event) =>
                    onShapeChange(event.target.value as GeofenceWrite["shape_type"])
                  }
                >
                  <option value="CIRCLE">Circle</option>
                  <option value="POLYGON">Custom polygon</option>
                </select>
              </label>
            </div>

            <label>
              Description
              <textarea
                aria-label="Geofence description"
                value={draft.description}
                maxLength={500}
                rows={3}
                onChange={(event) =>
                  change("description", event.target.value)
                }
                placeholder="Purpose or operating notes"
              />
            </label>
          </section>

          <section className="live-fleet-geofence-form-section" aria-labelledby="boundary-settings-heading">
            <h3 id="boundary-settings-heading">Boundary Settings</h3>
            {draft.shape_type === "CIRCLE" ? (
              <label className="live-fleet-geofence-radius">
                <span>Radius <output>{draft.radius_meters} m</output></span>
                <input
                  aria-label="Geofence radius"
                  type="range"
                  min="25"
                  max="3000"
                  step="25"
                  value={draft.radius_meters ?? 150}
                  onChange={(event) => onRadiusChange(Number(event.target.value))}
                />
              </label>
            ) : (
              <div className="live-fleet-geofence-draw">
              <strong>
                {draft.vertices.length} boundary points
              </strong>

              <span>
                Use at least three points. The boundary closes
                automatically.
              </span>

              <button type="button" onClick={onRedraw}>
                Redraw boundary
              </button>

              <button
                type="button"
                disabled={draft.vertices.length < 3}
                onClick={onFinishDrawing}
              >
                Finish drawing
              </button>
              </div>
            )}
          </section>

          <section className="live-fleet-geofence-form-section" aria-labelledby="appearance-monitoring-heading">
            <h3 id="appearance-monitoring-heading">Appearance &amp; Monitoring</h3>
            <div className="live-fleet-geofence-options">
            <label className="live-fleet-geofence-color-control">
              <span>Boundary color</span>
              <input
                aria-label="Geofence color"
                type="color"
                value={draft.color}
                onChange={(event) =>
                  change(
                    "color",
                    event.target.value.toUpperCase(),
                  )
                }
              />
            </label>

            <label className="live-fleet-geofence-switch">
              <span><strong>Show on map</strong><small>Display this geofence on the Live Map</small></span>
              <input
                type="checkbox"
                checked={draft.show_on_map}
                onChange={(event) =>
                  change("show_on_map", event.target.checked)
                }
              />
              <i aria-hidden="true" />
            </label>

            <label className="live-fleet-geofence-switch">
              <span><strong>Track activity</strong><small>Record enter / exit activity</small></span>
              <input
                type="checkbox"
                checked={draft.is_active}
                onChange={(event) =>
                  change("is_active", event.target.checked)
                }
              />
              <i aria-hidden="true" />
            </label>
            </div>
          </section>

          {saveState === "error" && (
            <p
              className="live-fleet-geofence-error"
              role="alert"
            >
              Unable to save this geofence. Check its name and
              boundary.
            </p>
          )}

          <footer>
            <button type="button" onClick={onCancelDraft}>
              Cancel
            </button>

            <button
              type="button"
              disabled={
                !draft.name.trim() ||
                draft.vertices.length < 3 ||
                saveState === "loading"
              }
              onClick={onSave}
            >
              {saveState === "loading"
                ? "Saving…"
                : draft.id
                  ? "Save Changes"
                  : "Create geofence"}
            </button>
          </footer>
        </div>
      ) : (
        <div className="live-fleet-geofence-browser">
          <div className="live-fleet-geofence-toolbar">
            <span><strong>Saved Geofences</strong><small>{geofences.length}</small></span>

            <button type="button" onClick={onPlaceNew}>
              + New Geofence
            </button>
          </div>

          {loadState === "loading" ? (
            <p>Loading geofences…</p>
          ) : loadState === "error" ? (
            <p role="alert">Unable to load geofences.</p>
          ) : geofences.length === 0 ? (
            <div className="live-fleet-geofence-empty">
              <strong>No geofences yet</strong>
              <span>
                Create one from here or use the map action menu.
              </span>
            </div>
          ) : (
            <div className="live-fleet-geofence-list">
              {geofences.map((item) => (
                <button
                  type="button"
                  className={
                    selectedId === item.id ? "selected" : ""
                  }
                  aria-pressed={selectedId === item.id}
                  key={item.id}
                  onClick={() => onSelect(item.id)}
                >
                  <i style={{ background: item.color }} />

                  <span>
                    <strong>{item.name}</strong>

                    <small>
                      {words(item.category)} ·{" "}
                      {item.shape_type === "CIRCLE"
                        ? `${item.radius_meters} m radius`
                        : `${item.vertices.length} points`}
                    </small>
                  </span>

                  <b title="Vehicles currently inside">
                    {item.current_vehicle_count}
                  </b>
                </button>
              ))}
            </div>
          )}

          {selected && (
            <section
              key={selected.id}
              className="live-fleet-geofence-detail"
              aria-label={`${selected.name} geofence details`}
            >
              <div className="live-fleet-geofence-section-heading">
                <span>Selected Geofence</span>
              </div>
              <header>
                <span>
                    <small>{words(selected.category)}</small>
                    <strong>{selected.name}</strong>
                    <em>
                      {selected.shape_type === "CIRCLE"
                        ? `${selected.radius_meters} m radius · Circle`
                        : `${selected.vertices.length} boundary points · Custom polygon`}
                    </em>
                </span>

                <button type="button" onClick={onEdit}>
                  Edit
                </button>
              </header>

              {selected.description && (
                <p>{selected.description}</p>
              )}

              <GeofenceMonitoring
                key={selected.id}
                geofence={selected}
                vehicles={vehicles}
                onViewActivity={onViewActivity}
              />
            </section>
          )}
        </div>
      )}
    </aside>
  );
}
