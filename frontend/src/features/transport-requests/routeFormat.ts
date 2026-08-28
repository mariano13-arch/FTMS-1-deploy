import type { TransportRoute } from "./types";

export const distanceLabel = (route: TransportRoute) =>
  `${(route.distance_meters / 1000).toFixed(1)} km`;

export const durationLabel = (route: TransportRoute) =>
  `${Math.round(route.duration_seconds / 60)} min`;

export const delayLabel = (route: TransportRoute) =>
  `+${Math.round(route.traffic_delay_seconds / 60)} min traffic`;
