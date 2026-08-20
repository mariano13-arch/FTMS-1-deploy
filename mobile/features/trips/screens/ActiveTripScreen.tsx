import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Platform, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';

import { AppButton } from '@/components/AppButton';
import { AppScreen } from '@/components/AppScreen';
import { EmptyState } from '@/components/EmptyState';
import { ApiError } from '@/services/api';
import {
  getDriverTrip,
  getDriverTripRoute,
  getDriverTripVehiclePosition,
  transitionDriverTrip,
} from '@/services/driverTrips';
import { colors, spacing } from '@/theme';
import type {
  DriverTrip,
  DriverTripExecution,
  DriverTripExecutionAction,
  DriverTripExecutionStatus,
  DriverTripRoute,
  DriverVehiclePosition,
} from '@/types';

const VEHICLE_POSITION_POLL_INTERVAL_MS = 15_000;

const EXECUTION_STAGES: {
  status: DriverTripExecutionStatus;
  label: string;
  timestamp: keyof Pick<
    DriverTripExecution,
    | 'executionStartedAt'
    | 'pickupArrivedAt'
    | 'pickupDepartedAt'
    | 'destinationArrivedAt'
    | 'completedAt'
  > | null;
}[] = [
  { status: 'ASSIGNED', label: 'Assigned', timestamp: null },
  {
    status: 'EN_ROUTE_TO_PICKUP',
    label: 'En route to pickup',
    timestamp: 'executionStartedAt',
  },
  { status: 'AT_PICKUP', label: 'At pickup', timestamp: 'pickupArrivedAt' },
  { status: 'IN_TRANSIT', label: 'In transit', timestamp: 'pickupDepartedAt' },
  {
    status: 'AT_DESTINATION',
    label: 'At destination',
    timestamp: 'destinationArrivedAt',
  },
  { status: 'COMPLETED', label: 'Completed', timestamp: 'completedAt' },
];

const ACTION_LABELS: Record<DriverTripExecutionAction, string> = {
  START_TOWARD_PICKUP: 'Start Trip to Pickup',
  ARRIVE_AT_PICKUP: "I've Arrived at Pickup",
  DEPART_PICKUP: 'Depart Pickup',
  ARRIVE_AT_DESTINATION: "I've Arrived at Destination",
  COMPLETE: 'Complete Trip',
};

const CONFIRMED_ACTIONS = new Set<DriverTripExecutionAction>([
  'DEPART_PICKUP',
  'ARRIVE_AT_DESTINATION',
  'COMPLETE',
]);

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value));
}

function formatDistance(meters: number) {
  return meters >= 1000 ? `${(meters / 1000).toFixed(1)} km` : `${meters} m`;
}

function formatDuration(seconds: number) {
  const minutes = Math.max(1, Math.round(seconds / 60));
  return `${minutes} min`;
}

function loadErrorMessage(error: unknown) {
  if (error instanceof ApiError && error.status === 401) {
    return 'Your driver session has expired. Sign in again to view this trip.';
  }
  if (error instanceof ApiError && error.status === 404) {
    return 'This trip is unavailable or is no longer assigned to your driver account.';
  }
  if (error instanceof ApiError) {
    return error.message;
  }
  return 'Unable to load the active trip.';
}

function transitionErrorMessage(error: unknown) {
  if (error instanceof ApiError && error.status === 400) {
    return 'The trip action was not accepted. Refresh the trip and try again.';
  }
  if (error instanceof ApiError && error.status === 401) {
    return 'Your driver session has expired. Sign in again before updating this trip.';
  }
  if (error instanceof ApiError && error.status === 404) {
    return 'This trip is unavailable or is no longer assigned to your driver account.';
  }
  if (error instanceof ApiError) {
    return error.message;
  }
  return 'Unable to update the trip. Please try again.';
}

function requestConfirmation(
  action: DriverTripExecutionAction,
  onConfirm: () => void,
  onCancel: () => void,
) {
  const message = `Confirm “${ACTION_LABELS[action]}”?`;
  if (Platform.OS === 'web') {
    if (globalThis.confirm(message)) {
      onConfirm();
    } else {
      onCancel();
    }
    return;
  }
  Alert.alert(
    'Confirm trip action',
    message,
    [
      { text: 'Cancel', style: 'cancel', onPress: onCancel },
      { text: 'Confirm', onPress: onConfirm },
    ],
    { cancelable: true, onDismiss: onCancel },
  );
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

export default function ActiveTripScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ tripId?: string | string[] }>();
  const tripId = Array.isArray(params.tripId) ? params.tripId[0] : params.tripId;
  const [trip, setTrip] = useState<DriverTrip | null>(null);
  const [isLoading, setIsLoading] = useState(Boolean(tripId));
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [route, setRoute] = useState<DriverTripRoute | null>(null);
  const [routeState, setRouteState] = useState<'loading' | 'ready' | 'error'>(
    tripId ? 'loading' : 'error',
  );
  const [vehiclePosition, setVehiclePosition] = useState<DriverVehiclePosition | null>(null);
  const [positionState, setPositionState] = useState<'loading' | 'ready' | 'error'>(
    tripId ? 'loading' : 'error',
  );
  const transitionInFlight = useRef(false);
  const confirmationPending = useRef(false);

  const loadTrip = useCallback(
    async (signal?: AbortSignal) => {
      if (!tripId) {
        setTrip(null);
        setError('No trip was selected. Return to My Trips and choose an assignment.');
        setIsLoading(false);
        return;
      }
      setIsLoading(true);
      setError(null);
      try {
        setTrip(await getDriverTrip(tripId, signal));
      } catch (loadError) {
        if (loadError instanceof Error && loadError.name === 'AbortError') {
          return;
        }
        setTrip(null);
        setError(loadErrorMessage(loadError));
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

  useEffect(() => {
    if (!tripId) {
      return;
    }
    const controller = new AbortController();
    setRouteState('loading');
    void getDriverTripRoute(tripId, controller.signal)
      .then((result) => {
        setRoute(result);
        setRouteState('ready');
      })
      .catch((routeError: unknown) => {
        if (routeError instanceof Error && routeError.name === 'AbortError') {
          return;
        }
        setRoute(null);
        setRouteState('error');
      });
    return () => controller.abort();
  }, [tripId]);

  useEffect(() => {
    if (!tripId || !trip || trip.execution.status === 'COMPLETED') {
      return;
    }
    let active = true;
    let controller: AbortController | null = null;
    setPositionState('loading');

    const fetchPosition = async () => {
      controller?.abort();
      controller = new AbortController();
      try {
        const result = await getDriverTripVehiclePosition(tripId, controller.signal);
        if (active) {
          setVehiclePosition(result);
          setPositionState('ready');
        }
      } catch (positionError) {
        if (positionError instanceof Error && positionError.name === 'AbortError') {
          return;
        }
        if (active) {
          setVehiclePosition(null);
          setPositionState('error');
        }
      }
    };

    void fetchPosition();
    const interval = setInterval(() => void fetchPosition(), VEHICLE_POSITION_POLL_INTERVAL_MS);
    return () => {
      active = false;
      clearInterval(interval);
      controller?.abort();
    };
  }, [trip, tripId]);

  const submitAction = useCallback(
    async (action: DriverTripExecutionAction) => {
      if (!tripId || transitionInFlight.current) {
        return;
      }
      transitionInFlight.current = true;
      setIsTransitioning(true);
      setError(null);
      try {
        const execution = await transitionDriverTrip(tripId, action);
        setTrip((current) => (current ? { ...current, execution } : current));
      } catch (transitionError) {
        if (transitionError instanceof ApiError && transitionError.status === 409) {
          try {
            const refreshedTrip = await getDriverTrip(tripId);
            setTrip(refreshedTrip);
            setError('The trip state changed. The latest server status has been loaded.');
          } catch (refreshError) {
            setTrip(null);
            setError(loadErrorMessage(refreshError));
          }
        } else {
          if (
            transitionError instanceof ApiError &&
            (transitionError.status === 401 || transitionError.status === 404)
          ) {
            setTrip(null);
          }
          setError(transitionErrorMessage(transitionError));
        }
      } finally {
        transitionInFlight.current = false;
        setIsTransitioning(false);
      }
    },
    [tripId],
  );

  const handleAction = useCallback(
    (action: DriverTripExecutionAction) => {
      if (transitionInFlight.current || confirmationPending.current) {
        return;
      }
      if (!CONFIRMED_ACTIONS.has(action)) {
        void submitAction(action);
        return;
      }
      confirmationPending.current = true;
      setIsConfirming(true);
      requestConfirmation(
        action,
        () => {
          confirmationPending.current = false;
          setIsConfirming(false);
          void submitAction(action);
        },
        () => {
          confirmationPending.current = false;
          setIsConfirming(false);
        },
      );
    },
    [submitAction],
  );

  const allowedActions = trip?.execution.allowedActions ?? [];
  const primaryAction = allowedActions.length === 1 ? allowedActions[0] : null;
  const hasActionConflict = allowedActions.length > 1;
  const currentStageIndex = trip
    ? EXECUTION_STAGES.findIndex((stage) => stage.status === trip.execution.status)
    : -1;

  return (
    <AppScreen
      title="Active Trip"
      description={trip ? `${trip.requestNumber} · ${trip.execution.statusLabel}` : undefined}>
      {isLoading ? (
        <View style={styles.stateCard}>
          <ActivityIndicator color={colors.burgundy} size="large" />
          <Text style={styles.stateText}>Loading active trip…</Text>
        </View>
      ) : !trip ? (
        <>
          <EmptyState title="Trip unavailable" message={error ?? 'No active trip was selected.'} />
          <AppButton label="Back to My Trips" onPress={() => router.replace('/(tabs)')} />
        </>
      ) : (
        <>
          <View style={styles.summaryCard}>
            <View style={styles.summaryHeader}>
              <View style={styles.summaryCopy}>
                <Text style={styles.requestNumber}>{trip.requestNumber}</Text>
                <Text style={styles.tripType}>{trip.requestTypeLabel}</Text>
              </View>
              <View style={styles.statusBadge}>
                <Text style={styles.statusText}>{trip.execution.statusLabel}</Text>
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
            <Text style={styles.sectionTitle}>Route and vehicle position</Text>
            <View style={styles.mapPlaceholder}>
              <Text style={styles.mapPlaceholderTitle}>
                {routeState === 'loading'
                  ? 'Loading TomTom road route…'
                  : routeState === 'ready'
                    ? 'TomTom road route loaded'
                    : 'Route currently unavailable'}
              </Text>
              <Text style={styles.mapPlaceholderText}>
                In-app map display is unavailable until this build has an approved mobile map
                renderer and client-safe TomTom Map Display credential.
              </Text>
            </View>
            {positionState === 'loading' ? (
              <Text style={styles.operationalNote}>Loading assigned-vehicle position…</Text>
            ) : positionState === 'error' || !vehiclePosition ? (
              <Text style={styles.operationalNote}>Vehicle location unavailable.</Text>
            ) : (
              <View style={styles.positionRow}>
                <View
                  style={[
                    styles.positionIndicator,
                    vehiclePosition.isStale && styles.stalePositionIndicator,
                  ]}
                />
                <View style={styles.positionCopy}>
                  <Text style={styles.positionTitle}>
                    {vehiclePosition.isStale
                      ? 'Last known vehicle position is stale'
                      : 'Vehicle position is current'}
                  </Text>
                  <Text style={styles.operationalNote}>
                    Recorded {formatDateTime(vehiclePosition.recordedAt)}
                  </Text>
                </View>
              </View>
            )}
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Trip facts</Text>
            <View style={styles.factsGrid}>
              <Fact label="Scheduled pickup" value={formatDateTime(trip.scheduledPickupAt)} />
              <Fact
                label="Vehicle"
                value={`${trip.vehicle.displayName} · ${trip.vehicle.plateNumber}`}
              />
              <Fact label="Passengers" value={String(trip.passengerCount)} />
              <Fact
                label="Request type"
                value={trip.requestCategoryLabel ?? trip.requestTypeLabel}
              />
              {route ? (
                <Fact label="Road distance" value={formatDistance(route.distanceMeters)} />
              ) : null}
              {route ? (
                <Fact label="TomTom travel time" value={formatDuration(route.durationSeconds)} />
              ) : null}
              {route && route.trafficDelaySeconds > 0 ? (
                <Fact
                  label="Traffic delay"
                  value={formatDuration(route.trafficDelaySeconds)}
                />
              ) : null}
            </View>
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Execution timeline</Text>
            <View style={styles.timeline}>
              {EXECUTION_STAGES.map((stage, index) => {
                const stageState =
                  index < currentStageIndex
                    ? 'complete'
                    : index === currentStageIndex
                      ? 'current'
                      : 'upcoming';
                const timestamp = stage.timestamp ? trip.execution[stage.timestamp] : null;
                return (
                  <View key={stage.status} style={styles.timelineRow}>
                    <View
                      style={[
                        styles.timelineMarker,
                        stageState === 'complete' && styles.completeMarker,
                        stageState === 'current' && styles.currentMarker,
                      ]}
                    />
                    <View style={styles.timelineCopy}>
                      <Text
                        style={[
                          styles.timelineLabel,
                          stageState === 'current' && styles.currentTimelineLabel,
                          stageState === 'upcoming' && styles.upcomingTimelineLabel,
                        ]}>
                        {stage.label}
                      </Text>
                      {timestamp ? (
                        <Text style={styles.timelineTime}>{formatDateTime(timestamp)}</Text>
                      ) : null}
                    </View>
                  </View>
                );
              })}
            </View>
          </View>

          {error ? (
            <View style={styles.messageCard}>
              <Text style={styles.messageText}>{error}</Text>
            </View>
          ) : null}

          {hasActionConflict ? (
            <View style={styles.messageCard}>
              <Text style={styles.messageText}>
                Multiple trip actions were returned. Refresh before continuing.
              </Text>
              <AppButton label="Refresh Trip" variant="secondary" onPress={() => void loadTrip()} />
            </View>
          ) : primaryAction ? (
            <AppButton
              disabled={isTransitioning || isConfirming}
              label={isTransitioning ? 'Updating…' : ACTION_LABELS[primaryAction]}
              onPress={() => handleAction(primaryAction)}
            />
          ) : trip.execution.status === 'COMPLETED' ? (
            <View style={styles.completedCard}>
              <Text style={styles.completedTitle}>Trip Completed</Text>
              {trip.execution.completedAt ? (
                <Text style={styles.completedTime}>
                  Completed {formatDateTime(trip.execution.completedAt)}
                </Text>
              ) : null}
              <AppButton label="Back to My Trips" onPress={() => router.replace('/(tabs)')} />
            </View>
          ) : (
            <View style={styles.messageCard}>
              <Text style={styles.messageText}>
                No execution action is currently available from the server.
              </Text>
              <AppButton label="Refresh Trip" variant="secondary" onPress={() => void loadTrip()} />
            </View>
          )}
        </>
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
  stateText: { color: colors.muted, fontSize: 14, textAlign: 'center' },
  summaryCard: {
    padding: spacing.lg,
    gap: spacing.lg,
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 12,
  },
  summaryHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.sm },
  summaryCopy: { flex: 1, gap: 2 },
  requestNumber: { color: colors.ink, fontSize: 19, fontWeight: '800' },
  tripType: { color: colors.muted, fontSize: 13 },
  statusBadge: {
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    backgroundColor: colors.burgundySoft,
    borderRadius: 999,
  },
  statusText: { color: colors.burgundy, fontSize: 11, fontWeight: '800' },
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
  mapPlaceholder: {
    minHeight: 190,
    justifyContent: 'center',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.xl,
    backgroundColor: colors.canvas,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 10,
  },
  mapPlaceholderTitle: { color: colors.ink, fontSize: 16, fontWeight: '800' },
  mapPlaceholderText: {
    maxWidth: 460,
    color: colors.muted,
    fontSize: 13,
    lineHeight: 18,
    textAlign: 'center',
  },
  operationalNote: { color: colors.muted, fontSize: 13, lineHeight: 18 },
  positionRow: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.sm },
  positionIndicator: {
    width: 10,
    height: 10,
    marginTop: 4,
    borderRadius: 5,
    backgroundColor: colors.positive,
  },
  stalePositionIndicator: { backgroundColor: colors.warning },
  positionCopy: { flex: 1, gap: 2 },
  positionTitle: { color: colors.ink, fontSize: 14, fontWeight: '700' },
  timeline: { gap: spacing.sm },
  timelineRow: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  timelineMarker: {
    width: 14,
    height: 14,
    marginTop: 3,
    borderRadius: 7,
    borderColor: colors.border,
    borderWidth: 2,
    backgroundColor: colors.surface,
  },
  completeMarker: { borderColor: colors.positive, backgroundColor: colors.positive },
  currentMarker: { borderColor: colors.burgundy, backgroundColor: colors.burgundy },
  timelineCopy: { flex: 1, gap: 2, paddingBottom: spacing.sm },
  timelineLabel: { color: colors.positive, fontSize: 14, fontWeight: '700' },
  currentTimelineLabel: { color: colors.burgundy },
  upcomingTimelineLabel: { color: colors.muted, fontWeight: '500' },
  timelineTime: { color: colors.muted, fontSize: 12 },
  messageCard: {
    gap: spacing.md,
    padding: spacing.lg,
    backgroundColor: '#fff4df',
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 12,
  },
  messageText: { color: colors.warning, fontSize: 14, lineHeight: 20 },
  completedCard: {
    gap: spacing.md,
    padding: spacing.lg,
    backgroundColor: '#e4f3ec',
    borderRadius: 12,
  },
  completedTitle: { color: colors.positive, fontSize: 20, fontWeight: '800' },
  completedTime: { color: colors.positive, fontSize: 14 },
});
