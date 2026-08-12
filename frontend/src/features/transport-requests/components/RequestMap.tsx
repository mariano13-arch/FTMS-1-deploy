import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, LngLatBoundsLike, Map as MapLibreMap, Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { TransportRequestBase, TransportRoute } from "../types";

const fallbackCenter: [number, number] = [121.0286, 14.5652];
const fallbackZoom = 13;
const trafficSourceId = "tomtom-traffic-source";
const trafficLayerId = "tomtom-traffic-layer";
const incidentsSourceId = "tomtom-incidents-source";
const incidentsLayerId = "tomtom-incidents-layer";
const routeSourceId = "request-route-source";
const routeCasingLayerId = "request-route-casing";
const routeLayerId = "request-route-line";
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

type MapProps = {
  request: TransportRequestBase | null;
  route?: TransportRoute | null;
  routeState?: "idle" | "loading" | "ready" | "error";
};

function styleUrl(style: MapStyle) {
  return `https://api.tomtom.com/maps/orbis/assets/styles/0.*/style?apiVersion=1&map=${mapStyles[style].tomTomStyle}`;
}

function savedStyle(): MapStyle {
  try {
    const value = localStorage.getItem(stylePreferenceKey);
    return value && value in mapStyles ? value as MapStyle : "street";
  } catch { return "street"; }
}

function savedToggle(key: string) {
  try {
    const value = localStorage.getItem(key);
    return value === "false" ? false : true;
  } catch { return true; }
}

function validCoordinate(latitude: unknown, longitude: unknown): [number, number] | null {
  const lat = Number(latitude);
  const lng = Number(longitude);
  return Number.isFinite(lat) && Number.isFinite(lng) ? [lng, lat] : null;
}

function markerElement(kind: "pickup" | "destination", label: string) {
  const element = document.createElement("div");
  element.className = `request-map-marker request-map-marker--${kind}`;
  element.title = `${kind === "pickup" ? "Pickup" : "Destination"}: ${label}`;
  element.setAttribute("aria-label", element.title);
  element.setAttribute("role", "img");
  return element;
}

export default function RequestMap({ request, route, routeState }: MapProps) {
  const tomTomKey = import.meta.env.VITE_TOMTOM_MAPS_KEY?.trim() ?? "";
  const containerRef = useRef<HTMLDivElement>(null);
  const settingsRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const mapLoadedRef = useRef(false);
  const appliedStyleRef = useRef<MapStyle | null>(null);
  const markersRef = useRef<Marker[]>([]);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [mapError, setMapError] = useState(false);
  const [styleRevision, setStyleRevision] = useState(0);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [mapStyle, setMapStyle] = useState<MapStyle>(savedStyle);
  const initialMapStyleRef = useRef(mapStyle);
  const [trafficEnabled, setTrafficEnabled] = useState(() => savedToggle(trafficPreferenceKey));
  const [incidentsEnabled, setIncidentsEnabled] = useState(() => savedToggle(incidentsPreferenceKey));
  const trafficEnabledRef = useRef(trafficEnabled);
  const incidentsEnabledRef = useRef(incidentsEnabled);
  useEffect(() => { trafficEnabledRef.current = trafficEnabled; }, [trafficEnabled]);
  useEffect(() => { incidentsEnabledRef.current = incidentsEnabled; }, [incidentsEnabled]);

  useEffect(() => {
    if (!settingsOpen) return;
    const closeOutside = (event: MouseEvent) => { if (!settingsRef.current?.contains(event.target as Node)) setSettingsOpen(false); };
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setSettingsOpen(false); };
    document.addEventListener("mousedown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => { document.removeEventListener("mousedown", closeOutside); document.removeEventListener("keydown", closeOnEscape); };
  }, [settingsOpen]);

  useEffect(() => { try { localStorage.setItem(stylePreferenceKey, mapStyle); } catch { /* preferences are optional */ } }, [mapStyle]);
  useEffect(() => { try { localStorage.setItem(trafficPreferenceKey, String(trafficEnabled)); } catch { /* preferences are optional */ } }, [trafficEnabled]);
  useEffect(() => { try { localStorage.setItem(incidentsPreferenceKey, String(incidentsEnabled)); } catch { /* preferences are optional */ } }, [incidentsEnabled]);

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
      transformRequest: url => {
        try {
          if (new URL(url).hostname === "api.tomtom.com") return { url, headers: { "TomTom-Api-Key": tomTomKey } };
        } catch { /* relative internal URLs do not receive TomTom credentials */ }
        return { url };
      },
    });
    mapRef.current = map;
    map.dragRotate.disable();
    map.touchZoomRotate.disableRotation();

    const reconcileOperationalLayers = () => {
      if (!map.getSource(trafficSourceId)) map.addSource(trafficSourceId, { type: "raster", tiles: ["https://api.tomtom.com/maps/orbis/traffic/flow/raster/tile/{z}/{x}/{y}?apiVersion=2&style=light&tileSize=256"], tileSize: 256, maxzoom: 22, attribution: "© TomTom Traffic" });
      if (!map.getLayer(trafficLayerId)) map.addLayer({ id: trafficLayerId, type: "raster", source: trafficSourceId, layout: { visibility: trafficEnabledRef.current ? "visible" : "none" }, paint: { "raster-opacity": 0.5 } });
      if (!map.getSource(incidentsSourceId)) map.addSource(incidentsSourceId, { type: "raster", tiles: ["https://api.tomtom.com/maps/orbis/traffic/incidents/raster/tile/{z}/{x}/{y}?apiVersion=2&style=light&tileSize=256"], tileSize: 256, maxzoom: 22, attribution: "© TomTom Traffic" });
      if (!map.getLayer(incidentsLayerId)) map.addLayer({ id: incidentsLayerId, type: "raster", source: incidentsSourceId, layout: { visibility: incidentsEnabledRef.current ? "visible" : "none" } });
      if (!map.getSource(routeSourceId)) map.addSource(routeSourceId, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      if (!map.getLayer(routeCasingLayerId)) map.addLayer({ id: routeCasingLayerId, type: "line", source: routeSourceId, layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#fffdf9", "line-width": 10, "line-opacity": 0.72 } });
      if (!map.getLayer(routeLayerId)) map.addLayer({ id: routeLayerId, type: "line", source: routeSourceId, layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#263d73", "line-width": 6, "line-opacity": 0.96 } });
      mapLoadedRef.current = true;
      setMapError(false);
      setMapLoaded(true);
      setStyleRevision(value => value + 1);
    };
    const onError = (event?: { error?: Error }) => {
      const message = event?.error?.message.toLowerCase() ?? "";
      if (mapLoadedRef.current && /sprite|glyph/.test(message)) return;
      setMapError(true);
    };
    map.on("load", reconcileOperationalLayers);
    map.on("style.load", reconcileOperationalLayers);
    map.on("error", onError);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => map.resize());
    observer?.observe(containerRef.current);

    return () => {
      observer?.disconnect();
      markersRef.current.forEach(marker => marker.remove());
      markersRef.current = [];
      map.off("load", reconcileOperationalLayers);
      map.off("style.load", reconcileOperationalLayers);
      map.off("error", onError);
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
    map.setLayoutProperty(trafficLayerId, "visibility", trafficEnabled ? "visible" : "none");
  }, [mapLoaded, trafficEnabled]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || !map.getLayer(incidentsLayerId)) return;
    map.setLayoutProperty(incidentsLayerId, "visibility", incidentsEnabled ? "visible" : "none");
  }, [incidentsEnabled, mapLoaded]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || !map.getSource(routeSourceId)) return;
    markersRef.current.forEach(marker => marker.remove());
    markersRef.current = [];
    const pickup = request ? validCoordinate(request.pickup_latitude, request.pickup_longitude) : null;
    const destination = request ? validCoordinate(request.destination_latitude, request.destination_longitude) : null;
    const routeCoordinates = route?.geometry?.coordinates ?? [];
    const routeData = routeCoordinates.length >= 2 ? { type: "Feature" as const, properties: {}, geometry: { type: "LineString" as const, coordinates: routeCoordinates } } : { type: "FeatureCollection" as const, features: [] };
    (map.getSource(routeSourceId) as GeoJSONSource).setData(routeData);
    if (!request || !pickup || !destination) { map.jumpTo({ center: fallbackCenter, zoom: fallbackZoom, bearing: 0, pitch: 0 }); return; }
    markersRef.current = [
      new maplibregl.Marker({ element: markerElement("pickup", request.pickup_name), anchor: "center" }).setLngLat(pickup).addTo(map),
      new maplibregl.Marker({ element: markerElement("destination", request.destination_name), anchor: "center" }).setLngLat(destination).addTo(map),
    ];
    const cameraPoints = routeCoordinates.length >= 2 ? [...routeCoordinates, pickup, destination] : [pickup, destination];
    const bounds = cameraPoints.reduce((result, coordinate) => result.extend(coordinate), new maplibregl.LngLatBounds(cameraPoints[0], cameraPoints[0]));
    map.fitBounds(bounds as LngLatBoundsLike, { padding: { top: 55, right: 320, bottom: 55, left: 55 }, maxZoom: 16, duration: 0 });
  }, [mapLoaded, request, route?.geometry?.coordinates, styleRevision]);

  return <div className={`request-map tomtom-request-map maplibre-request-map ${request ? "" : "request-map--empty"}`}>
    <div ref={containerRef} className="request-map-canvas" data-testid="request-map" aria-label="Transport request map" />
    {!tomTomKey && <div className="request-map-state" role="alert">TomTom map key is not configured.</div>}
    {tomTomKey && !mapLoaded && !mapError && <div className="request-map-loading" role="status">Loading TomTom map…</div>}
    {tomTomKey && mapError && <div className="request-map-tile-error" role="alert">Unable to load TomTom map.</div>}
    {tomTomKey && <div className="map-settings" ref={settingsRef}><button type="button" className="map-settings-button" title="Map settings" aria-label="Map settings" aria-expanded={settingsOpen} onClick={() => setSettingsOpen(value => !value)}>⋮</button>{settingsOpen && <div className="map-settings-popover" role="dialog" aria-label="Map settings"><header><strong>Map settings</strong><button type="button" className="map-settings-close" aria-label="Close map settings" onClick={() => setSettingsOpen(false)}>×</button></header><fieldset><legend>Map style</legend>{Object.entries(mapStyles).map(([value, option]) => <label key={value}><input type="radio" name="transport-map-style" value={value} checked={mapStyle === value} onChange={() => setMapStyle(value as MapStyle)} />{option.label}</label>)}</fieldset><fieldset><legend>Layers</legend><label><input type="checkbox" checked={trafficEnabled} onChange={event => setTrafficEnabled(event.target.checked)} />Live traffic</label><label><input type="checkbox" checked={incidentsEnabled} onChange={event => setIncidentsEnabled(event.target.checked)} />Traffic incidents</label></fieldset></div>}</div>}
    {request && routeState === "loading" && <div className="request-route-state" role="status">Calculating route…</div>}
    {request && routeState === "error" && <div className="request-route-state request-route-state--error" role="status">Route unavailable</div>}
    {request ? <div className="map-legend"><span><i className="pickup-dot" />{request.pickup_name}</span><span><i className="destination-dot" />{request.destination_name}</span></div> : <div className="request-map-empty-overlay">No request selected</div>}
  </div>;
}
