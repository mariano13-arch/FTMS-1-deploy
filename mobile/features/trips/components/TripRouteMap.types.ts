import type { DriverTripRoute } from '@/types';

export type TripRouteMapProps = {
  activeRoute: DriverTripRoute;
};

export function hasValidRouteCoordinates(
  value: unknown,
): value is { latitude: number; longitude: number } {
  if (!value || typeof value !== 'object') return false;
  const place = value as { latitude?: unknown; longitude?: unknown };
  return (
    typeof place.latitude === 'number' &&
    Number.isFinite(place.latitude) &&
    typeof place.longitude === 'number' &&
    Number.isFinite(place.longitude)
  );
}
