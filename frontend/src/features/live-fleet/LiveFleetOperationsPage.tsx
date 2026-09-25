import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getDrivers, type Driver } from "../../services/drivers";
import RequestMap, {
  type FleetPopupInfo,
} from "../transport-requests/components/RequestMap";
import type { TransportRoute } from "../transport-requests/types";
import GeofenceWorkspace from "./GeofenceWorkspace";
import { VehicleStatusDrawer } from "./VehicleStatusPage";
import {
  getFleetLiveVehicles,
  getFleetActiveAssignmentRoute,
  getFleetSafetyEvents,
  createGeofence as createGeofenceRecord,
  getGeofence,
  getGeofences,
  updateGeofence,
  type FleetLiveResponse,
  type FleetLiveVehicle,
  type FleetActiveRoute,
  type FleetSafetyEvent,
  type Geofence,
  type GeofenceCoordinate,
  type GeofenceEvent,
  type GeofenceWrite,
  type TelemetryState,
} from "./api";

type FleetFilter = "all" | "assigned" | "live" | "attention";
type NavigatorView = "vehicles" | "drivers";
type AsyncState = "idle" | "loading" | "ready" | "error";

const pollIntervalMs = 15_000;
const routeRefreshIntervalMs = 60_000;

const routeDistance = (meters: number) =>
  meters >= 1000 ? `${(meters / 1000).toFixed(1)} km` : `${meters} m`;
const routeDuration = (seconds: number) => `${Math.max(1, Math.ceil(seconds / 60))} min`;
const positionAge = (seconds: number) => {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours > 0 ? `${hours}h ${minutes}m old` : `${Math.max(1, minutes)}m old`;
};

const words = (value: string) =>
  value
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());

const stateLabel: Record<TelemetryState, string> = {
  live: "Live",
  stale: "Stale",
  offline: "Offline",
  no_telemetry: "No telemetry",
};

const navigatorLabel: Record<NavigatorView, string> = {
  vehicles: "Vehicles",
  drivers: "Drivers",
};

type GeofenceDraft = GeofenceWrite & { id?: string };

function circleVertices(
  center: GeofenceCoordinate,
  radiusMeters: number,
): GeofenceCoordinate[] {
  return Array.from({ length: 40 }, (_, index) => {
    const angle = (index / 40) * Math.PI * 2;

    const latitude =
      center.latitude +
      (radiusMeters * Math.cos(angle)) / 111_320;

    const longitudeScale =
      111_320 *
      Math.max(
        Math.abs(Math.cos((center.latitude * Math.PI) / 180)),
        0.2,
      );

    return {
      latitude,
      longitude:
        center.longitude +
        (radiusMeters * Math.sin(angle)) / longitudeScale,
    };
  });
}

function geofenceDraftFromPoint(
  point: GeofenceCoordinate,
): GeofenceDraft {
  const radiusMeters = 150;

  return {
    name: "",
    description: "",
    category: "CUSTOM",
    shape_type: "CIRCLE",
    center: point,
    radius_meters: radiusMeters,
    vertices: circleVertices(point, radiusMeters),
    color: "#008F8C",
    show_on_map: true,
    is_active: true,
  };
}

function FleetVehicleLayerRow({
  vehicle,
  selected,
  hidden,
  onToggleVisibility,
  onSelect,
}: {
  vehicle: FleetLiveVehicle;
  selected: boolean;
  hidden: boolean;
  onToggleVisibility: () => void;
  onSelect: () => void;
}) {
  return (
    <div className={`live-fleet-asset-row ${selected ? "selected" : ""}`}>
      <label
        className="live-fleet-marker-toggle"
        title={`${hidden ? "Show" : "Hide"} ${vehicle.display_name} on map`}
      >
        <input
          type="checkbox"
          checked={!hidden}
          onChange={onToggleVisibility}
          aria-label={`Show ${vehicle.display_name} on map`}
        />
        <span />
      </label>
      <button type="button" onClick={onSelect}>
        <span className="live-fleet-asset-icon" aria-hidden="true">▰</span>
        <span>
          <strong>{vehicle.display_name}</strong>
          <small>{vehicle.plate_number} · {words(vehicle.vehicle_type)}</small>
          <small>
            {vehicle.active_assignment
              ? `${vehicle.active_assignment.driver_name} · ${vehicle.active_assignment.driver_code}`
              : "No assigned driver"}
          </small>
        </span>
        <span
          className={`live-fleet-row-state live-fleet-row-state--${vehicle.telemetry_state}`}
          title={stateLabel[vehicle.telemetry_state]}
          aria-label={stateLabel[vehicle.telemetry_state]}
          role="img"
        />
      </button>
    </div>
  );
}

export default function LiveFleetOperationsPage({
  focusedVehicleId = "",
}: {
  focusedVehicleId?: string;
}) {
  const [data, setData] = useState<FleetLiveResponse | null>(null);
  const dataRef = useRef<FleetLiveResponse | null>(null);

  const [loadState, setLoadState] = useState<
    "loading" | "ready" | "error"
  >("loading");

  const [refreshError, setRefreshError] = useState(false);
  const [selectedId, setSelectedId] = useState(focusedVehicleId);
  const [statusVehicleId, setStatusVehicleId] = useState("");
  const [filter, setFilter] = useState<FleetFilter>("all");
  const [search, setSearch] = useState("");

  const [route, setRoute] = useState<TransportRoute | null>(null);
  const [plannedRoute, setPlannedRoute] = useState<TransportRoute | null>(null);
  const [activeRoute, setActiveRoute] = useState<FleetActiveRoute | null>(null);
  const [routeState, setRouteState] =
    useState<AsyncState>("idle");

  const [safetyEvents, setSafetyEvents] = useState<
    FleetSafetyEvent[]
  >([]);
  const [eventsState, setEventsState] =
    useState<AsyncState>("loading");

  const [popupVehicleId, setPopupVehicleId] = useState("");

  const [vehiclePanelOpen, setVehiclePanelOpen] = useState(!focusedVehicleId);

  const [navigatorView, setNavigatorView] =
    useState<NavigatorView>("vehicles");
  const [hiddenVehicleIds, setHiddenVehicleIds] = useState<
    Set<string>
  >(() => new Set());

  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [driversState, setDriversState] =
    useState<AsyncState>("loading");

  const [geofences, setGeofences] = useState<Geofence[]>([]);
  const [geofenceState, setGeofenceState] =
    useState<AsyncState>("loading");

  const [geofencePanelOpen, setGeofencePanelOpen] =
    useState(false);

  const [selectedGeofenceId, setSelectedGeofenceId] =
    useState("");

  const [selectedGeofence, setSelectedGeofence] =
    useState<Geofence | null>(null);

  const [geofenceDraft, setGeofenceDraft] =
    useState<GeofenceDraft | null>(null);

  const [geofenceDrawing, setGeofenceDrawing] =
    useState(false);

  const [geofencePlacement, setGeofencePlacement] =
    useState(false);

  const [geofenceSaveState, setGeofenceSaveState] =
    useState<AsyncState>("idle");

  const [
    geofenceActivitySelection,
    setGeofenceActivitySelection,
  ] = useState<{
    event: GeofenceEvent;
    focusKey: number;
  } | null>(null);

  const geofenceActivityFocusKey = useRef(0);

  useEffect(() => {
    dataRef.current = data;
  }, [data]);

  useEffect(() => {
    const controller = new AbortController();

    getDrivers("page_size=100", controller.signal)
      .then((response) => {
        setDrivers(response.results);
        setDriversState("ready");
      })
      .catch((reason) => {
        if (
          !(
            reason instanceof DOMException &&
            reason.name === "AbortError"
          )
        ) {
          setDriversState("error");
        }
      });

    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    getGeofences(controller.signal)
      .then((response) => {
        setGeofences(response.results);
        setGeofenceState("ready");
      })
      .catch((reason) => {
        if (
          !(
            reason instanceof DOMException &&
            reason.name === "AbortError"
          )
        ) {
          setGeofenceState("error");
        }
      });

    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!selectedGeofenceId) {
      return;
    }

    const controller = new AbortController();

    Promise.resolve(
      getGeofence(selectedGeofenceId, controller.signal),
    )
      .then((result) => {
        if (result) {
          setSelectedGeofence(result);
        }
      })
      .catch((reason) => {
        if (
          !(
            reason instanceof DOMException &&
            reason.name === "AbortError"
          )
        ) {
          setSelectedGeofence(null);
        }
      });

    return () => controller.abort();
  }, [selectedGeofenceId]);

  useEffect(() => {
    let active = true;
    let controller: AbortController | null = null;
    let timer = 0;

    const load = async () => {
      controller = new AbortController();

      try {
        const response = await getFleetLiveVehicles(
          controller.signal,
        );

        if (!active) {
          return;
        }

        setData(response);
        setLoadState("ready");
        setRefreshError(false);

        setSelectedId((current) =>
          current &&
          response.vehicles.some(
            (vehicle) => vehicle.device_id === current,
          )
            ? current
            : (response.vehicles[0]?.device_id ?? ""),
        );
      } catch (reason) {
        if (
          !active ||
          (reason instanceof DOMException &&
            reason.name === "AbortError")
        ) {
          return;
        }

        if (dataRef.current) {
          setRefreshError(true);
        } else {
          setLoadState("error");
        }
      } finally {
        if (active) {
          timer = window.setTimeout(load, pollIntervalMs);
        }
      }
    };

    timer = window.setTimeout(load, 0);

    return () => {
      active = false;
      window.clearTimeout(timer);
      controller?.abort();
    };
  }, []);

  useEffect(() => {
    if (
      loadState !== "ready" ||
      !data?.capabilities.safety_events
    ) {
      return;
    }

    const controller = new AbortController();

    const timer = window.setTimeout(() => {
      setEventsState("loading");

      getFleetSafetyEvents(controller.signal)
        .then((response) => {
          setSafetyEvents(response.events);
          setEventsState("ready");
        })
        .catch((reason) => {
          if (
            !(
              reason instanceof DOMException &&
              reason.name === "AbortError"
            )
          ) {
            setEventsState("error");
          }
        });
    }, 0);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [data?.capabilities.safety_events, loadState]);

  const selected =
    data?.vehicles.find(
      (vehicle) => vehicle.device_id === selectedId,
    ) ?? null;

  const selectedAssignment = selected?.active_assignment ?? null;
  const routeRefreshFingerprint = selectedAssignment
    ? [
        selectedAssignment.assignment_id,
        selectedAssignment.execution_status,
        selected?.telemetry?.latitude.toFixed(3) ?? "none",
        selected?.telemetry?.longitude.toFixed(3) ?? "none",
        Math.floor(Date.parse(data?.generated_at ?? "") / routeRefreshIntervalMs),
      ].join(":")
    : "";

  const statusVehicle = data?.vehicles.find(
    (vehicle) => vehicle.device_id === statusVehicleId,
  ) ?? null;
  const mapFocusedVehicleId = focusedVehicleId || statusVehicleId;

  useEffect(() => {
    const controller = new AbortController();

    const timer = window.setTimeout(() => {
      setRoute(null);
      setPlannedRoute(null);
      setActiveRoute(null);

      if (!selectedAssignment) {
        setRouteState("idle");
        return;
      }

      setRouteState("loading");

      getFleetActiveAssignmentRoute(selectedAssignment.assignment_id, controller.signal)
        .then(({ route: result }) => {
          setActiveRoute(result);
          setRoute(
            result.route
              ? {
                  request_id: selectedAssignment.request_id,
                  geometry: result.route.geometry,
                  distance_meters: result.route.distance_meters,
                  duration_seconds: result.route.duration_seconds,
                  traffic_delay_seconds: result.route.traffic_delay_seconds,
                  departure_time: result.route.departure_time,
                  arrival_time: result.route.arrival_time,
                  traffic_mode: result.route.traffic_mode,
                }
              : null,
          );
          setPlannedRoute(
            result.planned_route
              ? {
                  request_id: selectedAssignment.request_id,
                  ...result.planned_route,
                }
              : null,
          );
          setRouteState(
            result.route || result.planned_route
              ? "ready"
              : result.route_status === "NOT_ACTIVE"
                ? "idle"
                : "error",
          );
        })
        .catch((reason) => {
          if (
            !(
              reason instanceof DOMException &&
              reason.name === "AbortError"
            )
          ) {
            setRouteState("error");
          }
        });
    }, 0);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [routeRefreshFingerprint, selectedAssignment?.assignment_id]);

  const selectVehicle = useCallback(
    (deviceId: string) => {
      setSelectedId(deviceId);
      setPopupVehicleId("");
    },
    [],
  );

  const openVehiclePopup = useCallback(
    (deviceId: string) => {
      setSelectedId(deviceId);
      setPopupVehicleId(deviceId);
    },
    [],
  );

  const fleetLocations = useMemo(
    () =>
      (data?.vehicles ?? []).flatMap((vehicle) =>
        !vehicle.telemetry ||
        hiddenVehicleIds.has(vehicle.device_id)
          ? []
          : [
              {
                deviceId: vehicle.device_id,
                latitude: vehicle.telemetry.latitude,
                longitude: vehicle.telemetry.longitude,
                label: vehicle.display_name,
                telemetryState: vehicle.telemetry_state,
                positionSource: vehicle.telemetry.position_source,
                selected:
                  vehicle.device_id === selectedId,
                emergencySOS: vehicle.emergency_sos
                  ? { activatedAt: vehicle.emergency_sos.activated_at }
                  : null,
              },
            ],
      ),
    [data?.vehicles, hiddenVehicleIds, selectedId],
  );

  const popupVehicle =
    data?.vehicles.find(
      (vehicle) => vehicle.device_id === popupVehicleId,
    ) ?? null;

  const fleetPopup: FleetPopupInfo | null =
    popupVehicle?.telemetry
      ? {
          deviceId: popupVehicle.device_id,
          label: popupVehicle.display_name,
          plateNumber: popupVehicle.plate_number,
          telemetryState: popupVehicle.telemetry_state,
          latitude: popupVehicle.telemetry.latitude,
          longitude: popupVehicle.telemetry.longitude,
          speedKph: popupVehicle.telemetry.speed_kph,
          positionSource: popupVehicle.telemetry.position_source,
          positionAccuracyM: popupVehicle.telemetry.position_accuracy_m,
          rpm: popupVehicle.telemetry.rpm,
          coolantC: popupVehicle.telemetry.coolant_c,
          engineLoadPct: popupVehicle.telemetry.engine_load_pct,
          obdSource: popupVehicle.telemetry.obd_source,
          recordedAt: popupVehicle.telemetry.recorded_at,
          ageSeconds: popupVehicle.telemetry.age_seconds,
          driverName:
            popupVehicle.active_assignment?.driver_name,
          assignmentStatus: popupVehicle.active_assignment
            ? `${popupVehicle.active_assignment.request_number} · ${words(
                popupVehicle.active_assignment.execution_status,
              )}`
            : undefined,
          activeRouteSummary:
            popupVehicle.device_id === selectedId && activeRoute && (activeRoute.route || activeRoute.planned_route)
              ? [
                  activeRoute.route
                    ? `Active leg — ${activeRoute.position_state === "STALE" ? "From last known position" : activeRoute.phase === "TO_PICKUP" ? "To Pickup" : "To Destination"}: ${routeDistance(activeRoute.route.distance_meters)} · ${routeDuration(activeRoute.route.duration_seconds)} TomTom route estimate${activeRoute.position_state === "STALE" && activeRoute.position_age_seconds !== null ? ` · ${positionAge(activeRoute.position_age_seconds)}` : ""}`
                    : "Active leg unavailable",
                  activeRoute.planned_route
                    ? `Next — Pickup to Destination: ${routeDistance(activeRoute.planned_route.distance_meters)} · ${routeDuration(activeRoute.planned_route.duration_seconds)} TomTom route estimate`
                    : null,
                ].filter(Boolean).join(" · ")
              : popupVehicle.device_id === selectedId && popupVehicle.active_assignment && routeState === "error"
                ? "Active route unavailable"
                : undefined,
          telemetrySource:
            popupVehicle.telemetry.telemetry_source,
          emergencySOS: popupVehicle.emergency_sos
            ? { activatedAt: popupVehicle.emergency_sos.activated_at }
            : null,
        }
      : null;

  const mapRequest = selected?.active_assignment
    ? {
        pickup_name:
          selected.active_assignment.pickup_name,
        pickup_latitude:
          selected.active_assignment.pickup_latitude,
        pickup_longitude:
          selected.active_assignment.pickup_longitude,
        destination_name:
          selected.active_assignment.destination_name,
        destination_latitude:
          selected.active_assignment
            .destination_latitude,
        destination_longitude:
          selected.active_assignment
            .destination_longitude,
      }
    : null;

  const visibleVehicles = (data?.vehicles ?? []).filter(
    (vehicle) => {
      const matchesSearch =
        `${vehicle.display_name} ${vehicle.device_id} ${vehicle.plate_number} ${vehicle.active_assignment?.driver_name ?? ""}`
          .toLowerCase()
          .includes(search.trim().toLowerCase());

      const matchesFilter =
        filter === "all" ||
        (filter === "assigned" &&
          Boolean(vehicle.active_assignment)) ||
        (filter === "live" &&
          vehicle.telemetry_state === "live") ||
        (filter === "attention" &&
          ["stale", "offline", "no_telemetry"].includes(
            vehicle.telemetry_state,
          ));

      return matchesSearch && matchesFilter;
    },
  );

  const visibleDrivers = drivers.filter((driver) =>
    `${driver.full_name} ${driver.driver_code}`
      .toLowerCase()
      .includes(search.trim().toLowerCase()),
  );

  const navigatorCount =
    navigatorView === "vehicles"
      ? visibleVehicles.length
      : visibleDrivers.length;

  const allApplicableChecked =
    visibleVehicles.length > 0 &&
    visibleVehicles.every(
      (vehicle) => !hiddenVehicleIds.has(vehicle.device_id),
    );

  const toggleVehicleVisibility = (deviceId: string) =>
    setHiddenVehicleIds((current) => {
      const next = new Set(current);

      if (next.has(deviceId)) {
        next.delete(deviceId);
      } else {
        next.add(deviceId);
      }

      return next;
    });

  const toggleApplicableVehicleVisibility = () =>
    setHiddenVehicleIds((current) => {
      const next = new Set(current);
      visibleVehicles.forEach((vehicle) => {
        if (allApplicableChecked) {
          next.add(vehicle.device_id);
        } else {
          next.delete(vehicle.device_id);
        }
      });
      return next;
    });

  const selectDriver = (driver: Driver) => {
    const assignedVehicle = data?.vehicles.find(
      (vehicle) =>
        vehicle.active_assignment?.driver_id === driver.id,
    );

    if (assignedVehicle) {
      selectVehicle(assignedVehicle.device_id);
    }
  };

  const noFleetTelemetry =
    Boolean(data?.vehicles.length) &&
    data?.vehicles.every((vehicle) => !vehicle.telemetry);

  const startGeofenceDraft = (
    point: GeofenceCoordinate,
  ) => {
    setGeofenceDraft(geofenceDraftFromPoint(point));
    setSelectedGeofenceId("");
    setSelectedGeofence(null);
    setGeofenceDrawing(false);
    setGeofencePlacement(false);
    setGeofencePanelOpen(true);
    setGeofenceSaveState("idle");
  };

  const selectGeofence = (id: string) => {
    setSelectedGeofenceId(id);
    setSelectedGeofence(
      geofences.find((item) => item.id === id) ?? null,
    );
    setGeofenceDraft(null);
    setGeofenceDrawing(false);
    setGeofencePlacement(false);
    setGeofencePanelOpen(true);

    setGeofenceActivitySelection(null);
  };

  const viewGeofenceActivity = (
    event: GeofenceEvent,
  ) => {
    geofenceActivityFocusKey.current += 1;

    setGeofenceActivitySelection({
      event,
      focusKey: geofenceActivityFocusKey.current,
    });

    if (
      data?.vehicles.some(
        (vehicle) =>
          vehicle.device_id === event.device_id,
      )
    ) {
      setSelectedId(event.device_id);
      setPopupVehicleId("");
    }
  };

  const changeGeofenceRadius = (
    radiusMeters: number,
  ) =>
    setGeofenceDraft((current) =>
      current
        ? {
            ...current,
            radius_meters: radiusMeters,
            vertices: circleVertices(
              current.center,
              radiusMeters,
            ),
          }
        : current,
    );

  const changeGeofenceShape = (
    shape: GeofenceWrite["shape_type"],
  ) =>
    setGeofenceDraft((current) => {
      if (!current) {
        return current;
      }

      if (shape === "CIRCLE") {
        const radiusMeters =
          current.radius_meters ?? 150;

        setGeofenceDrawing(false);

        return {
          ...current,
          shape_type: shape,
          radius_meters: radiusMeters,
          vertices: circleVertices(
            current.center,
            radiusMeters,
          ),
        };
      }

      setGeofenceDrawing(true);

      return {
        ...current,
        shape_type: shape,
        radius_meters: null,
        vertices: [],
      };
    });

  const addGeofenceVertex = (
    point: GeofenceCoordinate,
  ) =>
    setGeofenceDraft((current) => {
      if (
        !current ||
        current.shape_type !== "POLYGON"
      ) {
        return current;
      }

      const vertices = [...current.vertices, point];

      const center = vertices.reduce(
        (result, vertex) => ({
          latitude:
            result.latitude +
            vertex.latitude / vertices.length,
          longitude:
            result.longitude +
            vertex.longitude / vertices.length,
        }),
        {
          latitude: 0,
          longitude: 0,
        },
      );

      return {
        ...current,
        vertices,
        center,
      };
    });

  const editSelectedGeofence = () => {
    if (!selectedGeofence) {
      return;
    }

    setGeofenceDraft({
      id: selectedGeofence.id,
      name: selectedGeofence.name,
      description: selectedGeofence.description,
      category: selectedGeofence.category,
      shape_type: selectedGeofence.shape_type,
      vertices: selectedGeofence.vertices,
      center: selectedGeofence.center,
      radius_meters:
        selectedGeofence.radius_meters,
      color: selectedGeofence.color,
      show_on_map: selectedGeofence.show_on_map,
      is_active: selectedGeofence.is_active,
    });

    setGeofenceSaveState("idle");
  };

  const saveGeofence = async () => {
    if (
      !geofenceDraft ||
      !geofenceDraft.name.trim() ||
      geofenceDraft.vertices.length < 3
    ) {
      return;
    }

    setGeofenceSaveState("loading");

    const { id, ...body } = geofenceDraft;

    try {
      const saved = id
        ? await updateGeofence(id, body)
        : await createGeofenceRecord(body);

      const response = await getGeofences();

      setGeofences(response.results);
      setSelectedGeofence(saved);
      setSelectedGeofenceId(saved.id);
      setGeofenceDraft(null);
      setGeofenceDrawing(false);
      setGeofenceSaveState("ready");
    } catch {
      setGeofenceSaveState("error");
    }
  };

  return (
    <section className="transport-page transport-page--workspace live-fleet-page">
      {loadState === "loading" && (
        <div
          className="live-fleet-page-state"
          role="status"
        >
          Loading fleet operations…
        </div>
      )}

      {loadState === "error" && (
        <div
          className="live-fleet-page-state live-fleet-page-state--error"
          role="alert"
        >
          <strong>
            Unable to load fleet operations
          </strong>
          <span>
            Please retry when the fleet service is
            available.
          </span>
        </div>
      )}

      {refreshError && (
        <p
          role="alert"
          className="message message--error live-fleet-refresh-error"
        >
          Latest refresh failed. Showing the last
          successful fleet snapshot.
        </p>
      )}

      {loadState === "ready" && data && (
        <div className="live-fleet-workspace">
          <div className="live-fleet-map">
            {noFleetTelemetry && (
              <div className="live-fleet-map-notice">
                Vehicles are registered, but no
                telemetry has been received yet.
              </div>
            )}

            <RequestMap
              request={mapRequest}
              route={route}
              plannedRoute={plannedRoute}
              routeState={routeState}
              routeCameraKey={
                selectedAssignment
                  ? `${selectedAssignment.assignment_id}:${selectedAssignment.execution_status}`
                  : undefined
              }
              fleetLocations={fleetLocations}
              focusedVehicleId={mapFocusedVehicleId || undefined}
              fleetPopup={fleetPopup}
              onVehicleSelect={openVehiclePopup}
              onVehicleStatus={(deviceId) => {
                setSelectedId(deviceId);
                setPopupVehicleId("");
                setVehiclePanelOpen(false);
                setStatusVehicleId(deviceId);
              }}
              onVehiclePopupClose={() =>
                setPopupVehicleId("")
              }
              geofenceActivityEvent={
                geofenceActivitySelection
                  ? {
                      id:
                        geofenceActivitySelection.event
                          .id,
                      focusKey:
                        geofenceActivitySelection
                          .focusKey,
                      eventType:
                        geofenceActivitySelection.event
                          .event_type,
                      occurredAt:
                        geofenceActivitySelection.event
                          .occurred_at,
                      latitude:
                        geofenceActivitySelection.event
                          .latitude,
                      longitude:
                        geofenceActivitySelection.event
                          .longitude,
                      vehicleName:
                        geofenceActivitySelection.event
                          .vehicle_name,
                      geofenceName:
                        geofenceActivitySelection.event
                          .geofence_name,
                    }
                  : null
              }
              geofences={geofences.map((item) => ({
                id: item.id,
                name: item.name,
                color: item.color,
                vertices: item.vertices,
                center: item.center,
                showOnMap: item.show_on_map,
                selected:
                  item.id === selectedGeofenceId,
              }))}
              geofenceDraft={
                geofenceDraft
                  ? {
                      color: geofenceDraft.color,
                      vertices:
                        geofenceDraft.vertices,
                    }
                  : null
              }
              geofenceDrawing={
                geofenceDrawing ||
                geofencePlacement
              }
              onGeofenceSelect={selectGeofence}
              onGeofenceCreateAt={
                startGeofenceDraft
              }
              onGeofenceDraftMapClick={(point) =>
                geofencePlacement
                  ? startGeofenceDraft(point)
                  : addGeofenceVertex(point)
              }
              onUtilityPanelOpen={() => {
                setVehiclePanelOpen(false);
                setGeofencePanelOpen(false);
              }}
            />
          </div>

          {(geofenceDrawing ||
            geofencePlacement) && (
            <div
              className="live-fleet-map-mode"
              role="status"
            >
              <strong>
                {geofencePlacement
                  ? "Choose the geofence center"
                  : `Draw custom boundary · ${geofenceDraft?.vertices.length ?? 0} points`}
              </strong>

              <span>
                {geofencePlacement
                  ? "Click anywhere on the map."
                  : "Click around the perimeter, then finish drawing."}
              </span>

              <button
                type="button"
                onClick={() => {
                  setGeofenceDrawing(false);
                  setGeofencePlacement(false);
                }}
              >
                Cancel
              </button>
            </div>
          )}

          {data.demo_telemetry.enabled && (
            <div
              className={`live-fleet-demo-banner ${
                data.demo_telemetry.active
                  ? ""
                  : "live-fleet-demo-banner--warning"
              }`}
              role="status"
            >
              {data.demo_telemetry.active
                ? `Demo telemetry mode active — ${data.demo_telemetry.simulated_vehicle_count} simulated location${
                    data.demo_telemetry
                      .simulated_vehicle_count === 1
                      ? ""
                      : "s"
                  } for capstone defense only.`
                : (data.demo_telemetry
                    .configuration_error ??
                  "Demo telemetry mode is enabled but unavailable.")}
            </div>
          )}

          <div
            className="live-fleet-panel-controls"
            aria-label="Map panels"
          >
            {!vehiclePanelOpen && (
              <button
                type="button"
                aria-expanded="false"
                aria-controls="live-fleet-vehicle-panel"
                onClick={() =>
                  setVehiclePanelOpen(true)
                }
              >
                Show fleet{" "}
                <span aria-hidden="true">▾</span>
              </button>
            )}

            <button
              type="button"
              aria-expanded={geofencePanelOpen}
              aria-controls="live-fleet-geofence-panel"
              onClick={() => setGeofencePanelOpen((open) => !open)}
            >
              Geofences{" "}
              <span aria-hidden="true">⬡</span>
            </button>
          </div>

          {vehiclePanelOpen && (
            <aside
              id="live-fleet-vehicle-panel"
              className="live-fleet-list live-fleet-navigator"
              aria-label="Fleet navigator"
            >
              <div
                className="live-fleet-navigator-header"
                data-testid="fleet-navigator-header"
              >
              <div className="live-fleet-navigator-titlebar">
                <strong>Fleet Map Layers</strong>
                <span>{data.vehicles.length}</span>
                <button
                  type="button"
                  aria-label="Collapse fleet navigator"
                  onClick={() => setVehiclePanelOpen(false)}
                >
                  <span aria-hidden="true">−</span>
                </button>
              </div>

              <div
                className="live-fleet-view-switcher"
                role="tablist"
                aria-label="Fleet map layer view"
              >
                {(["vehicles", "drivers"] as const).map((value) => (
                  <button
                    type="button"
                    role="tab"
                    aria-selected={navigatorView === value}
                    className={navigatorView === value ? "selected" : ""}
                    key={value}
                    onClick={() => {
                      setNavigatorView(value);
                      setSearch("");
                    }}
                  >
                    {navigatorLabel[value]}
                  </button>
                ))}
              </div>

              <label className="live-fleet-navigator-search">
                <span aria-hidden="true">
                  ⌕
                </span>

                <input
                  aria-label={
                    navigatorView === "vehicles"
                      ? "Search fleet vehicles"
                      : "Search drivers"
                  }
                  placeholder={
                    navigatorView ===
                    "drivers"
                      ? "Search driver or code"
                      : "Search vehicles"
                  }
                  value={search}
                  onChange={(event) =>
                    setSearch(
                      event.target.value,
                    )
                  }
                />
              </label>

              {navigatorView === "vehicles" && (
                <div
                  className="live-fleet-filters"
                  role="group"
                  aria-label="Fleet filters"
                >
                  {(
                    [
                      "all",
                      "assigned",
                      "live",
                      "attention",
                    ] as FleetFilter[]
                  ).map((value) => (
                    <button
                      type="button"
                      className={
                        filter === value
                          ? "selected"
                          : ""
                      }
                      key={value}
                      onClick={() =>
                        setFilter(value)
                      }
                    >
                      {words(value)}
                    </button>
                  ))}
                </div>
              )}

              {navigatorView === "vehicles" && (
                <div className="live-fleet-visibility-controls">
                  <span>Map Visibility</span>
                  <button
                    type="button"
                    onClick={toggleApplicableVehicleVisibility}
                    disabled={visibleVehicles.length === 0}
                    aria-label={
                      allApplicableChecked
                        ? "Uncheck all visible vehicles"
                        : "Check all visible vehicles"
                    }
                  >
                    {allApplicableChecked ? "Uncheck All" : "Check All"}
                  </button>
                </div>
              )}
              </div>

              <div
                className="live-fleet-rows"
                data-testid="fleet-navigator-scroll-region"
              >
                {navigatorView === "vehicles" &&
                  (data.vehicles.length ===
                  0 ? (
                    <p>
                      No vehicles are
                      registered for fleet
                      operations.
                    </p>
                  ) : visibleVehicles.length ===
                    0 ? (
                    <p>
                      No vehicles match this
                      view.
                    </p>
                  ) : (
                    visibleVehicles.map((vehicle) => (
                      <FleetVehicleLayerRow
                        key={vehicle.device_id}
                        vehicle={vehicle}
                        selected={vehicle.device_id === selectedId}
                        hidden={hiddenVehicleIds.has(vehicle.device_id)}
                        onToggleVisibility={() =>
                          toggleVehicleVisibility(vehicle.device_id)
                        }
                        onSelect={() => selectVehicle(vehicle.device_id)}
                      />
                    ))
                  ))}

                {navigatorView ===
                  "drivers" &&
                  (driversState ===
                  "loading" ? (
                    <p>
                      Loading drivers…
                    </p>
                  ) : driversState ===
                    "error" ? (
                    <p role="alert">
                      Unable to load drivers.
                    </p>
                  ) : visibleDrivers.length ===
                    0 ? (
                    <p>
                      No drivers match this
                      view.
                    </p>
                  ) : (
                    visibleDrivers.map(
                      (driver) => {
                        const assignedVehicle =
                          data.vehicles.find(
                            (vehicle) =>
                              vehicle
                                .active_assignment
                                ?.driver_id ===
                              driver.id,
                          );

                        return (
                          <button
                            type="button"
                            className="live-fleet-driver-row"
                            key={driver.id}
                            onClick={() =>
                              selectDriver(
                                driver,
                              )
                            }
                            disabled={
                              !assignedVehicle
                            }
                          >
                            <span className="live-fleet-driver-avatar">
                              {
                                driver
                                  .first_name[0]
                              }
                              {
                                driver
                                  .last_name[0]
                              }
                            </span>

                            <span>
                              <strong>
                                {
                                  driver.full_name
                                }
                              </strong>

                              <small>
                                {
                                  driver.driver_code
                                }{" "}
                                ·{" "}
                                {words(
                                  driver.employment_status,
                                )}
                              </small>

                              <small>
                                {assignedVehicle
                                  ? `Assigned to ${assignedVehicle.display_name}`
                                  : "No active vehicle assignment"}
                              </small>
                            </span>

                            <b>
                              {words(
                                driver.eligibility_status,
                              )}
                            </b>
                          </button>
                        );
                      },
                    )
                  ))}

              </div>

              <footer data-testid="fleet-navigator-footer">
                <span>
                  {navigatorView === "vehicles"
                    ? `${data.vehicles.length - hiddenVehicleIds.size} of ${data.vehicles.length} visible`
                    : `${navigatorCount} ${navigatorLabel[
                        navigatorView
                      ].toLowerCase()}`}
                </span>

                <span>
                  {eventsState === "error"
                    ? "Safety events unavailable"
                    : eventsState === "ready"
                      ? `${safetyEvents.length} recent safety events`
                      : "Loading safety events"}
                </span>
              </footer>
            </aside>
          )}

          <GeofenceWorkspace
            open={geofencePanelOpen}
            loadState={geofenceState}
            saveState={geofenceSaveState}
            geofences={geofences}
            selectedId={selectedGeofenceId}
            selected={
              selectedGeofenceId
                ? selectedGeofence
                : null
            }
            draft={geofenceDraft}
            vehicles={data.vehicles}
            onClose={() => {
              setGeofencePanelOpen(false);
              setGeofenceDrawing(false);
              setGeofencePlacement(false);
            }}
            onPlaceNew={() => {
              setGeofencePlacement(true);
              setSelectedGeofenceId("");
              setSelectedGeofence(null);
            }}
            onSelect={selectGeofence}
            onEdit={editSelectedGeofence}
            onDraftChange={setGeofenceDraft}
            onShapeChange={changeGeofenceShape}
            onRadiusChange={changeGeofenceRadius}
            onRedraw={() => {
              setGeofenceDraft((current) =>
                current
                  ? {
                      ...current,
                      vertices: [],
                    }
                  : current,
              );

              setGeofenceDrawing(true);
            }}
            onFinishDrawing={() =>
              setGeofenceDrawing(false)
            }
            onCancelDraft={() => {
              setGeofenceDraft(null);
              setGeofenceDrawing(false);
            }}
            onSave={() =>
              void saveGeofence()
            }
            onViewActivity={
              viewGeofenceActivity
            }
          />
        </div>
      )}
      {statusVehicle && (
        <VehicleStatusDrawer
          vehicle={statusVehicle}
          onClose={() => setStatusVehicleId("")}
        />
      )}
    </section>
  );
}
