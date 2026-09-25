import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Alert, StyleSheet, Text, View } from 'react-native';

import { AppButton } from '@/components/AppButton';
import { AppScreen } from '@/components/AppScreen';
import { useStaffAuth } from '@/features/auth/StaffAuthContext';
import { ApiError } from '@/services/api';
import { getVehicle, unpairTelemetryDevice } from '@/services/fleet';
import { colors, spacing } from '@/theme';
import type { Vehicle } from '@/types';

export default function VehicleDetailsScreen() {
  const router = useRouter();
  const { staff } = useStaffAuth();
  const { deviceId } = useLocalSearchParams<{ deviceId: string }>();
  const canManageTelemetry = staff?.role === 'FLEET_ADMIN' || staff?.role === 'FLEET_MANAGER';
  const [vehicle, setVehicle] = useState<Vehicle | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!deviceId) return;
    setLoading(true);
    setError(null);
    try {
      setVehicle(await getVehicle(deviceId, signal));
    } catch (loadError) {
      if (loadError instanceof Error && loadError.name === 'AbortError') return;
      setError(loadError instanceof ApiError ? loadError.message : 'Unable to load vehicle.');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [deviceId]);

  useFocusEffect(
    useCallback(() => {
      const controller = new AbortController();
      void load(controller.signal);
      return () => controller.abort();
    }, [load]),
  );

  function confirmUnpair() {
    const current = vehicle?.currentTelemetryDevice;
    if (!current || submitting) return;
    Alert.alert(
      'Unpair telemetry device?',
      `${current.deviceId} will stop being the current telemetry source. Historical telemetry will remain unchanged.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Unpair',
          style: 'destructive',
          onPress: () => {
            setSubmitting(true);
            setError(null);
            void unpairTelemetryDevice(current.deviceId)
              .then(() => load())
              .catch((unpairError: unknown) => {
                setError(unpairError instanceof ApiError ? unpairError.message : 'Unable to unpair device.');
              })
              .finally(() => setSubmitting(false));
          },
        },
      ],
    );
  }

  return (
    <AppScreen title={vehicle?.displayName ?? 'Vehicle Details'}>
      {loading ? <ActivityIndicator color={colors.burgundy} size="large" /> : null}
      {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
      {vehicle ? (
        <>
          <View style={styles.card}>
            <Detail label="Plate number" value={vehicle.plateNumber} />
            <Detail label="Vehicle type" value={vehicle.vehicleType} />
            <Detail
              label="Make / model"
              value={[vehicle.manufacturer, vehicle.model].filter(Boolean).join(' ') || 'Not recorded'}
            />
            <Detail label="Operational status" value={vehicle.isActive ? 'Active' : 'Inactive'} />
          </View>
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Telemetry Device</Text>
            {vehicle.currentTelemetryDevice ? (
              <>
                <Detail label="Current device ID" value={vehicle.currentTelemetryDevice.deviceId} />
                <Detail label="Pairing state" value="Paired" />
                <Detail label="Device registry state" value={vehicle.currentTelemetryDevice.registrationStatus} />
              </>
            ) : (
              <>
                <Detail label="Current device ID" value="None" />
                <Detail label="Pairing state" value="Unpaired" />
              </>
            )}
            {canManageTelemetry ? (
              <>
                <AppButton
                  disabled={!vehicle.isActive}
                  label={vehicle.currentTelemetryDevice ? 'Replace Telemetry Device' : 'Sync Telemetry Device'}
                  onPress={() =>
                    router.push({ pathname: '/scanner', params: { vehicleDeviceId: deviceId } })
                  }
                />
                {vehicle.currentTelemetryDevice ? (
                  <AppButton
                    disabled={submitting}
                    label={submitting ? 'Unpairing…' : 'Unpair Telemetry Device'}
                    onPress={confirmUnpair}
                    variant="danger"
                  />
                ) : null}
              </>
            ) : (
              <Text style={styles.muted}>Telemetry pairing is read-only for Dispatchers.</Text>
            )}
            {!vehicle.isActive ? (
              <Text style={styles.warning}>Inactive vehicles cannot receive a telemetry pairing.</Text>
            ) : null}
          </View>
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Vehicle Inspection</Text>
            {vehicle.latestInspection ? (
              <>
                <Detail label="Latest result" value={vehicle.latestInspection.result} />
                <Detail label="Inspection date" value={vehicle.latestInspection.inspectionDate} />
              </>
            ) : (
              <Text style={styles.muted}>No inspections recorded</Text>
            )}
            <AppButton
              label="Start Inspection"
              onPress={() =>
                router.push({ pathname: '/start-inspection', params: { vehicleDeviceId: deviceId } })
              }
            />
            <AppButton
              label="Inspection History"
              onPress={() =>
                router.push({ pathname: '/inspection-history', params: { vehicleDeviceId: deviceId } })
              }
              variant="secondary"
            />
          </View>
        </>
      ) : null}
    </AppScreen>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.detailRow}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: spacing.md,
    padding: spacing.lg,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  sectionTitle: { color: colors.ink, fontSize: 18, fontWeight: '800' },
  detailRow: { gap: spacing.xs },
  label: { color: colors.muted, fontSize: 12, fontWeight: '700', textTransform: 'uppercase' },
  value: { color: colors.ink, fontSize: 16 },
  muted: { color: colors.muted },
  error: { color: colors.danger },
  warning: { color: colors.warning, lineHeight: 20 },
});
