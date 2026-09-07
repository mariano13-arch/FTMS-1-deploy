import { useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { AppButton } from '@/components/AppButton';
import { AppScreen } from '@/components/AppScreen';
import { ApiError } from '@/services/api';
import { getInspectionDefinition, getInspection } from '@/services/inspections';
import { colors, spacing } from '@/theme';
import type { InspectionDefinition, VehicleInspection } from '@/types';

export default function InspectionDetailScreen() {
  const { vehicleDeviceId, inspectionId } = useLocalSearchParams<{
    vehicleDeviceId: string;
    inspectionId: string;
  }>();
  const [inspection, setInspection] = useState<VehicleInspection | null>(null);
  const [definition, setDefinition] = useState<InspectionDefinition | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load(signal?: AbortSignal) {
    const parsedId = Number(inspectionId);
    if (!vehicleDeviceId || !Number.isInteger(parsedId)) {
      setError('The inspection link is invalid.');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [loadedInspection, loadedDefinition] = await Promise.all([
        getInspection(vehicleDeviceId, parsedId, signal),
        getInspectionDefinition(signal),
      ]);
      setInspection(loadedInspection);
      setDefinition(loadedDefinition);
    } catch (loadError) {
      if (loadError instanceof Error && loadError.name === 'AbortError') return;
      setError(loadError instanceof ApiError ? loadError.message : 'Unable to load inspection.');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [vehicleDeviceId, inspectionId]);

  return (
    <AppScreen title="Inspection Details" description="Read-only saved inspection record">
      {loading ? <ActivityIndicator color={colors.burgundy} size="large" /> : null}
      {error ? (
        <>
          <Text accessibilityRole="alert" style={styles.error}>{error}</Text>
          <AppButton label="Retry" onPress={() => void load()} variant="secondary" />
        </>
      ) : null}
      {inspection ? (
        <>
          <View style={styles.card}>
            <Detail label="Result" value={choiceLabel(definition?.results, inspection.result)} />
            <Detail label="Type" value={choiceLabel(definition?.inspectionTypes, inspection.inspectionType)} />
            <Detail label="Inspection date" value={inspection.inspectionDate} />
            <Detail label="Recorded" value={new Date(inspection.createdAt).toLocaleString()} />
            <Detail label="Inspector" value={inspection.inspectorName} />
          </View>
          <View style={styles.card}>
            <Text style={styles.title}>Checklist</Text>
            {definition?.checklist.map((item) => (
              <Detail
                key={item.field}
                label={item.label}
                value={choiceLabel(item.choices, inspection.conditions[item.field] ?? '')}
              />
            ))}
          </View>
          <View style={styles.card}>
            <Text style={styles.title}>Readings and findings</Text>
            <Detail label="Odometer" value={inspection.odometerKm === null ? 'Not recorded' : `${inspection.odometerKm} km`} />
            <Detail label="Fuel level" value={inspection.fuelLevelPercent === null ? 'Not recorded' : `${inspection.fuelLevelPercent}%`} />
            <Detail label="Issues found" value={inspection.issuesFound || 'None recorded'} />
            <Detail label="Notes" value={inspection.notes || 'None recorded'} />
          </View>
        </>
      ) : null}
    </AppScreen>
  );
}

function choiceLabel(choices: Array<{ value: string; label: string }> | undefined, value: string) {
  return choices?.find((choice) => choice.value === value)?.label ?? value;
}

function Detail({ label, value }: { label: string; value: string }) {
  return <View style={styles.detail}><Text style={styles.label}>{label}</Text><Text style={styles.value}>{value}</Text></View>;
}

const styles = StyleSheet.create({
  card: { gap: spacing.md, padding: spacing.lg, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  title: { color: colors.ink, fontSize: 18, fontWeight: '800' },
  detail: { gap: spacing.xs },
  label: { color: colors.muted, fontSize: 12, fontWeight: '700', textTransform: 'uppercase' },
  value: { color: colors.ink, fontSize: 16, lineHeight: 22 },
  error: { color: colors.danger },
});
