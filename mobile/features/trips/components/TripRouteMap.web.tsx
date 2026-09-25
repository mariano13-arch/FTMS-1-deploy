import { StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '@/theme';

import type { TripRouteMapProps } from './TripRouteMap.types';

export default function TripRouteMap({ activeRoute }: TripRouteMapProps) {
  return (
    <View style={styles.container}>
      <View style={styles.headingRow}>
        <View style={styles.mapIcon}>
          <View style={styles.mapIconLine} />
          <View style={styles.mapIconPoint} />
        </View>
        <View style={styles.headingCopy}>
          <Text style={styles.title}>Live trip map</Text>
          <Text style={styles.message}>
            The interactive vehicle map is available in the Android and iOS mobile builds.
          </Text>
        </View>
      </View>

      <View style={styles.routeCard}>
        <View style={styles.stopRow}>
          <View style={[styles.marker, styles.pickupMarker]} />
          <View style={styles.stopCopy}>
            <Text style={styles.stopLabel}>Pickup</Text>
            <Text style={styles.stopName}>{activeRoute.pickup?.name || 'Pickup unavailable'}</Text>
          </View>
        </View>
        <View style={styles.connector} />
        <View style={styles.stopRow}>
          <View style={[styles.marker, styles.destinationMarker]} />
          <View style={styles.stopCopy}>
            <Text style={styles.stopLabel}>Destination</Text>
            <Text style={styles.stopName}>
              {activeRoute.destination?.name || 'Destination unavailable'}
            </Text>
          </View>
        </View>
      </View>

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
  container: {
    minHeight: 240,
    justifyContent: 'center',
    gap: spacing.md,
    padding: spacing.lg,
    backgroundColor: colors.canvas,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 10,
  },
  headingRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  headingCopy: { flex: 1, gap: spacing.xs },
  title: { color: colors.ink, fontSize: 16, fontWeight: '800' },
  message: { color: colors.muted, fontSize: 13, lineHeight: 18 },
  mapIcon: {
    width: 42,
    height: 42,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.burgundySoft,
    borderRadius: 21,
  },
  mapIconLine: { width: 20, height: 3, backgroundColor: colors.burgundy, borderRadius: 2 },
  mapIconPoint: {
    position: 'absolute',
    width: 8,
    height: 8,
    backgroundColor: colors.burgundy,
    borderRadius: 4,
  },
  routeCard: { gap: spacing.xs },
  stopRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  marker: { width: 10, height: 10 },
  pickupMarker: { backgroundColor: colors.burgundy, borderRadius: 5 },
  destinationMarker: { backgroundColor: colors.ink, borderRadius: 2 },
  connector: { width: 2, height: 12, marginLeft: 4, backgroundColor: colors.border },
  stopCopy: { flex: 1 },
  stopLabel: { color: colors.muted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
  stopName: { color: colors.ink, fontSize: 13, fontWeight: '700' },
  notice: { color: colors.warning, fontSize: 13 },
});
