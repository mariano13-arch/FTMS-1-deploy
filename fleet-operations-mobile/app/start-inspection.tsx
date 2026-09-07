import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, TextInput, View } from 'react-native';

import { AppButton } from '@/components/AppButton';
import { AppScreen } from '@/components/AppScreen';
import { ApiError } from '@/services/api';
import { getVehicle } from '@/services/fleet';
import {
  getInspection,
  getInspectionDefinition,
  submitInspection,
} from '@/services/inspections';
import { colors, spacing } from '@/theme';
import type { InspectionDefinition, Vehicle, VehicleInspection } from '@/types';

export default function StartInspectionScreen() {
  const router = useRouter();
  const { vehicleDeviceId } = useLocalSearchParams<{ vehicleDeviceId: string }>();
  const [vehicle, setVehicle] = useState<Vehicle | null>(null);
  const [definition, setDefinition] = useState<InspectionDefinition | null>(null);
  const [conditions, setConditions] = useState<Record<string, string>>({});
  const [inspectionType, setInspectionType] = useState('');
  const [result, setResult] = useState('');
  const [odometer, setOdometer] = useState('');
  const [fuelLevel, setFuelLevel] = useState('');
  const [issuesFound, setIssuesFound] = useState('');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<VehicleInspection | null>(null);
  const submissionInFlight = useRef(false);
  const idempotencyKey = useRef(
    `fleet-inspection-${Date.now()}-${Math.random().toString(36).slice(2)}`,
  ).current;

  useEffect(() => {
    const controller = new AbortController();
    if (!vehicleDeviceId) {
      setError('No vehicle was selected.');
      setLoading(false);
      return () => controller.abort();
    }
    Promise.all([
      getVehicle(vehicleDeviceId, controller.signal),
      getInspectionDefinition(controller.signal),
    ])
      .then(([loadedVehicle, loadedDefinition]) => {
        setVehicle(loadedVehicle);
        setDefinition(loadedDefinition);
      })
      .catch((loadError: unknown) => {
        if (loadError instanceof Error && loadError.name === 'AbortError') return;
        setError(loadError instanceof ApiError ? loadError.message : 'Unable to load inspection.');
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [vehicleDeviceId]);

  async function submit() {
    if (!vehicleDeviceId || !definition || submissionInFlight.current) return;
    const missingChecklist = definition.checklist.some(
      (item) => item.required && !conditions[item.field],
    );
    if (!inspectionType || !result || missingChecklist) {
      setError('Choose an inspection type, result, and response for every required checklist item.');
      return;
    }
    const parsedOdometer = odometer ? Number(odometer) : undefined;
    const parsedFuelLevel = fuelLevel ? Number(fuelLevel) : undefined;
    if (
      (parsedOdometer !== undefined && (!Number.isInteger(parsedOdometer) || parsedOdometer < 0)) ||
      (parsedFuelLevel !== undefined &&
        (!Number.isInteger(parsedFuelLevel) || parsedFuelLevel < 0 || parsedFuelLevel > 100))
    ) {
      setError('Odometer must be a non-negative whole number and fuel level must be 0–100.');
      return;
    }
    submissionInFlight.current = true;
    setPending(true);
    setError(null);
    try {
      const created = await submitInspection(
        vehicleDeviceId,
        {
          inspection_type: inspectionType,
          result,
          ...conditions,
          odometer_km: parsedOdometer,
          fuel_level_percent: parsedFuelLevel,
          issues_found: issuesFound,
          notes,
        },
        idempotencyKey,
      );
      const [, authoritativeInspection] = await Promise.all([
        getVehicle(vehicleDeviceId),
        getInspection(vehicleDeviceId, created.id),
      ]);
      setSaved(authoritativeInspection);
    } catch (submitError) {
      setError(submitError instanceof ApiError ? submitError.message : 'Unable to submit inspection.');
    } finally {
      submissionInFlight.current = false;
      setPending(false);
    }
  }

  if (saved) {
    return (
      <AppScreen title="Inspection Submitted" description="The saved FTMS record was confirmed.">
        <View style={styles.card}>
          <Detail label="Vehicle" value={vehicle?.plateNumber ?? vehicleDeviceId ?? ''} />
          <Detail label="Result" value={saved.result} />
          <Detail label="Inspector" value={saved.inspectorName} />
          <Detail label="Recorded" value={new Date(saved.createdAt).toLocaleString()} />
        </View>
        <AppButton
          label="View Inspection History"
          onPress={() =>
            router.replace({ pathname: '/inspection-history', params: { vehicleDeviceId } })
          }
        />
        <AppButton label="Back to Vehicle" onPress={() => router.back()} variant="secondary" />
      </AppScreen>
    );
  }

  return (
    <AppScreen
      title="Start Inspection"
      description={vehicle ? `${vehicle.displayName} · ${vehicle.plateNumber}` : undefined}>
      {loading ? <ActivityIndicator color={colors.burgundy} size="large" /> : null}
      {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
      {definition ? (
        <>
          <ChoiceSection
            label="Inspection type"
            choices={definition.inspectionTypes}
            value={inspectionType}
            onChange={setInspectionType}
          />
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Checklist</Text>
            {definition.checklist.map((item) => (
              <ChoiceSection
                key={item.field}
                label={`${item.label}${item.required ? ' *' : ''}`}
                choices={item.choices}
                value={conditions[item.field] ?? ''}
                onChange={(value) => setConditions((current) => ({ ...current, [item.field]: value }))}
                nested
              />
            ))}
          </View>
          <ChoiceSection
            label="Inspection result"
            choices={definition.results}
            value={result}
            onChange={setResult}
          />
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Readings and findings</Text>
            <Field label="Odometer (km)" value={odometer} onChangeText={setOdometer} numeric />
            <Field label="Fuel level (%)" value={fuelLevel} onChangeText={setFuelLevel} numeric />
            <Field label="Issues found" value={issuesFound} onChangeText={setIssuesFound} multiline />
            <Field label="Notes" value={notes} onChangeText={setNotes} multiline />
          </View>
          <Text style={styles.muted}>* Required. The server records the inspection date and inspector.</Text>
          <AppButton
            disabled={pending}
            label={pending ? 'Submitting…' : 'Submit Inspection'}
            onPress={() => void submit()}
          />
        </>
      ) : null}
    </AppScreen>
  );
}

function ChoiceSection({ label, choices, value, onChange, nested = false }: {
  label: string;
  choices: Array<{ value: string; label: string }>;
  value: string;
  onChange: (value: string) => void;
  nested?: boolean;
}) {
  return (
    <View style={nested ? styles.nestedChoice : styles.card}>
      <Text style={nested ? styles.choiceLabel : styles.sectionTitle}>{label}</Text>
      <View style={styles.choiceRow}>
        {choices.map((choice) => (
          <AppButton
            key={choice.value}
            label={choice.label}
            onPress={() => onChange(choice.value)}
            style={styles.choiceButton}
            variant={value === choice.value ? 'primary' : 'secondary'}
          />
        ))}
      </View>
    </View>
  );
}

function Field({ label, value, onChangeText, numeric = false, multiline = false }: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  numeric?: boolean;
  multiline?: boolean;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.choiceLabel}>{label}</Text>
      <TextInput
        keyboardType={numeric ? 'number-pad' : 'default'}
        multiline={multiline}
        onChangeText={onChangeText}
        style={[styles.input, multiline && styles.multiline]}
        value={value}
      />
    </View>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return <View style={styles.field}><Text style={styles.choiceLabel}>{label}</Text><Text>{value}</Text></View>;
}

const styles = StyleSheet.create({
  card: { gap: spacing.md, padding: spacing.lg, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  sectionTitle: { color: colors.ink, fontSize: 18, fontWeight: '800' },
  nestedChoice: { gap: spacing.sm, paddingVertical: spacing.sm },
  choiceLabel: { color: colors.ink, fontSize: 14, fontWeight: '700' },
  choiceRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  choiceButton: { flexGrow: 1, minWidth: 120 },
  field: { gap: spacing.sm },
  input: { minHeight: 46, borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.surface, padding: spacing.md, color: colors.ink },
  multiline: { minHeight: 92, textAlignVertical: 'top' },
  muted: { color: colors.muted },
  error: { color: colors.danger, lineHeight: 20 },
});
