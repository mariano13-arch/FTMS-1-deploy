import React, { Suspense } from "react";
import LoadingIndicator from "../../components/common/LoadingIndicator";
import type { TransportRequestListItem, TransportRoute } from "../transport-requests/types";
import type { ConsolidationStop, Recommendation } from "../../services/dispatch";

const RequestMap = React.lazy(() => import("../transport-requests/components/RequestMap"));

const duration = (seconds: number | null) =>
  seconds === null ? "Unavailable" : `${Math.ceil(seconds / 60)} min`;
const distance = (meters: number | null) =>
  meters === null
    ? "Unavailable"
    : meters >= 1000
      ? `${(meters / 1000).toFixed(1)} km`
      : `${meters} m`;

export default function GisPreview({
  recommendation,
  request,
  route,
  routeState,
  stops,
}: {
  recommendation: Recommendation;
  request: TransportRequestListItem;
  route: TransportRoute | null;
  routeState: "idle" | "loading" | "ready" | "error";
  stops?: ConsolidationStop[];
}) {
  const gis = recommendation.gis_preview;
  const vehicleLocation = gis.vehicle_location
    ? {
        latitude: gis.vehicle_location.latitude,
        longitude: gis.vehicle_location.longitude,
        label: recommendation.recommended_vehicle.display_name,
      }
    : null;
  return (
    <section className="dispatch-gis">
      <h3>GIS Recommendation Preview</h3>
      <div className="dispatch-gis-map">
        <Suspense fallback={<LoadingIndicator variant="card" message="Loading map…" />}>
          <RequestMap
            request={request}
            route={route}
            routeState={routeState}
            operationalLocation={vehicleLocation}
            numberedStops={stops}
          />
        </Suspense>
      </div>
      <p>
        TomTom vehicle-to-pickup metrics:{" "}
        {duration(recommendation.travel_time_seconds)} ·{" "}
        {distance(recommendation.distance_meters)}
      </p>
      <small>
        {stops?.length
          ? "Consolidation stops use real coordinates; multi-stop geometry is unavailable, so no route line is drawn."
          : "Vehicle-to-pickup road geometry unavailable; no route line is drawn. Pickup-to-destination uses the real TomTom request route when available."}
      </small>
    </section>
  );
}
