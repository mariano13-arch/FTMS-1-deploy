import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { AppButton } from '@/components/AppButton';
import { AppScreen } from '@/components/AppScreen';
import { ApiError } from '@/services/api';
import { getVehicle } from '@/services/fleet';
import { colors, spacing } from '@/theme';
import type { Vehicle } from '@/types';

export default function PairDeviceScreen() {
  const router = useRouter();
  const { vehicleDeviceId } = useLocalSearchParams<{ vehicleDeviceId: string }>();
  const [vehicle, setVehicle] = useState<Vehicle | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    if (vehicleDeviceId) {
      getVehicle(vehicleDeviceId, controller.signal).then(setVehicle).catch((loadError: unknown) => {
        if (loadError instanceof Error && loadError.name === 'AbortError') return;
        setError(loadError instanceof ApiError ? loadError.message : 'Unable to load vehicle.');
      });
    }
    return () => controller.abort();
  }, [vehicleDeviceId]);

  return (
    <AppScreen
      title={vehicle?.currentTelemetryDevice ? 'Replace Telemetry Device' : 'Sync Telemetry Device'}
      description="Scan only a registered FTMS telemetry device identifier.">
      {!vehicle && !error ? <ActivityIndicator color={colors.burgundy} size="large" /> : null}
      {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
      {vehicle ? (
        <View style={styles.card}>
          <Text style={styles.name}>{vehicle.displayName}</Text>
          <Text style={styles.detail}>{vehicle.plateNumber} · {vehicle.vehicleType}</Text>
          <Text style={styles.detail}>
            {vehicle.currentTelemetryDevice
              ? `Current device: ${vehicle.currentTelemetryDevice.deviceId}`
              : 'No current telemetry device'}
          </Text>
          <AppButton
            label="Scan Device QR"
            onPress={() =>
              router.push({ pathname: '/scanner', params: { vehicleDeviceId } })
            }
          />
          <Text style={styles.note}>QR codes are identifiers only. Pairing still requires your authenticated staff session.</Text>
        </View>
      ) : null}
    </AppScreen>
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
  name: { color: colors.ink, fontSize: 18, fontWeight: '800' },
  detail: { color: colors.muted },
  note: { color: colors.muted, fontSize: 13, lineHeight: 18 },
  error: { color: colors.danger },
});
