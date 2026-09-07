import { type BarcodeScanningResult, CameraView, useCameraPermissions } from 'expo-camera';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useRef, useState } from 'react';
import { ActivityIndicator, Linking, StyleSheet, Text, View } from 'react-native';

import { AppButton } from '@/components/AppButton';
import { AppScreen } from '@/components/AppScreen';
import { parseTelemetryDeviceQr } from '@/features/pairing/qr';
import { ApiError } from '@/services/api';
import { getTelemetryDevice } from '@/services/fleet';
import { colors, spacing } from '@/theme';

export default function ScannerScreen() {
  const router = useRouter();
  const { vehicleDeviceId } = useLocalSearchParams<{ vehicleDeviceId: string }>();
  const [permission, requestPermission] = useCameraPermissions();
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastValue = useRef<string | null>(null);

  async function scanned(result: BarcodeScanningResult) {
    if (processing || lastValue.current === result.data) return;
    lastValue.current = result.data;
    setProcessing(true);
    setError(null);
    const deviceId = parseTelemetryDeviceQr(result.data);
    if (!deviceId) {
      setError('Invalid FTMS telemetry device QR code.');
      return;
    }
    try {
      await getTelemetryDevice(deviceId);
      router.replace({
        pathname: '/confirm-pairing',
        params: { vehicleDeviceId, scannedDeviceId: deviceId },
      });
    } catch (lookupError) {
      setError(
        lookupError instanceof ApiError && lookupError.status === 404
          ? 'Device not registered in FTMS.'
          : lookupError instanceof ApiError
            ? lookupError.message
            : 'Unable to validate this device.',
      );
    }
  }

  function scanAgain() {
    lastValue.current = null;
    setError(null);
    setProcessing(false);
  }

  if (!permission) {
    return (
      <AppScreen title="Scan Device QR">
        <ActivityIndicator color={colors.burgundy} size="large" />
      </AppScreen>
    );
  }
  if (!permission.granted) {
    return (
      <AppScreen title="Camera permission required" description="Camera access is used only to read telemetry device QR identifiers.">
        {permission.canAskAgain ? (
          <AppButton label="Allow Camera" onPress={() => void requestPermission()} />
        ) : (
          <>
            <Text style={styles.error}>Camera access is denied. Enable it in system settings to scan a device.</Text>
            <AppButton label="Open Settings" onPress={() => void Linking.openSettings()} />
          </>
        )}
      </AppScreen>
    );
  }
  return (
    <AppScreen title="Scan Device QR" description="Align a registered FTMS telemetry device QR code inside the frame." scroll={false}>
      <CameraView
        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
        facing="back"
        onBarcodeScanned={processing ? undefined : (result) => void scanned(result)}
        style={styles.camera}
      />
      {processing ? <ActivityIndicator color={colors.burgundy} /> : null}
      {error ? (
        <View style={styles.errorCard}>
          <Text accessibilityRole="alert" style={styles.error}>{error}</Text>
          <AppButton label="Scan Again" onPress={scanAgain} variant="secondary" />
        </View>
      ) : null}
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  camera: { flex: 1, minHeight: 320, borderRadius: 16, overflow: 'hidden' },
  errorCard: { gap: spacing.sm, padding: spacing.md, backgroundColor: colors.surface, borderRadius: 10 },
  error: { color: colors.danger, lineHeight: 20 },
});
