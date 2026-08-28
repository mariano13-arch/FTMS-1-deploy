import {
  type KeyboardEvent as ReactKeyboardEvent,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import * as maplibregl from "maplibre-gl";
import type {
  GeoJSONSource,
  LngLatBoundsLike,
  Map as MapLibreMap,
  Marker,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { ApiError } from "../../../services/api";
import { getPlaceDetails, suggestPlaces } from "../api";
import type {
  PlaceSuggestion,
  TransportRequestBase,
  TransportRoute,
} from "../types";
import LoadingIndicator from "../../../components/common/LoadingIndicator";

const fallbackCenter: [number, number] = [121.0286, 14.5652];
const fallbackZoom = 13;
const trafficSourceId = "tomtom-traffic-source";
const trafficLayerId = "tomtom-traffic-layer";
const incidentsSourceId = "tomtom-incidents-source";
const incidentsLayerId = "tomtom-incidents-layer";
const routeSourceId = "request-route-source";
const routeCasingLayerId = "request-route-casing";
const routeLayerId = "request-route-line";
const fleetTrailSourceId = "fleet-trail-source";
const fleetTrailLineLayerId = "fleet-trail-line";
const fleetTrailPointLayerId = "fleet-trail-points";
const geofenceSourceId = "fleet-geofences-source";
const geofenceFillLayerId = "fleet-geofences-fill";
const geofenceLineLayerId = "fleet-geofences-line";
const geofenceDraftSourceId = "fleet-geofence-draft-source";
const geofenceDraftFillLayerId = "fleet-geofence-draft-fill";
const geofenceDraftLineLayerId = "fleet-geofence-draft-line";
const geofenceDraftPointLayerId = "fleet-geofence-draft-points";
const stylePreferenceKey = "ftms.transportRequests.mapStyle";
const trafficPreferenceKey = "ftms.transportRequests.trafficEnabled";
const incidentsPreferenceKey = "ftms.transportRequests.incidentsEnabled";
const mapStyles = {
  street: { label: "Street", tomTomStyle: "basic_street-light-driving" },
  mono: { label: "Mono", tomTomStyle: "basic_mono-light" },
  satellite: { label: "Satellite", tomTomStyle: "basic_street-satellite" },
  dark: { label: "Dark", tomTomStyle: "basic_street-dark-driving" },
} as const;
type MapStyle = keyof typeof mapStyles;

type MapContextPoint = {
  x: number;
  y: number;
  latitude: number;
  longitude: number;
};
type MapCoordinate = { latitude: number; longitude: number };
type MapSearchStatus =
  | "idle"
  | "loading"
  | "empty"
  | "error"
  | "unavailable"
  | "select-error";
let fallbackMapSearchSession = 0;
const newMapSearchSession = () => {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function")
    return crypto.randomUUID();
  fallbackMapSearchSession += 1;
  return `00000000-0000-4000-8001-${String(fallbackMapSearchSession).padStart(12, "0")}`;
};
export type FleetPopupInfo = {
  deviceId: string;
  label: string;
  plateNumber: string;
  telemetryState: "live" | "stale" | "offline" | "no_telemetry";
  latitude: number;
  longitude: number;
  speedKph: number;
  recordedAt: string;
  ageSeconds: number;
  driverName?: string;
  assignmentStatus?: string;
  telemetrySource: "real" | "demo";
};

type MapProps = {
  request: Pick<
    TransportRequestBase,
    | "pickup_latitude"
    | "pickup_longitude"
    | "pickup_name"
    | "destination_latitude"
    | "destination_longitude"
    | "destination_name"
  > | null;
  route?: TransportRoute | null;
  routeState?: "idle" | "loading" | "ready" | "error";
  operationalLocation?: {
    latitude: number;
    longitude: number;
    label: string;
  } | null;
  numberedStops?: Array<{
    sequence: number;
    latitude: string;
    longitude: string;
    label: string;
  }>;
  fleetLocations?: Array<{
    deviceId: string;
    latitude: number;
    longitude: number;
    label: string;
    telemetryState: "live" | "stale" | "offline" | "no_telemetry";
    selected?: boolean;
  }>;
  fleetTrail?: Array<{
    event_id: string;
    latitude: number;
    longitude: number;
    recorded_at: string;
  }>;
  safetyEvents?: Array<{
    event_id: string;
    event_type: "HARSH_BRAKING" | "HARSH_ACCELERATION";
    latitude: number;
    longitude: number;
    vehicle_name: string;
  }>;
  onVehicleSelect?: (deviceId: string) => void;
  fleetPopup?: FleetPopupInfo | null;
  onVehiclePopupClose?: () => void;
  onSafetyEventSelect?: (eventId: string) => void;
  geofences?: Array<{
    id: string;
    name: string;
    color: string;
    vertices: MapCoordinate[];
    center: MapCoordinate;
    showOnMap: boolean;
    selected?: boolean;
  }>;
  geofenceDraft?: { color: string; vertices: MapCoordinate[] } | null;
  geofenceDrawing?: boolean;
  onGeofenceSelect?: (id: string) => void;
  onGeofenceCreateAt?: (point: MapCoordinate) => void;
  onGeofenceDraftMapClick?: (point: MapCoordinate) => void;
};

function styleUrl(style: MapStyle) {
  return `https://api.tomtom.com/maps/orbis/assets/styles/0.*/style?apiVersion=1&map=${mapStyles[style].tomTomStyle}`;
}

function savedStyle(): MapStyle {
  try {
    const value = localStorage.getItem(stylePreferenceKey);
    return value && value in mapStyles ? (value as MapStyle) : "street";
  } catch {
    return "street";
  }
}

function savedToggle(key: string) {
  try {
    const value = localStorage.getItem(key);
    return value === "false" ? false : true;
  } catch {
    return true;
  }
}

function validCoordinate(
  latitude: unknown,
  longitude: unknown,
): [number, number] | null {
  const lat = Number(latitude);
  const lng = Number(longitude);
  return Number.isFinite(lat) && Number.isFinite(lng) ? [lng, lat] : null;
}

function markerElement(
  kind: "pickup" | "destination" | "vehicle",
  label: string,
) {
  const element = document.createElement("div");
  element.className = `request-map-marker request-map-marker--${kind}`;
  const kindLabel =
    kind === "pickup"
      ? "Pickup"
      : kind === "destination"
        ? "Destination"
        : "Vehicle";
  element.title = `${kindLabel}: ${label}`;
  element.setAttribute("aria-label", element.title);
  element.setAttribute("role", "img");
  return element;
}

function safetyEventMarker(
  label: string,
  eventType: "HARSH_BRAKING" | "HARSH_ACCELERATION",
) {
  const element = document.createElement("button");
  element.type = "button";
  element.className = "request-map-safety-marker";
  element.title = `${eventType === "HARSH_BRAKING" ? "Harsh braking" : "Harsh acceleration"}: ${label}`;
  element.setAttribute("aria-label", element.title);
  return element;
}

function fleetVehicleMarker(
  label: string,
  telemetryState: "live" | "stale" | "offline" | "no_telemetry",
) {
  const element = document.createElement("button");
  element.type = "button";
  element.className = `request-map-marker request-map-marker--vehicle request-map-marker--${telemetryState} request-map-fleet-marker`;
  element.title = `${label} — ${telemetryState === "no_telemetry" ? "No telemetry" : `${telemetryState[0].toUpperCase()}${telemetryState.slice(1)} telemetry`}`;
  element.setAttribute("aria-label", `Open ${label} vehicle details`);
  return element;
}

function searchResultMarker(label: string) {
  const element = document.createElement("div");
  element.className = "fleet-map-search-marker";
  element.title = `Search result: ${label}`;
  element.setAttribute("aria-label", element.title);
  element.setAttribute("role", "img");
  return element;
}

function numberedMarker(sequence: number, label: string) {
  const element = document.createElement("div");
  element.className = "request-map-marker request-map-marker--numbered";
  element.textContent = String(sequence);
  element.title = `Stop ${sequence}: ${label}`;
  element.setAttribute("aria-label", element.title);
  element.setAttribute("role", "img");
  return element;
}

function geofenceLabelMarker(label: string, color: string) {
  const element = document.createElement("button");
  element.type = "button";
  element.className = "fleet-map-geofence-label";
  element.style.setProperty("--geofence-color", color);
  element.textContent = label;
  element.title = `Open geofence: ${label}`;
  element.setAttribute("aria-label", element.title);
  return element;
}

function popupAge(seconds: number) {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

function fleetPopupElement(
  info: FleetPopupInfo,
  actions: {
    close: () => void;
    zoom: () => void;
    replay: () => void;
    replayAvailable: boolean;
  },
) {
  const card = document.createElement("article");
  card.className = "fleet-map-popup-card";
  card.setAttribute("aria-label", `${info.label} map details`);
  const header = document.createElement("header");
  const icon = document.createElement("span");
  icon.className = `fleet-map-popup-icon fleet-map-popup-icon--${info.telemetryState}`;
  icon.setAttribute("aria-hidden", "true");
  const identity = document.createElement("span");
  const plate = document.createElement("strong");
  plate.textContent = info.plateNumber;
  const name = document.createElement("span");
  name.textContent = info.label;
  identity.append(plate, name);
  const close = document.createElement("button");
  close.type = "button";
  close.className = "fleet-map-popup-close";
  close.setAttribute("aria-label", "Close vehicle map details");
  close.textContent = "×";
  close.addEventListener("click", actions.close);
  header.append(icon, identity, close);
  const accent = document.createElement("div");
  accent.className = `fleet-map-popup-accent fleet-map-popup-accent--${info.telemetryState}`;
  const summary = document.createElement("div");
  summary.className = "fleet-map-popup-summary";
  const age = document.createElement("strong");
  age.textContent = popupAge(info.ageSeconds);
  const speed = document.createElement("strong");
  speed.textContent = `Speed: ${info.speedKph} km/h`;
  const updated = document.createElement("span");
  updated.textContent = `${info.telemetrySource === "demo" ? "Demo snapshot" : "Last update"}: ${new Date(info.recordedAt).toLocaleTimeString()}`;
  const location = document.createElement("span");
  location.textContent = `${info.latitude.toFixed(5)}, ${info.longitude.toFixed(5)}`;
  summary.append(age, speed, updated, location);
  const context = document.createElement("div");
  context.className = "fleet-map-popup-context";
  const contextLine = (label: string, value: string) => {
    const line = document.createElement("p");
    const heading = document.createElement("strong");
    heading.textContent = label;
    line.append(heading, document.createTextNode(` ${value}`));
    return line;
  };
  const source = contextLine(
    "Source",
    info.telemetrySource === "demo" ? "Demo telemetry" : "Real telemetry",
  );
  const driver = contextLine("Driver", info.driverName ?? "No active driver");
  const dispatch = contextLine(
    "Dispatch",
    info.assignmentStatus ?? "No active dispatch",
  );
  context.append(source, driver, dispatch);
  const footer = document.createElement("footer");
  const zoom = document.createElement("button");
  zoom.type = "button";
  zoom.textContent = "Zoom to";
  zoom.addEventListener("click", actions.zoom);
  const replay = document.createElement("button");
  replay.type = "button";
  replay.textContent = "Replay";
  replay.disabled = !actions.replayAvailable;
  replay.title = actions.replayAvailable
    ? "Fit recent telemetry trail"
    : "Replay unavailable";
  replay.addEventListener("click", actions.replay);
  footer.append(zoom, replay);
  card.append(header, accent, summary, context, footer);
  return card;
}

export default function RequestMap({
  request,
  route,
  routeState,
  operationalLocation,
  numberedStops,
  fleetLocations,
  fleetTrail,
  fleetPopup,
  safetyEvents,
  onVehicleSelect,
  onVehiclePopupClose,
  onSafetyEventSelect,
  geofences,
  geofenceDraft,
  geofenceDrawing,
  onGeofenceSelect,
  onGeofenceCreateAt,
  onGeofenceDraftMapClick,
}: MapProps) {
  const tomTomKey = import.meta.env.VITE_TOMTOM_MAPS_KEY?.trim() ?? "";
  const containerRef = useRef<HTMLDivElement>(null);
  const settingsRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const mapLoadedRef = useRef(false);
  const appliedStyleRef = useRef<MapStyle | null>(null);
  const markersRef = useRef<Marker[]>([]);
  const searchMarkerRef = useRef<Marker | null>(null);
  const fleetPopupRef = useRef<maplibregl.Popup | null>(null);
  const cameraContextRef = useRef("");
  const geofenceCameraRef = useRef("");
  const [mapLoaded, setMapLoaded] = useState(false);
  const [mapError, setMapError] = useState(false);
  const [styleRevision, setStyleRevision] = useState(0);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const searchListId = useId();
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchSuggestions, setSearchSuggestions] = useState<PlaceSuggestion[]>(
    [],
  );
  const [searchActive, setSearchActive] = useState(-1);
  const [searchStatus, setSearchStatus] = useState<MapSearchStatus>("idle");
  const searchSessionRef = useRef<string | null>(null);
  const searchSelectedRef = useRef<string | null>(null);
  const searchDetailsControllerRef = useRef<AbortController | null>(null);
  const [mapContextPoint, setMapContextPoint] =
    useState<MapContextPoint | null>(null);
  const [geofenceDraftPoint, setGeofenceDraftPoint] = useState<{
    latitude: number;
    longitude: number;
  } | null>(null);
  const [mapStyle, setMapStyle] = useState<MapStyle>(savedStyle);
  const initialMapStyleRef = useRef(mapStyle);
  const [trafficEnabled, setTrafficEnabled] = useState(() =>
    savedToggle(trafficPreferenceKey),
  );
  const [incidentsEnabled, setIncidentsEnabled] = useState(() =>
    savedToggle(incidentsPreferenceKey),
  );
  const trafficEnabledRef = useRef(trafficEnabled);
  const incidentsEnabledRef = useRef(incidentsEnabled);
  const fleetLocationsRef = useRef(fleetLocations);
  const onVehiclePopupCloseRef = useRef(onVehiclePopupClose);
  const geofenceDrawingRef = useRef(geofenceDrawing);
  const onGeofenceDraftMapClickRef = useRef(onGeofenceDraftMapClick);
  useEffect(() => {
    trafficEnabledRef.current = trafficEnabled;
  }, [trafficEnabled]);
  useEffect(() => {
    incidentsEnabledRef.current = incidentsEnabled;
  }, [incidentsEnabled]);
  useEffect(() => {
    fleetLocationsRef.current = fleetLocations;
  }, [fleetLocations]);
  useEffect(() => {
    onVehiclePopupCloseRef.current = onVehiclePopupClose;
  }, [onVehiclePopupClose]);
  useEffect(() => {
    geofenceDrawingRef.current = geofenceDrawing;
  }, [geofenceDrawing]);
  useEffect(() => {
    onGeofenceDraftMapClickRef.current = onGeofenceDraftMapClick;
  }, [onGeofenceDraftMapClick]);

  useEffect(() => {
    if (!settingsOpen) return;
    const closeOutside = (event: MouseEvent) => {
      if (!settingsRef.current?.contains(event.target as Node))
        setSettingsOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSettingsOpen(false);
    };
    document.addEventListener("mousedown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [settingsOpen]);

  useEffect(() => {
    if (!searchOpen) return;
    searchInputRef.current?.focus();
    const closeOutside = (event: PointerEvent) => {
      if (!searchRef.current?.contains(event.target as Node))
        setSearchOpen(false);
    };
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setSearchOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [searchOpen]);

  useEffect(() => {
    const query = searchQuery.trim();
    if (
      !searchOpen ||
      searchSelectedRef.current === searchQuery ||
      query.length < 3
    )
      return;
    searchSessionRef.current ??= newMapSearchSession();
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void suggestPlaces(query, searchSessionRef.current!, controller.signal)
        .then((result) => {
          setSearchSuggestions(result.results.slice(0, 5));
          setSearchActive(-1);
          setSearchStatus(result.results.length ? "idle" : "empty");
        })
        .catch((error) => {
          if (error instanceof DOMException && error.name === "AbortError")
            return;
          setSearchSuggestions([]);
          setSearchStatus(
            error instanceof ApiError && [429, 503].includes(error.status)
              ? "unavailable"
              : "error",
          );
        });
    }, 300);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [searchOpen, searchQuery]);

  useEffect(
    () => () => {
      searchDetailsControllerRef.current?.abort();
      searchMarkerRef.current?.remove();
      searchMarkerRef.current = null;
    },
    [],
  );

  useEffect(() => {
    if (!mapContextPoint) return;
    const closeOutside = (event: MouseEvent) => {
      if (!(event.target as Element).closest?.(".fleet-map-context-menu"))
        setMapContextPoint(null);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMapContextPoint(null);
    };
    document.addEventListener("mousedown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [mapContextPoint]);

  useEffect(() => {
    try {
      localStorage.setItem(stylePreferenceKey, mapStyle);
      localStorage.setItem(trafficPreferenceKey, String(trafficEnabled));
      localStorage.setItem(incidentsPreferenceKey, String(incidentsEnabled));
    } catch {
      /* preferences are optional */
    }
  }, [mapStyle, trafficEnabled, incidentsEnabled]);

  useEffect(() => {
    if (!tomTomKey || !containerRef.current || mapRef.current) return;
    const initialMapStyle = initialMapStyleRef.current;
    appliedStyleRef.current = initialMapStyle;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: styleUrl(initialMapStyle),
      center: fallbackCenter,
      zoom: fallbackZoom,
      pitch: 0,
      bearing: 0,
      attributionControl: false,
      transformRequest: (url) => {
        try {
          if (new URL(url).hostname === "api.tomtom.com")
            return { url, headers: { "TomTom-Api-Key": tomTomKey } };
        } catch {
          /* relative internal URLs do not receive TomTom credentials */
        }
        return { url };
      },
    });
    mapRef.current = map;
    map.dragRotate.disable();
    map.touchZoomRotate.disableRotation();

    const reconcileOperationalLayers = () => {
      if (!map.getSource(trafficSourceId))
        map.addSource(trafficSourceId, {
          type: "raster",
          tiles: [
            "https://api.tomtom.com/maps/orbis/traffic/flow/raster/tile/{z}/{x}/{y}?apiVersion=2&style=light&tileSize=256",
          ],
          tileSize: 256,
          maxzoom: 22,
          attribution: "© TomTom Traffic",
        });
      if (!map.getLayer(trafficLayerId))
        map.addLayer({
          id: trafficLayerId,
          type: "raster",
          source: trafficSourceId,
          layout: {
            visibility: trafficEnabledRef.current ? "visible" : "none",
          },
          paint: { "raster-opacity": 0.5 },
        });
      if (!map.getSource(incidentsSourceId))
        map.addSource(incidentsSourceId, {
          type: "raster",
          tiles: [
            "https://api.tomtom.com/maps/orbis/traffic/incidents/raster/tile/{z}/{x}/{y}?apiVersion=2&style=light&tileSize=256",
          ],
          tileSize: 256,
          maxzoom: 22,
          attribution: "© TomTom Traffic",
        });
      if (!map.getLayer(incidentsLayerId))
        map.addLayer({
          id: incidentsLayerId,
          type: "raster",
          source: incidentsSourceId,
          layout: {
            visibility: incidentsEnabledRef.current ? "visible" : "none",
          },
        });
      if (!map.getSource(routeSourceId))
        map.addSource(routeSourceId, {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
      if (!map.getLayer(routeCasingLayerId))
        map.addLayer({
          id: routeCasingLayerId,
          type: "line",
          source: routeSourceId,
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": "#fffdf9",
            "line-width": 10,
            "line-opacity": 0.72,
          },
        });
      if (!map.getLayer(routeLayerId))
        map.addLayer({
          id: routeLayerId,
          type: "line",
          source: routeSourceId,
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": "#263d73",
            "line-width": 6,
            "line-opacity": 0.96,
          },
        });
      if (fleetLocationsRef.current !== undefined) {
        if (!map.getSource(geofenceSourceId))
          map.addSource(geofenceSourceId, {
            type: "geojson",
            data: { type: "FeatureCollection", features: [] },
          });
        if (!map.getLayer(geofenceFillLayerId))
          map.addLayer({
            id: geofenceFillLayerId,
            type: "fill",
            source: geofenceSourceId,
            paint: {
              "fill-color": ["get", "color"],
              "fill-opacity": ["case", ["get", "selected"], 0.25, 0.12],
            },
          });
        if (!map.getLayer(geofenceLineLayerId))
          map.addLayer({
            id: geofenceLineLayerId,
            type: "line",
            source: geofenceSourceId,
            layout: { "line-cap": "round", "line-join": "round" },
            paint: {
              "line-color": ["get", "color"],
              "line-width": ["case", ["get", "selected"], 4, 2],
              "line-dasharray": [2, 1],
            },
          });
        if (!map.getSource(geofenceDraftSourceId))
          map.addSource(geofenceDraftSourceId, {
            type: "geojson",
            data: { type: "FeatureCollection", features: [] },
          });
        if (!map.getLayer(geofenceDraftFillLayerId))
          map.addLayer({
            id: geofenceDraftFillLayerId,
            type: "fill",
            source: geofenceDraftSourceId,
            filter: ["==", ["geometry-type"], "Polygon"],
            paint: { "fill-color": ["get", "color"], "fill-opacity": 0.22 },
          });
        if (!map.getLayer(geofenceDraftLineLayerId))
          map.addLayer({
            id: geofenceDraftLineLayerId,
            type: "line",
            source: geofenceDraftSourceId,
            filter: [
              "in",
              ["geometry-type"],
              ["literal", ["LineString", "Polygon"]],
            ],
            paint: {
              "line-color": ["get", "color"],
              "line-width": 3,
              "line-dasharray": [1.5, 1],
            },
          });
        if (!map.getLayer(geofenceDraftPointLayerId))
          map.addLayer({
            id: geofenceDraftPointLayerId,
            type: "circle",
            source: geofenceDraftSourceId,
            filter: ["==", ["geometry-type"], "Point"],
            paint: {
              "circle-radius": 5,
              "circle-color": "#fff",
              "circle-stroke-color": ["get", "color"],
              "circle-stroke-width": 3,
            },
          });
      }
      mapLoadedRef.current = true;
      setMapError(false);
      setMapLoaded(true);
      setStyleRevision((value) => value + 1);
    };
    const onError = (event?: { error?: Error }) => {
      const message = event?.error?.message.toLowerCase() ?? "";
      if (mapLoadedRef.current && /sprite|glyph/.test(message)) return;
      setMapError(true);
    };
    const onMapClick = (event: {
      point: { x: number; y: number };
      lngLat: { lng: number; lat: number };
    }) => {
      if (fleetLocationsRef.current === undefined) return;
      if (geofenceDrawingRef.current) {
        onGeofenceDraftMapClickRef.current?.({
          latitude: event.lngLat.lat,
          longitude: event.lngLat.lng,
        });
        return;
      }
      const width = containerRef.current?.clientWidth ?? 0;
      const height = containerRef.current?.clientHeight ?? 0;
      setMapContextPoint({
        x: Math.max(
          8,
          Math.min(event.point.x, width > 230 ? width - 222 : event.point.x),
        ),
        y: Math.max(
          8,
          Math.min(event.point.y, height > 190 ? height - 182 : event.point.y),
        ),
        latitude: event.lngLat.lat,
        longitude: event.lngLat.lng,
      });
      onVehiclePopupCloseRef.current?.();
    };
    const closeMapContext = () => setMapContextPoint(null);
    map.on("load", reconcileOperationalLayers);
    map.on("style.load", reconcileOperationalLayers);
    map.on("error", onError);
    map.on("click", onMapClick);
    map.on("movestart", closeMapContext);
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(() => map.resize());
    observer?.observe(containerRef.current);

    return () => {
      observer?.disconnect();
      markersRef.current.forEach((marker) => marker.remove());
      markersRef.current = [];
      searchMarkerRef.current?.remove();
      searchMarkerRef.current = null;
      fleetPopupRef.current?.remove();
      fleetPopupRef.current = null;
      map.off("load", reconcileOperationalLayers);
      map.off("style.load", reconcileOperationalLayers);
      map.off("error", onError);
      map.off("click", onMapClick);
      map.off("movestart", closeMapContext);
      map.remove();
      mapRef.current = null;
      mapLoadedRef.current = false;
    };
  }, [tomTomKey]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || appliedStyleRef.current === mapStyle) return;
    appliedStyleRef.current = mapStyle;
    mapLoadedRef.current = false;
    setMapLoaded(false);
    setMapError(false);
    map.setStyle(styleUrl(mapStyle));
  }, [mapStyle]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || !map.getLayer(trafficLayerId)) return;
    map.setLayoutProperty(
      trafficLayerId,
      "visibility",
      trafficEnabled ? "visible" : "none",
    );
  }, [mapLoaded, trafficEnabled]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || !map.getLayer(incidentsLayerId)) return;
    map.setLayoutProperty(
      incidentsLayerId,
      "visibility",
      incidentsEnabled ? "visible" : "none",
    );
  }, [incidentsEnabled, mapLoaded]);

  useEffect(() => {
    const map = mapRef.current;
    const selected = geofences?.find(
      (item) => item.selected && item.vertices.length >= 3,
    );
    if (
      !map ||
      !mapLoaded ||
      !selected ||
      geofenceCameraRef.current === selected.id
    )
      return;
    geofenceCameraRef.current = selected.id;
    const coordinates = selected.vertices.map(
      (point) => [point.longitude, point.latitude] as [number, number],
    );
    const bounds = coordinates.reduce(
      (result, coordinate) => result.extend(coordinate),
      new maplibregl.LngLatBounds(coordinates[0], coordinates[0]),
    );
    map.fitBounds(bounds as LngLatBoundsLike, {
      padding: 90,
      maxZoom: 17,
      duration: 450,
    });
  }, [geofences, mapLoaded]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || !map.getSource(routeSourceId)) return;
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];
    fleetPopupRef.current?.remove();
    fleetPopupRef.current = null;
    const pickup = request
      ? validCoordinate(request.pickup_latitude, request.pickup_longitude)
      : null;
    const destination = request
      ? validCoordinate(
          request.destination_latitude,
          request.destination_longitude,
        )
      : null;
    const routeCoordinates = route?.geometry?.coordinates ?? [];
    const routeData =
      routeCoordinates.length >= 2
        ? {
            type: "Feature" as const,
            properties: {},
            geometry: {
              type: "LineString" as const,
              coordinates: routeCoordinates,
            },
          }
        : { type: "FeatureCollection" as const, features: [] };
    (map.getSource(routeSourceId) as GeoJSONSource).setData(routeData);
    if (fleetLocations !== undefined) {
      if (!map.getSource(fleetTrailSourceId))
        map.addSource(fleetTrailSourceId, {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
      if (!map.getLayer(fleetTrailLineLayerId))
        map.addLayer({
          id: fleetTrailLineLayerId,
          type: "line",
          source: fleetTrailSourceId,
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": "#177b8f",
            "line-width": 3,
            "line-opacity": 0.72,
            "line-dasharray": [1.2, 1.5],
          },
        });
      if (!map.getLayer(fleetTrailPointLayerId))
        map.addLayer({
          id: fleetTrailPointLayerId,
          type: "circle",
          source: fleetTrailSourceId,
          paint: {
            "circle-radius": 3,
            "circle-color": "#fff",
            "circle-stroke-color": "#177b8f",
            "circle-stroke-width": 2,
          },
        });
      const trailCoordinates = (fleetTrail ?? []).flatMap((point) => {
        const coordinate = validCoordinate(point.latitude, point.longitude);
        return coordinate ? [coordinate] : [];
      });
      const trailData =
        trailCoordinates.length >= 2
          ? {
              type: "Feature" as const,
              properties: {},
              geometry: {
                type: "LineString" as const,
                coordinates: trailCoordinates,
              },
            }
          : { type: "FeatureCollection" as const, features: [] };
      (map.getSource(fleetTrailSourceId) as GeoJSONSource).setData(trailData);
      const geofenceFeatures = (geofences ?? [])
        .filter((item) => item.showOnMap && item.vertices.length >= 3)
        .map((item) => ({
          type: "Feature" as const,
          properties: {
            id: item.id,
            color: item.color,
            selected: Boolean(item.selected),
          },
          geometry: {
            type: "Polygon" as const,
            coordinates: [
              [
                ...item.vertices.map((point) => [
                  point.longitude,
                  point.latitude,
                ]),
                [item.vertices[0].longitude, item.vertices[0].latitude],
              ],
            ],
          },
        }));
      (map.getSource(geofenceSourceId) as GeoJSONSource | undefined)?.setData({
        type: "FeatureCollection",
        features: geofenceFeatures,
      });
      const draftFeatures: Array<Record<string, unknown>> = [];
      if (geofenceDraft?.vertices.length) {
        const coordinates = geofenceDraft.vertices.map((point) => [
          point.longitude,
          point.latitude,
        ]);
        if (coordinates.length >= 3)
          draftFeatures.push({
            type: "Feature",
            properties: { color: geofenceDraft.color },
            geometry: {
              type: "Polygon",
              coordinates: [[...coordinates, coordinates[0]]],
            },
          });
        else if (coordinates.length >= 2)
          draftFeatures.push({
            type: "Feature",
            properties: { color: geofenceDraft.color },
            geometry: { type: "LineString", coordinates },
          });
        coordinates.forEach((coordinate) =>
          draftFeatures.push({
            type: "Feature",
            properties: { color: geofenceDraft.color },
            geometry: { type: "Point", coordinates: coordinate },
          }),
        );
      }
      (
        map.getSource(geofenceDraftSourceId) as GeoJSONSource | undefined
      )?.setData({
        type: "FeatureCollection",
        features: draftFeatures,
      } as unknown as GeoJSON.FeatureCollection);
    }
    const fleetPoints = (fleetLocations ?? []).flatMap((location) => {
      const coordinate = validCoordinate(location.latitude, location.longitude);
      if (!coordinate) return [];
      const element = fleetVehicleMarker(
        location.label,
        location.telemetryState,
      );
      if (location.selected)
        element.classList.add("request-map-marker--selected");
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        onVehicleSelect?.(location.deviceId);
      });
      markersRef.current.push(
        new maplibregl.Marker({ element, anchor: "center" })
          .setLngLat(coordinate)
          .addTo(map),
      );
      if (fleetPopup?.deviceId === location.deviceId) {
        const replayCoordinates = (fleetTrail ?? []).flatMap((point) => {
          const replayCoordinate = validCoordinate(
            point.latitude,
            point.longitude,
          );
          return replayCoordinate ? [replayCoordinate] : [];
        });
        const popup = new maplibregl.Popup({
          closeButton: false,
          closeOnClick: false,
          offset: 18,
          maxWidth: "360px",
          className: "fleet-map-popup",
        })
          .setLngLat(coordinate)
          .setDOMContent(
            fleetPopupElement(fleetPopup, {
              close: () => onVehiclePopupClose?.(),
              zoom: () =>
                map.jumpTo({
                  center: coordinate,
                  zoom: 17,
                  bearing: 0,
                  pitch: 0,
                }),
              replay: () => {
                if (replayCoordinates.length < 2) return;
                const replayBounds = replayCoordinates.reduce(
                  (result, point) => result.extend(point),
                  new maplibregl.LngLatBounds(
                    replayCoordinates[0],
                    replayCoordinates[0],
                  ),
                );
                map.fitBounds(replayBounds as LngLatBoundsLike, {
                  padding: 80,
                  maxZoom: 17,
                  duration: 500,
                });
              },
              replayAvailable: replayCoordinates.length >= 2,
            }),
          )
          .addTo(map);
        fleetPopupRef.current = popup;
      }
      return [coordinate];
    });
    (safetyEvents ?? []).forEach((event) => {
      const coordinate = validCoordinate(event.latitude, event.longitude);
      if (!coordinate) return;
      const element = safetyEventMarker(event.vehicle_name, event.event_type);
      element.addEventListener("click", (clickEvent) => {
        clickEvent.stopPropagation();
        onSafetyEventSelect?.(event.event_id);
      });
      markersRef.current.push(
        new maplibregl.Marker({ element, anchor: "center" })
          .setLngLat(coordinate)
          .addTo(map),
      );
    });
    (geofences ?? [])
      .filter((item) => item.showOnMap)
      .forEach((geofence) => {
        const element = geofenceLabelMarker(geofence.name, geofence.color);
        element.classList.toggle("selected", Boolean(geofence.selected));
        element.addEventListener("click", (clickEvent) => {
          clickEvent.stopPropagation();
          onGeofenceSelect?.(geofence.id);
        });
        markersRef.current.push(
          new maplibregl.Marker({ element, anchor: "bottom" })
            .setLngLat([geofence.center.longitude, geofence.center.latitude])
            .addTo(map),
        );
      });
    if (!request || !pickup || !destination) {
      const cameraContext = fleetLocations !== undefined ? "fleet" : "empty";
      if (cameraContextRef.current !== cameraContext) {
        cameraContextRef.current = cameraContext;
        if (fleetPoints.length === 1)
          map.jumpTo({
            center: fleetPoints[0],
            zoom: 15,
            bearing: 0,
            pitch: 0,
          });
        else if (fleetPoints.length > 1) {
          const fleetBounds = fleetPoints.reduce(
            (result, coordinate) => result.extend(coordinate),
            new maplibregl.LngLatBounds(fleetPoints[0], fleetPoints[0]),
          );
          map.fitBounds(fleetBounds as LngLatBoundsLike, {
            padding: 55,
            maxZoom: 15,
            duration: 0,
          });
        } else
          map.jumpTo({
            center: fallbackCenter,
            zoom: fallbackZoom,
            bearing: 0,
            pitch: 0,
          });
      }
      return;
    }
    const stopCoordinates = (numberedStops ?? []).flatMap((stop) => {
      const coordinate = validCoordinate(stop.latitude, stop.longitude);
      if (!coordinate) return [];
      markersRef.current.push(
        new maplibregl.Marker({
          element: numberedMarker(stop.sequence, stop.label),
          anchor: "center",
        })
          .setLngLat(coordinate)
          .addTo(map),
      );
      return [coordinate];
    });
    if (stopCoordinates.length === 0)
      markersRef.current.push(
        new maplibregl.Marker({
          element: markerElement("pickup", request.pickup_name),
          anchor: "center",
        })
          .setLngLat(pickup)
          .addTo(map),
        new maplibregl.Marker({
          element: markerElement("destination", request.destination_name),
          anchor: "center",
        })
          .setLngLat(destination)
          .addTo(map),
      );
    const vehicleLocation = operationalLocation
      ? validCoordinate(
          operationalLocation.latitude,
          operationalLocation.longitude,
        )
      : null;
    if (vehicleLocation && operationalLocation)
      markersRef.current.push(
        new maplibregl.Marker({
          element: markerElement("vehicle", operationalLocation.label),
          anchor: "center",
        })
          .setLngLat(vehicleLocation)
          .addTo(map),
      );
    const requestPoints =
      stopCoordinates.length > 0
        ? stopCoordinates
        : routeCoordinates.length >= 2
          ? [...routeCoordinates, pickup, destination]
          : [pickup, destination];
    const cameraPoints = [...requestPoints, ...fleetPoints];
    if (vehicleLocation) cameraPoints.push(vehicleLocation);
    const cameraContext = `request:${pickup.join(",")}:${destination.join(",")}:${requestPoints.map((point) => point.join(",")).join(";")}`;
    if (cameraContextRef.current !== cameraContext) {
      cameraContextRef.current = cameraContext;
      const bounds = cameraPoints.reduce(
        (result, coordinate) => result.extend(coordinate),
        new maplibregl.LngLatBounds(cameraPoints[0], cameraPoints[0]),
      );
      map.fitBounds(bounds as LngLatBoundsLike, {
        padding: { top: 55, right: 320, bottom: 55, left: 55 },
        maxZoom: 16,
        duration: 0,
      });
    }
  }, [
    fleetLocations,
    fleetPopup,
    fleetTrail,
    geofenceDraft,
    geofences,
    mapLoaded,
    numberedStops,
    onGeofenceSelect,
    onSafetyEventSelect,
    onVehiclePopupClose,
    onVehicleSelect,
    operationalLocation,
    request,
    route?.geometry?.coordinates,
    safetyEvents,
    styleRevision,
  ]);

  const findNearestFleetAsset = () => {
    if (!mapContextPoint) return;
    const nearest = (fleetLocations ?? []).reduce<
      | (NonNullable<MapProps["fleetLocations"]>[number] & { distance: number })
      | null
    >((current, location) => {
      const latitudeScale = Math.cos(
        (mapContextPoint.latitude * Math.PI) / 180,
      );
      const longitudeDelta =
        (location.longitude - mapContextPoint.longitude) * latitudeScale;
      const latitudeDelta = location.latitude - mapContextPoint.latitude;
      const distance =
        longitudeDelta * longitudeDelta + latitudeDelta * latitudeDelta;
      return !current || distance < current.distance
        ? { ...location, distance }
        : current;
    }, null);
    setMapContextPoint(null);
    if (!nearest) return;
    onVehicleSelect?.(nearest.deviceId);
    mapRef.current?.jumpTo({
      center: [nearest.longitude, nearest.latitude],
      zoom: 16,
      bearing: 0,
      pitch: 0,
    });
  };

  const zoomToContextPoint = () => {
    if (!mapContextPoint) return;
    mapRef.current?.jumpTo({
      center: [mapContextPoint.longitude, mapContextPoint.latitude],
      zoom: 17,
      bearing: 0,
      pitch: 0,
    });
    setMapContextPoint(null);
  };

  const createGeofenceDraft = () => {
    if (!mapContextPoint) return;
    if (onGeofenceCreateAt) {
      onGeofenceCreateAt({
        latitude: mapContextPoint.latitude,
        longitude: mapContextPoint.longitude,
      });
      setMapContextPoint(null);
      return;
    }
    setGeofenceDraftPoint({
      latitude: mapContextPoint.latitude,
      longitude: mapContextPoint.longitude,
    });
    setMapContextPoint(null);
  };

  const changeMapSearch = (value: string) => {
    searchDetailsControllerRef.current?.abort();
    searchSelectedRef.current = null;
    setSearchQuery(value);
    setSearchActive(-1);
    if (value.trim().length < 3) {
      setSearchSuggestions([]);
      setSearchStatus("idle");
    } else setSearchStatus("loading");
  };

  const selectMapSearchResult = async (suggestion: PlaceSuggestion) => {
    const sessionId = searchSessionRef.current;
    if (!sessionId) return;
    searchDetailsControllerRef.current?.abort();
    const controller = new AbortController();
    searchDetailsControllerRef.current = controller;
    setSearchStatus("loading");
    try {
      const detail = await getPlaceDetails(
        suggestion.type,
        suggestion.id,
        sessionId,
        controller.signal,
      );
      const coordinate: [number, number] = [detail.longitude, detail.latitude];
      searchMarkerRef.current?.remove();
      if (mapRef.current)
        searchMarkerRef.current = new maplibregl.Marker({
          element: searchResultMarker(detail.title),
          anchor: "bottom",
        })
          .setLngLat(coordinate)
          .addTo(mapRef.current);
      mapRef.current?.jumpTo({
        center: coordinate,
        zoom: 17,
        bearing: 0,
        pitch: 0,
      });
      searchSelectedRef.current = detail.display_address;
      setSearchQuery(detail.display_address);
      setSearchSuggestions([]);
      setSearchActive(-1);
      setSearchStatus("idle");
      setMapContextPoint(null);
      searchSessionRef.current = null;
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError"))
        setSearchStatus("select-error");
    } finally {
      if (searchDetailsControllerRef.current === controller)
        searchDetailsControllerRef.current = null;
    }
  };

  const mapSearchKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      setSearchOpen(false);
      setSearchActive(-1);
      return;
    }
    if (!searchSuggestions.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSearchActive((value) =>
        Math.min(value + 1, searchSuggestions.length - 1),
      );
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setSearchActive((value) => Math.max(value - 1, 0));
    } else if (event.key === "Enter" && searchActive >= 0) {
      event.preventDefault();
      void selectMapSearchResult(searchSuggestions[searchActive]);
    }
  };

  return (
    <div
      className={`request-map tomtom-request-map maplibre-request-map ${request ? "" : "request-map--empty"}`}
    >
      <div
        ref={containerRef}
        className="request-map-canvas"
        data-testid="request-map"
        aria-label="Transport request map"
      />
      {!tomTomKey && (
        <div className="request-map-state" role="alert">
          TomTom map key is not configured.
        </div>
      )}
      {tomTomKey && !mapLoaded && !mapError && (
        <div className="request-map-loading" role="status">
          <LoadingIndicator size="sm" message="Loading TomTom map…" />
        </div>
      )}
      {tomTomKey && mapError && (
        <div className="request-map-tile-error" role="alert">
          Unable to load TomTom map.
        </div>
      )}
      {mapContextPoint && (
        <div
          className="fleet-map-context-menu"
          role="menu"
          aria-label="Map actions"
          style={{ left: mapContextPoint.x, top: mapContextPoint.y }}
        >
          <header>Map</header>
          <button type="button" role="menuitem" onClick={findNearestFleetAsset}>
            Nearest fleet asset
          </button>
          <button type="button" role="menuitem" onClick={zoomToContextPoint}>
            Zoom to
          </button>
          <button type="button" role="menuitem" onClick={createGeofenceDraft}>
            Create geofence
          </button>
        </div>
      )}
      {geofenceDraftPoint && (
        <div className="fleet-geofence-draft-notice" role="status">
          <button
            type="button"
            aria-label="Dismiss geofence notice"
            onClick={() => setGeofenceDraftPoint(null)}
          >
            ×
          </button>
          <strong>Geofence center selected</strong>
          <span>
            {geofenceDraftPoint.latitude.toFixed(5)},{" "}
            {geofenceDraftPoint.longitude.toFixed(5)}
          </span>
          <small>Not saved. Geofence persistence is not configured yet.</small>
        </div>
      )}
      {tomTomKey && fleetLocations !== undefined && (
        <div
          className={`fleet-map-search ${searchOpen ? "fleet-map-search--open" : ""}`}
          ref={searchRef}
        >
          <button
            type="button"
            className="fleet-map-search-toggle"
            title="Search places"
            aria-label={searchOpen ? "Close map search" : "Search map places"}
            aria-expanded={searchOpen}
            onClick={() => {
              setSearchOpen((value) => !value);
              setSettingsOpen(false);
              setMapContextPoint(null);
            }}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="10.8" cy="10.8" r="6.2" />
              <path d="m15.4 15.4 4.1 4.1" />
            </svg>
          </button>
          {searchOpen && (
            <div className="fleet-map-search-panel">
              <input
                ref={searchInputRef}
                type="search"
                value={searchQuery}
                placeholder="Search a place"
                aria-label="Search map places"
                role="combobox"
                aria-autocomplete="list"
                aria-controls={searchListId}
                aria-expanded={searchQuery.trim().length >= 3}
                aria-activedescendant={
                  searchActive >= 0
                    ? `${searchListId}-${searchActive}`
                    : undefined
                }
                onChange={(event) => changeMapSearch(event.target.value)}
                onKeyDown={mapSearchKeyDown}
              />
              {searchQuery.trim().length >= 3 && (
                <div
                  id={searchListId}
                  className="fleet-map-search-results"
                  role="listbox"
                  aria-label="Map place suggestions"
                >
                  {searchStatus === "loading" ? (
                    <div className="fleet-map-search-state" role="status">
                      Searching places…
                    </div>
                  ) : searchStatus === "empty" ? (
                    <div className="fleet-map-search-state">
                      No matching places found.
                    </div>
                  ) : searchStatus === "unavailable" ? (
                    <div className="fleet-map-search-state" role="alert">
                      Place search is temporarily unavailable.
                    </div>
                  ) : searchStatus === "error" ? (
                    <div className="fleet-map-search-state" role="alert">
                      Unable to search places.
                    </div>
                  ) : searchStatus === "select-error" ? (
                    <div className="fleet-map-search-state" role="alert">
                      Unable to open this place.
                    </div>
                  ) : (
                    searchSuggestions.map((suggestion, index) => (
                      <button
                        type="button"
                        role="option"
                        id={`${searchListId}-${index}`}
                        aria-selected={searchActive === index}
                        className={searchActive === index ? "active" : ""}
                        key={`${suggestion.type}:${suggestion.id}`}
                        onMouseEnter={() => setSearchActive(index)}
                        onClick={() => void selectMapSearchResult(suggestion)}
                      >
                        <strong>{suggestion.title}</strong>
                        {suggestion.subtitles.map((value) => (
                          <small key={value}>{value}</small>
                        ))}
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
      {tomTomKey && (
        <div className="map-settings" ref={settingsRef}>
          <button
            type="button"
            className="map-settings-button btn btn-sm btn-outline-secondary"
            title="Map settings"
            aria-label="Map settings"
            aria-expanded={settingsOpen}
            onClick={() => setSettingsOpen((value) => !value)}
          >
            ⋮
          </button>
          {settingsOpen && (
            <div
              className="map-settings-popover"
              role="dialog"
              aria-label="Map settings"
            >
              <header>
                <strong>Map settings</strong>
                <button
                  type="button"
                  className="map-settings-close btn-close"
                  aria-label="Close map settings"
                  onClick={() => setSettingsOpen(false)}
                >
                  ×
                </button>
              </header>
              <fieldset>
                <legend>Map style</legend>
                {Object.entries(mapStyles).map(([value, option]) => (
                  <label key={value}>
                    <input
                      type="radio"
                      name="transport-map-style"
                      value={value}
                      checked={mapStyle === value}
                      onChange={() => setMapStyle(value as MapStyle)}
                    />
                    {option.label}
                  </label>
                ))}
              </fieldset>
              <fieldset>
                <legend>Layers</legend>
                <label>
                  <input
                    type="checkbox"
                    checked={trafficEnabled}
                    onChange={(event) =>
                      setTrafficEnabled(event.target.checked)
                    }
                  />
                  Live traffic
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={incidentsEnabled}
                    onChange={(event) =>
                      setIncidentsEnabled(event.target.checked)
                    }
                  />
                  Traffic incidents
                </label>
              </fieldset>
            </div>
          )}
        </div>
      )}
      {request && routeState === "loading" && (
        <div className="request-route-state" role="status">
          <LoadingIndicator size="sm" message="Calculating route…" />
        </div>
      )}
      {request && routeState === "error" && (
        <div
          className="request-route-state request-route-state--error"
          role="status"
        >
          Route unavailable
        </div>
      )}
      {fleetLocations !== undefined ? (
        <div
          className="map-legend fleet-map-legend"
          aria-label="Fleet map legend"
        >
          <span>
            <i className="fleet-legend-live" />
            Live
          </span>
          <span>
            <i className="fleet-legend-stale" />
            Stale
          </span>
          <span>
            <i className="fleet-legend-offline" />
            Offline
          </span>
          <span>
            <i className="fleet-legend-none" />
            No telemetry
          </span>
          <span>
            <i className="fleet-legend-selected" />
            Selected vehicle
          </span>
          <span>
            <i className="fleet-legend-route" />
            Active dispatch route
          </span>
          <span>
            <i className="fleet-legend-trail" />
            Recent breadcrumb trail
          </span>
          {(safetyEvents?.length ?? 0) > 0 && (
            <span>
              <i className="fleet-legend-safety" />
              Safety event
            </span>
          )}
        </div>
      ) : request ? (
        <div className="map-legend">
          <span>
            <i className="pickup-dot" />
            {request.pickup_name}
          </span>
          <span>
            <i className="destination-dot" />
            {request.destination_name}
          </span>
        </div>
      ) : (
        <div className="request-map-empty-overlay">No request selected</div>
      )}
    </div>
  );
}
