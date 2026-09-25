import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { DriverAuthProvider, useDriverAuth } from '@/features/auth/DriverAuthContext';
import AuthLoadingScreen from '@/features/auth/screens/AuthLoadingScreen';
import { colors } from '@/theme';

export default function RootLayout() {
  return (
    <DriverAuthProvider>
      <RootNavigator />
    </DriverAuthProvider>
  );
}

function RootNavigator() {
  const { driver, isBootstrapping } = useDriverAuth();

  if (isBootstrapping) {
    return <AuthLoadingScreen />;
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
        <Stack.Protected guard={!driver}>
          <Stack.Screen name="index" options={{ headerShown: false }} />
          <Stack.Screen name="setup-password" options={{ title: 'Set Up Driver Account' }} />
        </Stack.Protected>
        <Stack.Protected guard={Boolean(driver)}>
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="trips/[tripId]" options={{ title: 'Trip Details' }} />
          <Stack.Screen name="trip-receipts" options={{ title: 'Trip Receipts' }} />
          <Stack.Screen name="trip-receipt-new" options={{ title: 'Add Receipt' }} />
          <Stack.Screen name="trip-receipt-detail" options={{ title: 'Receipt Detail' }} />
          <Stack.Screen name="inspection" options={{ title: 'Pre-Trip Inspection' }} />
          <Stack.Screen name="active-trip" options={{ title: 'Active Trip' }} />
          <Stack.Screen name="incident" options={{ title: 'Incident Report' }} />
          <Stack.Screen name="completion" options={{ title: 'Proof of Completion' }} />
        </Stack.Protected>
      </Stack>
    </>
  );
}
