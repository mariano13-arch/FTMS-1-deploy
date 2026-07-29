import { useEffect } from "react";
import { CircleMarker, MapContainer, TileLayer, useMap } from "react-leaflet";
import type { TelemetryEvent } from "../services/telemetry";

type Position = [latitude: number, longitude: number];

function Recenter({ position }: { position: Position }) {
  const map = useMap();
  const [latitude, longitude] = position;
  useEffect(() => {
    map.setView([latitude, longitude]);
  }, [latitude, longitude, map]);
  return null;
}

export default function LiveVehicleMap({
  latest,
}: {
  latest: TelemetryEvent | null;
}) {
  if (latest === null) {
    return <p className="map-waiting">Waiting for live vehicle location…</p>;
  }
  const position: Position = [latest.latitude, latest.longitude];
  return (
    <section className="map-panel" aria-labelledby="map-title">
      <div className="map-panel__header">
        <h2 id="map-title">Live vehicle location</h2>
        <p>
          Current position: {latest.latitude.toFixed(4)},{" "}
          {latest.longitude.toFixed(4)}
        </p>
      </div>
      <MapContainer center={position} zoom={16} scrollWheelZoom={false}>
        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <CircleMarker center={position} radius={10} pathOptions={{ color: "#5ce3a6" }} />
        <Recenter position={position} />
      </MapContainer>
    </section>
  );
}
