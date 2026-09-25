import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { StaffAuthProvider, useStaffAuth } from '@/features/auth/StaffAuthContext';
import { colors } from '@/theme';

export default function RootLayout() {
  return (
    <StaffAuthProvider>
      <Navigator />
    </StaffAuthProvider>
  );
}

function Navigator() {
  const { staff, isBootstrapping } = useStaffAuth();
  const canManageTelemetry = staff?.role === 'FLEET_ADMIN' || staff?.role === 'FLEET_MANAGER';
  if (isBootstrapping) {
    return (
      <View style={styles.loading}>
        <ActivityIndicator color={colors.burgundy} size="large" />
      </View>
    );
  }
  return (
    <>
      <StatusBar style="dark" />
      <Stack
        screenOptions={{
          headerBackButtonDisplayMode: 'minimal',
          headerTintColor: colors.burgundy,
          headerTitleStyle: { color: colors.ink, fontWeight: '700' },
          headerShadowVisible: false,
          contentStyle: { backgroundColor: colors.canvas },
        }}>
        <Stack.Protected guard={!staff}>
          <Stack.Screen name="index" options={{ headerShown: false }} />
        </Stack.Protected>
        <Stack.Protected guard={Boolean(staff)}>
          <Stack.Screen name="vehicles/index" options={{ title: 'Vehicles', headerBackVisible: false }} />
          <Stack.Screen name="vehicles/[deviceId]" options={{ title: 'Vehicle Details' }} />
          <Stack.Protected guard={canManageTelemetry}>
            <Stack.Screen name="pair-device" options={{ title: 'Sync Telemetry Device' }} />
            <Stack.Screen name="scanner" options={{ title: 'Scan Device QR' }} />
            <Stack.Screen name="confirm-pairing" options={{ title: 'Confirm Pairing' }} />
          </Stack.Protected>
          <Stack.Screen name="start-inspection" options={{ title: 'Vehicle Inspection' }} />
          <Stack.Screen name="inspection-history" options={{ title: 'Inspection History' }} />
          <Stack.Screen name="inspection-detail" options={{ title: 'Inspection Details' }} />
        </Stack.Protected>
      </Stack>
    </>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.canvas },
});
