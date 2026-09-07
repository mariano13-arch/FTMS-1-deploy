import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';

import { AppButton } from '@/components/AppButton';
import { AppScreen } from '@/components/AppScreen';
import { EmptyState } from '@/components/EmptyState';
import { ApiError } from '@/services/api';
import { acceptDriverTrip, getDriverTrip } from '@/services/driverTrips';
import { colors, spacing } from '@/theme';
import type { DriverTrip } from '@/types';

function formatSchedule(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value));
}

function detailErrorMessage(error: unknown) {
  if (error instanceof ApiError && error.status === 404) {
    return 'This trip was not found or is not assigned to your driver account.';
  }
  if (error instanceof ApiError && error.status === 401) {
    return 'Your driver session has expired. Sign in again to view this trip.';
  }
  if (error instanceof ApiError) {
    return error.message;
  }
  return 'Unable to load this trip.';
}

type FactProps = { label: string; value: string };

function Fact({ label, value }: FactProps) {
  return (
    <View style={styles.fact}>
      <Text style={styles.factLabel}>{label}</Text>
      <Text style={styles.factValue}>{value}</Text>
    </View>
  );
}

export default function TripDetailsScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ tripId?: string | string[] }>();
  const tripId = Array.isArray(params.tripId) ? params.tripId[0] : params.tripId;
  const [trip, setTrip] = useState<DriverTrip | null>(null);
  const [isLoading, setIsLoading] = useState(Boolean(tripId));
  const [isAccepting, setIsAccepting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [acceptanceError, setAcceptanceError] = useState<string | null>(null);

  const loadTrip = useCallback(
    async (signal?: AbortSignal) => {
      if (!tripId) {
        setError('No trip was selected.');
        setIsLoading(false);
        return;
      }
      setIsLoading(true);
      setError(null);
      setAcceptanceError(null);
      try {
        setTrip(await getDriverTrip(tripId, signal));
      } catch (loadError) {
        if (loadError instanceof Error && loadError.name === 'AbortError') {
          return;
        }
        setTrip(null);
        setError(detailErrorMessage(loadError));
      } finally {
        if (!signal?.aborted) {
          setIsLoading(false);
        }
      }
    },
    [tripId],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadTrip(controller.signal);
    return () => controller.abort();
  }, [loadTrip]);

  const acceptTrip = useCallback(async () => {
    if (!tripId || !trip || isAccepting) {
      return;
    }
    setIsAccepting(true);
    setAcceptanceError(null);
    try {
      setTrip(await acceptDriverTrip(tripId, trip.assignmentConfirmedAt));
    } catch (acceptError) {
      setAcceptanceError(detailErrorMessage(acceptError));
    } finally {
      setIsAccepting(false);
    }
  }, [isAccepting, trip, tripId]);

  return (
    <AppScreen
      title={trip?.requestNumber ?? 'Trip Details'}
      description={trip ? formatSchedule(trip.scheduledPickupAt) : undefined}>
      {isLoading ? (
        <View style={styles.stateCard}>
          <ActivityIndicator color={colors.burgundy} size="large" />
          <Text style={styles.stateText}>Loading trip details…</Text>
        </View>
      ) : error ? (
        <View style={styles.stateCard}>
          <Text style={styles.errorTitle}>Trip unavailable</Text>
          <Text style={styles.stateText}>{error}</Text>
          {tripId ? <AppButton label="Retry" onPress={() => void loadTrip()} /> : null}
        </View>
      ) : trip ? (
        <>
          <View style={styles.heroCard}>
            <View style={styles.heroHeader}>
              <View style={styles.heroCopy}>
                <Text style={styles.tripType}>{trip.requestTypeLabel}</Text>
                {trip.requestCategoryLabel ? (
                  <Text style={styles.category}>{trip.requestCategoryLabel}</Text>
                ) : null}
              </View>
              <View
                style={[
                  styles.statusBadge,
                  trip.status === 'READY_FOR_DISPATCH' && styles.readyBadge,
                ]}>
                <Text
                  style={[
                    styles.statusText,
                    trip.status === 'READY_FOR_DISPATCH' && styles.readyText,
                  ]}>
                  {trip.statusLabel}
                </Text>
              </View>
            </View>

            <View style={styles.stop}>
              <View style={styles.pickupMarker} />
              <View style={styles.stopCopy}>
                <Text style={styles.stopLabel}>Pickup</Text>
                <Text style={styles.stopName}>{trip.pickup.name}</Text>
                <Text style={styles.stopAddress}>{trip.pickup.address}</Text>
              </View>
            </View>
            <View style={styles.connector} />
            <View style={styles.stop}>
              <View style={styles.destinationMarker} />
              <View style={styles.stopCopy}>
                <Text style={styles.stopLabel}>Destination</Text>
                <Text style={styles.stopName}>{trip.destination.name}</Text>
                <Text style={styles.stopAddress}>{trip.destination.address}</Text>
              </View>
            </View>
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Trip facts</Text>
            <View style={styles.factsGrid}>
              <Fact label="Scheduled pickup" value={formatSchedule(trip.scheduledPickupAt)} />
              <Fact
                label="Vehicle"
                value={`${trip.vehicle.displayName} · ${trip.vehicle.plateNumber}`}
              />
              <Fact label="Passengers" value={String(trip.passengerCount)} />
              <Fact label="Est. duration" value={`${trip.estimatedDurationMinutes} min`} />
              {trip.luggageCount > 0 ? (
                <Fact label="Luggage" value={String(trip.luggageCount)} />
              ) : null}
              <Fact label="Priority" value={trip.priorityLabel} />
              <Fact label="Execution" value={trip.execution.statusLabel} />
              <Fact
                label="Driver acknowledgement"
                value={trip.isAccepted ? 'Accepted' : 'Awaiting acceptance'}
              />
            </View>
          </View>

          {trip.handlingInstructions ||
          trip.loadDescription ||
          trip.loadQuantity !== null ||
          trip.estimatedWeightKg !== null ||
          trip.temperatureRequirement ? (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Instructions and load</Text>
              {trip.handlingInstructions ? (
                <View style={styles.instructionBlock}>
                  <Text style={styles.factLabel}>Handling instructions</Text>
                  <Text style={styles.bodyText}>{trip.handlingInstructions}</Text>
                </View>
              ) : null}
              {trip.loadDescription ? (
                <Fact label="Load" value={trip.loadDescription} />
              ) : null}
              {trip.loadQuantity !== null ? (
                <Fact label="Load quantity" value={String(trip.loadQuantity)} />
              ) : null}
              {trip.estimatedWeightKg !== null ? (
                <Fact label="Estimated weight" value={`${trip.estimatedWeightKg} kg`} />
              ) : null}
              {trip.temperatureRequirement ? (
                <Fact label="Temperature requirement" value={trip.temperatureRequirement} />
              ) : null}
            </View>
          ) : null}

          {acceptanceError ? (
            <View style={styles.inlineError}>
              <Text style={styles.inlineErrorText}>{acceptanceError}</Text>
              <AppButton
                label="Reload Assignment"
                variant="secondary"
                onPress={() => void loadTrip()}
              />
            </View>
          ) : null}

          {!trip.isAccepted && trip.status === 'READY_FOR_DISPATCH' ? (
            <AppButton
              label={isAccepting ? 'Accepting…' : 'Accept Trip'}
              disabled={isAccepting}
              onPress={() => void acceptTrip()}
            />
          ) : null}

          {trip.isAccepted &&
          trip.execution.status !== 'COMPLETED' &&
          trip.execution.allowedActions.length > 0 ? (
            <AppButton
              label="Open Active Trip"
              onPress={() =>
                router.push({ pathname: '/active-trip', params: { tripId: trip.id } })
              }
            />
          ) : null}
        </>
      ) : (
        <EmptyState title="No trip selected" message="Return to My Trips and select an assignment." />
      )}
    </AppScreen>
  );
}

const styles = StyleSheet.create({
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
  heroCard: {
    padding: spacing.lg,
    gap: spacing.lg,
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 12,
  },
  heroHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.sm },
  heroCopy: { flex: 1, gap: 2 },
  tripType: { color: colors.ink, fontSize: 18, fontWeight: '800' },
  category: { color: colors.muted, fontSize: 13 },
  statusBadge: {
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    backgroundColor: '#fff4df',
    borderRadius: 999,
  },
  readyBadge: { backgroundColor: '#e4f3ec' },
  statusText: { color: colors.warning, fontSize: 11, fontWeight: '800' },
  readyText: { color: colors.positive },
  stop: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  pickupMarker: {
    width: 14,
    height: 14,
    marginTop: 4,
    borderRadius: 7,
    backgroundColor: colors.burgundy,
  },
  destinationMarker: {
    width: 14,
    height: 14,
    marginTop: 4,
    borderRadius: 3,
    backgroundColor: colors.ink,
  },
  connector: {
    width: 2,
    height: 22,
    marginVertical: -14,
    marginLeft: 6,
    backgroundColor: colors.border,
  },
  stopCopy: { flex: 1, gap: 2 },
  stopLabel: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  stopName: { color: colors.ink, fontSize: 16, fontWeight: '700' },
  stopAddress: { color: colors.muted, fontSize: 13, lineHeight: 18 },
  section: {
    padding: spacing.lg,
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 12,
  },
  sectionTitle: { color: colors.ink, fontSize: 16, fontWeight: '800' },
  factsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  fact: {
    flexGrow: 1,
    flexBasis: '46%',
    minWidth: 130,
    gap: 3,
    padding: spacing.md,
    backgroundColor: colors.canvas,
    borderRadius: 8,
  },
  factLabel: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  factValue: { color: colors.ink, fontSize: 14, fontWeight: '700', lineHeight: 19 },
  instructionBlock: { gap: spacing.xs },
  bodyText: { color: colors.ink, fontSize: 14, lineHeight: 20 },
  inlineError: {
    padding: spacing.md,
    backgroundColor: '#fff0f0',
    borderColor: colors.burgundy,
    borderWidth: 1,
    borderRadius: 8,
  },
  inlineErrorText: { color: colors.burgundy, fontSize: 13, lineHeight: 18 },
});
