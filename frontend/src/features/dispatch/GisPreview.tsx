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
  plannedRoute,
  vehiclePosition,
  routeState,
  stops,
}: {
  recommendation: Recommendation;
  request: TransportRequestListItem;
  route: TransportRoute | null;
  plannedRoute: TransportRoute | null;
  vehiclePosition: {
    latitude: number;
    longitude: number;
    positionStatus: "CURRENT" | "STALE";
  } | null;
  routeState: "idle" | "loading" | "ready" | "error";
  stops?: ConsolidationStop[];
}) {
  const vehicleLocation = vehiclePosition
    ? {
        latitude: vehiclePosition.latitude,
        longitude: vehiclePosition.longitude,
        label: recommendation.recommended_vehicle.display_name,
        plateNumber: recommendation.recommended_vehicle.plate_number,
        positionStatus: vehiclePosition.positionStatus,
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
            plannedRoute={plannedRoute}
            routeState={routeState}
            operationalLocation={vehicleLocation}
            recommendationPreview={!stops?.length}
            numberedStops={stops}
          />
        </Suspense>
      </div>
      {!stops?.length && !vehicleLocation && (
        <small className="dispatch-gis-position-note">
          Recommended vehicle position unavailable.
        </small>
      )}
      <p>
        TomTom vehicle-to-pickup metrics:{" "}
        {duration(recommendation.travel_time_seconds)} ·{" "}
        {distance(recommendation.distance_meters)}
      </p>
      <small>
        {stops?.length
          ? "Consolidation stops use real coordinates; multi-stop geometry is unavailable, so no route line is drawn."
          : routeState === "error"
            ? "Route geometry temporarily unavailable"
            : "Road route preview: selected vehicle to pickup, then pickup to destination."}
      </small>
    </section>
  );
}
