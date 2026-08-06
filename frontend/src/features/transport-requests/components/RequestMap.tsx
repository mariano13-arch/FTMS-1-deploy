import { useEffect } from "react";
import { CircleMarker, MapContainer, Polyline, TileLayer, useMap } from "react-leaflet";
import type { TransportRequestBase } from "../types";

function Fit({ points }: { points: [[number, number], [number, number]] }) {
  const map = useMap();
  useEffect(() => { map.fitBounds(points, { padding: [35, 35] }); }, [map, points]);
  return null;
}
const fallbackCenter: [number, number] = [14.5652, 121.0286];
function DefaultView({ active }: { active: boolean }) {
  const map = useMap();
  useEffect(() => { if (!active) map.setView(fallbackCenter, 13); }, [active, map]);
  return null;
}
export default function RequestMap({ request }: { request: TransportRequestBase | null }) {
  const pickup: [number, number] = request ? [Number(request.pickup_latitude), Number(request.pickup_longitude)] : fallbackCenter;
  const destination: [number, number] | null = request ? [Number(request.destination_latitude), Number(request.destination_longitude)] : null;
  const points: [[number, number], [number, number]] | null = destination ? [pickup, destination] : null;
  return <div className={`request-map ${request ? "" : "request-map--empty"}`}><MapContainer center={pickup} zoom={13} scrollWheelZoom={false}>
    <TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
    <DefaultView active={Boolean(request)} />
    {request && destination && points && <><CircleMarker center={pickup} radius={9} pathOptions={{ color: "#8f1d2c", fillOpacity: 1 }} /><CircleMarker center={destination} radius={9} pathOptions={{ color: "#247058", fillOpacity: 1 }} /><Polyline positions={points} pathOptions={{ color: "#9b7653", dashArray: "6 7" }} /><Fit points={points} /></>}
  </MapContainer>{request ? <div className="map-legend"><span><i className="pickup-dot" />{request.pickup_name}</span><span><i className="destination-dot" />{request.destination_name}</span></div> : <div className="request-map-empty-overlay">No request selected</div>}</div>;
}
