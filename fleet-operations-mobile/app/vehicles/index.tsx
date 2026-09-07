import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { AppButton } from '@/components/AppButton';
import { AppScreen } from '@/components/AppScreen';
import { useStaffAuth } from '@/features/auth/StaffAuthContext';
import { ApiError } from '@/services/api';
import { getVehicles } from '@/services/fleet';
import { colors, spacing } from '@/theme';
import type { Vehicle } from '@/types';

export default function VehiclesScreen() {
  const router = useRouter();
  const { staff, signOut } = useStaffAuth();
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      setVehicles(await getVehicles(signal));
    } catch (loadError) {
      if (loadError instanceof Error && loadError.name === 'AbortError') return;
      setError(loadError instanceof ApiError ? loadError.message : 'Unable to load vehicles.');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      const controller = new AbortController();
      void load(controller.signal);
      return () => controller.abort();
    }, [load]),
  );

  return (
    <AppScreen title="Vehicles" description={`Signed in as ${staff?.displayName ?? 'fleet staff'}.`}>
      <AppButton label="Sign Out" onPress={() => void signOut()} variant="secondary" />
      {loading ? <ActivityIndicator color={colors.burgundy} size="large" /> : null}
      {error ? (
        <View style={styles.state}>
          <Text accessibilityRole="alert" style={styles.error}>{error}</Text>
          <AppButton label="Retry" onPress={() => void load()} variant="secondary" />
        </View>
      ) : null}
      {!loading && !error && vehicles.length === 0 ? (
        <Text style={styles.muted}>No existing vehicles are available.</Text>
      ) : null}
      {vehicles.map((vehicle) => (
        <Pressable
          accessibilityRole="button"
          key={vehicle.compatibilityDeviceId}
          onPress={() => router.push(`/vehicles/${encodeURIComponent(vehicle.compatibilityDeviceId)}`)}
          style={styles.card}>
          <View style={styles.row}>
            <Text style={styles.name}>{vehicle.displayName}</Text>
            <Text style={vehicle.isActive ? styles.active : styles.inactive}>
              {vehicle.isActive ? 'Active' : 'Inactive'}
            </Text>
          </View>
          <Text style={styles.detail}>{vehicle.plateNumber} · {vehicle.vehicleType}</Text>
          <Text style={styles.device}>
            {vehicle.currentTelemetryDevice
              ? `Device: ${vehicle.currentTelemetryDevice.deviceId}`
              : 'No telemetry device paired'}
          </Text>
        </Pressable>
      ))}
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  state: { gap: spacing.md },
  error: { color: colors.danger },
  muted: { color: colors.muted },
  card: {
    gap: spacing.sm,
    padding: spacing.lg,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  row: { flexDirection: 'row', justifyContent: 'space-between', gap: spacing.md },
  name: { flex: 1, color: colors.ink, fontSize: 17, fontWeight: '800' },
  detail: { color: colors.muted },
  device: { color: colors.burgundy, fontWeight: '700' },
  active: { color: colors.positive, fontWeight: '700' },
  inactive: { color: colors.danger, fontWeight: '700' },
});
