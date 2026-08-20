import { useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import { AppButton } from '@/components/AppButton';
import { AppScreen } from '@/components/AppScreen';
import { useDriverAuth } from '@/features/auth/DriverAuthContext';
import { colors, spacing } from '@/theme';

export default function LoginScreen() {
  const parameters = useLocalSearchParams<{ setup?: string }>();
  const { error, isSubmitting, signIn } = useDriverAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  async function submit() {
    if (!username.trim() || !password) {
      return;
    }
    try {
      await signIn(username.trim(), password);
    } catch {
      // The provider exposes a controlled, non-sensitive error message.
    }
  }

  return (
    <AppScreen
      eyebrow="Logistics 2 · FTMS"
      title="Driver sign in"
      description="Sign in with the Django account linked to your FTMS Driver record.">
      {parameters.setup === 'success' ? (
        <Text accessibilityRole="alert" style={styles.success}>
          Password set successfully. Sign in to continue.
        </Text>
      ) : null}
      <View style={styles.form}>
        <Text style={styles.label}>Username</Text>
        <TextInput
          autoCapitalize="none"
          autoComplete="username"
          autoCorrect={false}
          editable={!isSubmitting}
          onChangeText={setUsername}
          placeholder="Enter username"
          placeholderTextColor={colors.muted}
          returnKeyType="next"
          style={styles.input}
          value={username}
        />
        <Text style={styles.label}>Password</Text>
        <TextInput
          autoCapitalize="none"
          autoComplete="current-password"
          editable={!isSubmitting}
          onChangeText={setPassword}
          onSubmitEditing={() => void submit()}
          placeholder="Enter password"
          placeholderTextColor={colors.muted}
          returnKeyType="done"
          secureTextEntry
          style={styles.input}
          value={password}
        />
        {error ? (
          <Text accessibilityRole="alert" style={styles.error}>
            {error}
          </Text>
        ) : null}
        <AppButton
          disabled={isSubmitting || !username.trim() || !password}
          label={isSubmitting ? 'Signing in…' : 'Sign In'}
          onPress={() => void submit()}
          style={isSubmitting || !username.trim() || !password ? styles.disabled : undefined}
        />
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  form: {
    gap: spacing.sm,
    padding: spacing.lg,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  label: { color: colors.ink, fontSize: 13, fontWeight: '700', marginTop: spacing.xs },
  input: {
    minHeight: 48,
    paddingHorizontal: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    backgroundColor: colors.canvas,
    color: colors.muted,
  },
  error: { color: colors.burgundy, fontSize: 13, lineHeight: 18, marginVertical: spacing.xs },
  success: { color: colors.positive, fontSize: 14, fontWeight: '700' },
  disabled: { opacity: 0.55 },
});
