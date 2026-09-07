import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { AppButton } from '@/components/AppButton';
import { AppScreen } from '@/components/AppScreen';
import { ApiError } from '@/services/api';
import { getVehicle } from '@/services/fleet';
import { getInspectionHistory } from '@/services/inspections';
import { colors, spacing } from '@/theme';
import type { Vehicle, VehicleInspection } from '@/types';

export default function InspectionHistoryScreen() {
  const router = useRouter();
  const { vehicleDeviceId } = useLocalSearchParams<{ vehicleDeviceId: string }>();
  const [vehicle, setVehicle] = useState<Vehicle | null>(null);
  const [inspections, setInspections] = useState<VehicleInspection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!vehicleDeviceId) {
      setError('No vehicle was selected.');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [loadedVehicle, history] = await Promise.all([
        getVehicle(vehicleDeviceId, signal),
        getInspectionHistory(vehicleDeviceId, signal),
      ]);
      setVehicle(loadedVehicle);
      setInspections(history);
    } catch (loadError) {
      if (loadError instanceof Error && loadError.name === 'AbortError') return;
      setError(loadError instanceof ApiError ? loadError.message : 'Unable to load inspection history.');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [vehicleDeviceId]);

  useFocusEffect(useCallback(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]));

  return (
    <AppScreen
      title="Inspection History"
      description={vehicle ? `${vehicle.displayName} · ${vehicle.plateNumber}` : undefined}>
      {loading ? <ActivityIndicator color={colors.burgundy} size="large" /> : null}
      {error ? (
        <>
          <Text accessibilityRole="alert" style={styles.error}>{error}</Text>
          <AppButton label="Retry" onPress={() => void load()} variant="secondary" />
        </>
      ) : null}
      {!loading && !error && inspections.length === 0 ? (
        <View style={styles.empty}><Text style={styles.muted}>No inspections recorded for this vehicle.</Text></View>
      ) : null}
      {inspections.map((inspection) => (
        <Pressable
          accessibilityRole="button"
          key={inspection.id}
          onPress={() => router.push({
            pathname: '/inspection-detail',
            params: { vehicleDeviceId, inspectionId: String(inspection.id) },
          })}
          style={({ pressed }) => [styles.card, pressed && styles.pressed]}>
          <View style={styles.row}>
            <Text style={styles.result}>{inspection.result}</Text>
            <Text style={styles.date}>{inspection.inspectionDate}</Text>
          </View>
          <Text style={styles.muted}>{inspection.inspectionType} · {inspection.inspectorName}</Text>
          {inspection.issuesFound ? <Text style={styles.findings}>{inspection.issuesFound}</Text> : null}
        </Pressable>
      ))}
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  card: { gap: spacing.sm, padding: spacing.lg, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  row: { flexDirection: 'row', justifyContent: 'space-between', gap: spacing.md },
  result: { color: colors.ink, fontWeight: '800' },
  date: { color: colors.muted },
  findings: { color: colors.ink, lineHeight: 20 },
  muted: { color: colors.muted },
  empty: { padding: spacing.xl, borderRadius: 12, backgroundColor: colors.surface, alignItems: 'center' },
  error: { color: colors.danger },
  pressed: { opacity: 0.75 },
});
