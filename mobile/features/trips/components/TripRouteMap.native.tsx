import { useEffect, useMemo, useRef } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import MapView, { Marker, Polyline } from 'react-native-maps';

import { colors, spacing } from '@/theme';

import { hasValidRouteCoordinates, type TripRouteMapProps } from './TripRouteMap.types';

export default function TripRouteMap({ activeRoute }: TripRouteMapProps) {
  const mapRef = useRef<MapView>(null);
  const fittedPhase = useRef<string | null>(null);
  const routeCoordinates = useMemo(
    () =>
      activeRoute.route?.geometry.coordinates
        .map(([longitude, latitude]) => ({ latitude, longitude }))
        .filter(hasValidRouteCoordinates) ?? [],
    [activeRoute.route?.geometry.coordinates],
  );
  const fitKey = `${activeRoute.phase}:${activeRoute.executionStatus}`;
  const pickup = hasValidRouteCoordinates(activeRoute.pickup) ? activeRoute.pickup : null;
  const destination = hasValidRouteCoordinates(activeRoute.destination)
    ? activeRoute.destination
    : null;
  const vehiclePosition = hasValidRouteCoordinates(activeRoute.vehiclePosition)
    ? activeRoute.vehiclePosition
    : null;
  const fitMap = () => {
    if (fittedPhase.current === fitKey) return;
    const points = [...routeCoordinates];
    if (vehiclePosition) points.push(vehiclePosition);
    if (pickup) points.push(pickup);
    if (destination) points.push(destination);
    if (points.length > 1) {
      mapRef.current?.fitToCoordinates(points, {
        edgePadding: { top: 42, right: 42, bottom: 42, left: 42 },
        animated: false,
      });
      fittedPhase.current = fitKey;
    }
  };
  useEffect(fitMap, [fitKey, routeCoordinates]);

  return (
    <View style={styles.container}>
      <MapView ref={mapRef} style={styles.map} onMapReady={fitMap}>
        {vehiclePosition ? (
          <Marker
            coordinate={vehiclePosition}
            title="Assigned vehicle"
            pinColor={colors.positive}
          />
        ) : null}
        {pickup ? <Marker coordinate={pickup} title="Pickup" pinColor={colors.burgundy} /> : null}
        {destination ? (
          <Marker coordinate={destination} title="Destination" pinColor={colors.ink} />
        ) : null}
        {routeCoordinates.length > 1 ? (
          <Polyline coordinates={routeCoordinates} strokeColor={colors.burgundy} strokeWidth={5} />
        ) : null}
      </MapView>
      {!pickup ? <Text style={styles.notice}>Pickup unavailable</Text> : null}
      {!destination ? <Text style={styles.notice}>Destination unavailable</Text> : null}
      {activeRoute.routeStatus === 'POSITION_UNAVAILABLE' ? (
        <Text style={styles.notice}>Vehicle position unavailable</Text>
      ) : null}
      {activeRoute.routeStatus === 'TEMPORARILY_UNAVAILABLE' ? (
        <Text style={styles.notice}>Route temporarily unavailable</Text>
      ) : null}
      {activeRoute.positionState === 'STALE' ? (
        <Text style={styles.notice}>Route shown from last known vehicle position</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: spacing.sm },
  map: { width: '100%', height: 240, borderRadius: 10 },
  notice: { color: colors.warning, fontSize: 13 },
});
