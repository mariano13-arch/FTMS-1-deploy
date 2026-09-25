import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { AppButton } from '@/components/AppButton';
import { AppScreen } from '@/components/AppScreen';
import { ApiError } from '@/services/api';
import { getTelemetryDevice, getVehicle, pairTelemetryDevice } from '@/services/fleet';
import { colors, spacing } from '@/theme';
import type { TelemetryDevice, Vehicle } from '@/types';

export default function ConfirmPairingScreen() {
  const router = useRouter();
  const { vehicleDeviceId, scannedDeviceId, registryResult } = useLocalSearchParams<{
    vehicleDeviceId: string;
    scannedDeviceId: string;
    registryResult?: 'existing' | 'registered';
  }>();
  const [vehicle, setVehicle] = useState<Vehicle | null>(null);
  const [device, setDevice] = useState<TelemetryDevice | null>(null);
  const [replacementAccepted, setReplacementAccepted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    if (!vehicleDeviceId || !scannedDeviceId) return () => controller.abort();
    Promise.all([
      getVehicle(vehicleDeviceId, controller.signal),
      getTelemetryDevice(scannedDeviceId, controller.signal),
    ])
      .then(([vehicleResult, deviceResult]) => {
        setVehicle(vehicleResult);
        setDevice(deviceResult);
      })
      .catch((loadError: unknown) => {
        if (loadError instanceof Error && loadError.name === 'AbortError') return;
        setError(loadError instanceof ApiError ? loadError.message : 'Unable to review pairing.');
      });
    return () => controller.abort();
  }, [scannedDeviceId, vehicleDeviceId]);

  const pairedElsewhere = Boolean(
    device?.currentVehicle && vehicle && device.currentVehicle.vehicleId !== vehicle.id,
  );
  const alreadyPaired = Boolean(
    device?.currentVehicle && vehicle && device.currentVehicle.vehicleId === vehicle.id,
  );
  const replacement = Boolean(
    vehicle?.currentTelemetryDevice &&
      device &&
      vehicle.currentTelemetryDevice.deviceId !== device.deviceId,
  );
  const deviceOperational = device?.registrationStatus === 'REGISTERED';
  const canConfirm = useMemo(
    () =>
      Boolean(vehicle && device) &&
      !pairedElsewhere &&
      !alreadyPaired &&
      deviceOperational &&
      (!replacement || replacementAccepted) &&
      !submitting,
    [
      alreadyPaired,
      device,
      deviceOperational,
      pairedElsewhere,
      replacement,
      replacementAccepted,
      submitting,
      vehicle,
    ],
  );

  async function confirm() {
    if (!canConfirm || !vehicle || !device) return;
    setSubmitting(true);
    setError(null);
    try {
      await pairTelemetryDevice(device.deviceId, vehicle.id, replacement);
      const [freshVehicle, freshDevice] = await Promise.all([
        getVehicle(vehicle.compatibilityDeviceId),
        getTelemetryDevice(device.deviceId),
      ]);
      setVehicle(freshVehicle);
      setDevice(freshDevice);
      setSuccess(true);
    } catch (pairError) {
      setError(pairError instanceof ApiError ? pairError.message : 'Unable to pair device.');
    } finally {
      setSubmitting(false);
    }
  }

  if (success && vehicle && device) {
    return (
      <AppScreen title="Pairing complete" description={`${device.deviceId} is now the current telemetry source for ${vehicle.displayName}.`}>
        <View style={styles.successCard}>
          <Text style={styles.success}>Authoritative pairing confirmed</Text>
          <Text style={styles.value}>{vehicle.plateNumber} · {device.deviceId}</Text>
        </View>
        <AppButton
          label="Return to Vehicle"
          onPress={() => router.replace(`/vehicles/${encodeURIComponent(vehicle.compatibilityDeviceId)}`)}
        />
      </AppScreen>
    );
  }

  return (
    <AppScreen title="Confirm Pairing" description="Review the authoritative vehicle and device before making changes.">
      {!vehicle && !device && !error ? <ActivityIndicator color={colors.burgundy} size="large" /> : null}
      {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
      {vehicle && device ? (
        <>
          {registryResult === 'existing' ? (
            <Text style={styles.info}>Device already registered. Review its current binding before continuing.</Text>
          ) : null}
          {registryResult === 'registered' ? (
            <Text style={styles.success}>Device registered. It remains unpaired until you explicitly confirm pairing.</Text>
          ) : null}
          <View style={styles.card}>
            <Detail label="Vehicle" value={`${vehicle.displayName} / ${vehicle.plateNumber}`} />
            <Detail label="Device" value={device.deviceId} />
            <Detail label="Registration" value={device.registrationStatus} />
            <Detail
              label="Current pairing"
              value={device.currentVehicle
                ? `${device.currentVehicle.displayName} / ${device.currentVehicle.plateNumber}`
                : 'Unpaired'}
            />
          </View>
          {pairedElsewhere ? (
            <Text accessibilityRole="alert" style={styles.error}>
              This device is paired to another vehicle. Unpair it explicitly before reassignment.
            </Text>
          ) : null}
          {alreadyPaired ? (
            <Text style={styles.success}>This device is already paired to the selected vehicle.</Text>
          ) : null}
          {!deviceOperational ? (
            <Text accessibilityRole="alert" style={styles.error}>
              This device is not registered for operation and cannot be paired.
            </Text>
          ) : null}
          {replacement ? (
            <View style={styles.warningCard}>
              <Text style={styles.warningTitle}>Device replacement</Text>
              <Text style={styles.warning}>
                Current device: {vehicle.currentTelemetryDevice?.deviceId}{'\n'}
                New device: {device.deviceId}{'\n'}
                The new device will become the future telemetry source. Existing history will remain unchanged.
              </Text>
              <Pressable
                accessibilityRole="checkbox"
                accessibilityState={{ checked: replacementAccepted }}
                onPress={() => setReplacementAccepted((value) => !value)}
                style={styles.checkboxRow}>
                <View style={[styles.checkbox, replacementAccepted && styles.checkboxChecked]} />
                <Text style={styles.checkboxLabel}>I understand and confirm this replacement.</Text>
              </Pressable>
            </View>
          ) : null}
          <AppButton
            disabled={!canConfirm}
            label={submitting ? 'Pairing…' : replacement ? 'Confirm Replacement' : 'Confirm Pairing'}
            onPress={() => void confirm()}
          />
          <AppButton label="Cancel" onPress={() => router.back()} variant="secondary" />
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
  detailRow: { gap: spacing.xs },
  label: { color: colors.muted, fontSize: 12, fontWeight: '700', textTransform: 'uppercase' },
  value: { color: colors.ink, fontSize: 16 },
  error: { color: colors.danger, lineHeight: 20 },
  success: { color: colors.positive, fontWeight: '800' },
  info: { color: colors.ink, fontWeight: '700', lineHeight: 20 },
  successCard: { gap: spacing.sm, padding: spacing.lg, backgroundColor: colors.surface, borderRadius: 12 },
  warningCard: { gap: spacing.md, padding: spacing.lg, backgroundColor: colors.burgundySoft, borderRadius: 12 },
  warningTitle: { color: colors.warning, fontWeight: '800', fontSize: 16 },
  warning: { color: colors.ink, lineHeight: 21 },
  checkboxRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  checkbox: { width: 22, height: 22, borderRadius: 4, borderWidth: 2, borderColor: colors.burgundy },
  checkboxChecked: { backgroundColor: colors.burgundy },
  checkboxLabel: { flex: 1, color: colors.ink, fontWeight: '700' },
});
