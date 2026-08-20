import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';

import { AppButton } from '@/components/AppButton';
import { AppScreen } from '@/components/AppScreen';
import { EmptyState } from '@/components/EmptyState';
import { ApiError } from '@/services/api';
import { getDriverTrips } from '@/services/driverTrips';
import { colors, spacing } from '@/theme';
import type { DriverTrip } from '@/types';

function formatSchedule(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value));
}

function tripErrorMessage(error: unknown) {
  if (error instanceof ApiError && error.status === 401) {
    return 'Your driver session has expired. Sign in again to reload assignments.';
  }
  if (error instanceof ApiError) {
    return error.message;
  }
  return 'Unable to load assigned trips.';
}

export default function MyTripsScreen() {
  const router = useRouter();
  const [trips, setTrips] = useState<DriverTrip[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadTrips = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    setError(null);
    try {
      setTrips(await getDriverTrips(signal));
    } catch (loadError) {
      if (loadError instanceof Error && loadError.name === 'AbortError') {
        return;
      }
      setError(tripErrorMessage(loadError));
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false);
      }
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      const controller = new AbortController();
      void loadTrips(controller.signal);
      return () => controller.abort();
    }, [loadTrips]),
  );

  return (
    <AppScreen
      title="My Trips"
      description="Confirmed FTMS assignments for your driver account.">
      {isLoading ? (
        <View style={styles.stateCard}>
          <ActivityIndicator color={colors.burgundy} size="large" />
          <Text style={styles.stateText}>Loading assigned trips…</Text>
        </View>
      ) : error ? (
        <View style={styles.stateCard}>
          <Text style={styles.errorTitle}>Trips unavailable</Text>
          <Text style={styles.stateText}>{error}</Text>
          <AppButton label="Retry" onPress={() => void loadTrips()} />
        </View>
      ) : trips.length === 0 ? (
        <EmptyState
          title="No trips assigned"
          message="There are no active FTMS dispatch assignments for this driver."
        />
      ) : (
        <View style={styles.list}>
          {trips.map((trip) => (
            <Pressable
              key={trip.id}
              accessibilityRole="button"
              accessibilityLabel={`Open ${trip.requestNumber}`}
              onPress={() =>
                router.push({ pathname: '/trips/[tripId]', params: { tripId: trip.id } })
              }
              style={({ pressed }) => [styles.tripCard, pressed && styles.pressed]}>
              <View style={styles.cardHeader}>
                <View style={styles.headerCopy}>
                  <Text style={styles.requestNumber}>{trip.requestNumber}</Text>
                  <Text style={styles.schedule}>{formatSchedule(trip.scheduledPickupAt)}</Text>
                </View>
                <View
                  style={[
                    styles.statusBadge,
                    trip.execution.status !== 'ASSIGNED' && styles.readyBadge,
                  ]}>
                  <Text
                    style={[
                      styles.statusText,
                      trip.execution.status !== 'ASSIGNED' && styles.readyText,
                    ]}>
                    {trip.execution.statusLabel}
                  </Text>
                </View>
              </View>

              <View style={styles.route}>
                <View style={styles.routeMarker} />
                <View style={styles.routeCopy}>
                  <Text style={styles.locationLabel}>Pickup</Text>
                  <Text style={styles.locationName}>{trip.pickup.name}</Text>
                  <Text style={styles.address}>{trip.pickup.address}</Text>
                </View>
              </View>
              <View style={styles.routeLine} />
              <View style={styles.route}>
                <View style={[styles.routeMarker, styles.destinationMarker]} />
                <View style={styles.routeCopy}>
                  <Text style={styles.locationLabel}>Destination</Text>
                  <Text style={styles.locationName}>{trip.destination.name}</Text>
                  <Text style={styles.address}>{trip.destination.address}</Text>
                </View>
              </View>

              <View style={styles.cardFooter}>
                <Text style={styles.vehicle}>
                  {trip.vehicle.displayName} · {trip.vehicle.plateNumber}
                </Text>
                <Text style={styles.openLabel}>View details →</Text>
              </View>
            </Pressable>
          ))}
        </View>
      )}
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  list: { gap: spacing.md },
  stateCard: {
    minHeight: 180,
    justifyContent: 'center',
    gap: spacing.md,
    padding: spacing.xl,
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 12,
  },
  stateText: { color: colors.muted, fontSize: 14, lineHeight: 20, textAlign: 'center' },
  errorTitle: { color: colors.ink, fontSize: 18, fontWeight: '700', textAlign: 'center' },
  tripCard: {
    padding: spacing.lg,
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 12,
  },
  pressed: { opacity: 0.75 },
  cardHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.sm },
  headerCopy: { flex: 1, gap: 2 },
  requestNumber: { color: colors.ink, fontSize: 18, fontWeight: '800' },
  schedule: { color: colors.muted, fontSize: 13 },
  statusBadge: {
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    backgroundColor: '#fff4df',
    borderRadius: 999,
  },
  readyBadge: { backgroundColor: '#e4f3ec' },
  statusText: { color: colors.warning, fontSize: 11, fontWeight: '800' },
  readyText: { color: colors.positive },
  route: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  routeMarker: {
    width: 12,
    height: 12,
    marginTop: 4,
    borderRadius: 6,
    backgroundColor: colors.burgundy,
  },
  destinationMarker: { backgroundColor: colors.ink },
  routeLine: {
    width: 2,
    height: 16,
    marginVertical: -10,
    marginLeft: 5,
    backgroundColor: colors.border,
  },
  routeCopy: { flex: 1, gap: 2 },
  locationLabel: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  locationName: { color: colors.ink, fontSize: 15, fontWeight: '700' },
  address: { color: colors.muted, fontSize: 13, lineHeight: 18 },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing.sm,
    paddingTop: spacing.md,
    borderTopColor: colors.border,
    borderTopWidth: 1,
  },
  vehicle: { flex: 1, color: colors.muted, fontSize: 12 },
  openLabel: { color: colors.burgundy, fontSize: 12, fontWeight: '800' },
});
