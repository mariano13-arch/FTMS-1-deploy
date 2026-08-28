import type { Geofence, GeofenceWrite } from "./api";

type GeofenceDraft = GeofenceWrite & { id?: string };
type Props = {
  open: boolean;
  loadState: "idle" | "loading" | "ready" | "error";
  saveState: "idle" | "loading" | "ready" | "error";
  geofences: Geofence[];
  selectedId: string;
  selected: Geofence | null;
  draft: GeofenceDraft | null;
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
};

const words = (value: string) =>
  value
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());

export default function GeofenceWorkspace({
  open,
  loadState,
  saveState,
  geofences,
  selectedId,
  selected,
  draft,
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
}: Props) {
  if (!open) return null;
  const change = <K extends keyof GeofenceDraft>(
    field: K,
    value: GeofenceDraft[K],
  ) => draft && onDraftChange({ ...draft, [field]: value });
  return (
    <aside
      id="live-fleet-geofence-panel"
      className="live-fleet-geofence-panel"
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
          <label>
            Name
            <input
              aria-label="Geofence name"
              value={draft.name}
              maxLength={120}
              onChange={(event) => change("name", event.target.value)}
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
                  change(
                    "category",
                    event.target.value as GeofenceWrite["category"],
                  )
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
                  onShapeChange(
                    event.target.value as GeofenceWrite["shape_type"],
                  )
                }
              >
                <option value="CIRCLE">Circle</option>
                <option value="POLYGON">Custom polygon</option>
              </select>
            </label>
          </div>
          {draft.shape_type === "CIRCLE" ? (
            <label>
              Radius <span>{draft.radius_meters} m</span>
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
              <strong>{draft.vertices.length} boundary points</strong>
              <span>
                Use at least three points. The boundary closes automatically.
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
          <label>
            Description
            <textarea
              aria-label="Geofence description"
              value={draft.description}
              maxLength={500}
              rows={3}
              onChange={(event) => change("description", event.target.value)}
              placeholder="Purpose or operating notes"
            />
          </label>
          <div className="live-fleet-geofence-options">
            <label>
              Color
              <input
                aria-label="Geofence color"
                type="color"
                value={draft.color}
                onChange={(event) =>
                  change("color", event.target.value.toUpperCase())
                }
              />
            </label>
            <label>
              <input
                type="checkbox"
                checked={draft.show_on_map}
                onChange={(event) =>
                  change("show_on_map", event.target.checked)
                }
              />
              Show on map
            </label>
            <label>
              <input
                type="checkbox"
                checked={draft.is_active}
                onChange={(event) => change("is_active", event.target.checked)}
              />
              Track activity
            </label>
          </div>
          {saveState === "error" && (
            <p className="live-fleet-geofence-error" role="alert">
              Unable to save this geofence. Check its name and boundary.
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
                  ? "Save changes"
                  : "Create geofence"}
            </button>
          </footer>
        </div>
      ) : (
        <div className="live-fleet-geofence-browser">
          <div className="live-fleet-geofence-toolbar">
            <span>
              {geofences.length} saved zone{geofences.length === 1 ? "" : "s"}
            </span>
            <button type="button" onClick={onPlaceNew}>
              + New geofence
            </button>
          </div>
          {loadState === "loading" ? (
            <p>Loading geofences…</p>
          ) : loadState === "error" ? (
            <p role="alert">Unable to load geofences.</p>
          ) : geofences.length === 0 ? (
            <div className="live-fleet-geofence-empty">
              <strong>No geofences yet</strong>
              <span>Create one from here or use the map action menu.</span>
            </div>
          ) : (
            <div className="live-fleet-geofence-list">
              {geofences.map((item) => (
                <button
                  type="button"
                  className={selectedId === item.id ? "selected" : ""}
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
              className="live-fleet-geofence-detail"
              aria-label={`${selected.name} geofence details`}
            >
              <header>
                <span>
                  <small>{words(selected.category)}</small>
                  <strong>{selected.name}</strong>
                </span>
                <button type="button" onClick={onEdit}>
                  Edit
                </button>
              </header>
              {selected.description && <p>{selected.description}</p>}
              <div className="live-fleet-geofence-metrics">
                <span>
                  <strong>{selected.current_vehicle_count}</strong>Currently
                  inside
                </span>
                <span>
                  <strong>{selected.event_count}</strong>Recorded transitions
                </span>
              </div>
              <h3>Vehicles inside</h3>
              {selected.current_vehicles?.length ? (
                <ul>
                  {selected.current_vehicles.map((vehicle) => (
                    <li key={vehicle.vehicle_id}>
                      <strong>{vehicle.vehicle_name}</strong>
                      <span>
                        {vehicle.plate_number} · seen{" "}
                        {new Date(vehicle.recorded_at).toLocaleTimeString()}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p>No vehicles currently inside.</p>
              )}
              <h3>Entry / exit activity</h3>
              {selected.events?.length ? (
                <ol>
                  {selected.events.map((event) => (
                    <li key={event.id}>
                      <i
                        className={
                          event.event_type === "ENTER" ? "enter" : "exit"
                        }
                      >
                        {event.event_type === "ENTER" ? "IN" : "OUT"}
                      </i>
                      <span>
                        <strong>{event.vehicle_name}</strong>
                        <small>
                          {event.plate_number} ·{" "}
                          {new Date(event.occurred_at).toLocaleString()}
                        </small>
                      </span>
                    </li>
                  ))}
                </ol>
              ) : (
                <p>No real telemetry transitions recorded yet.</p>
              )}
              <small className="live-fleet-geofence-source-note">
                Activity uses persisted real telemetry. Demo-only map positions
                are not written to history.
              </small>
            </section>
          )}
        </div>
      )}
    </aside>
  );
}
