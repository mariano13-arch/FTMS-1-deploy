import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import { AppButton } from '@/components/AppButton';
import { AppScreen } from '@/components/AppScreen';
import { ApiError } from '@/services/api';
import { setupDriverPassword } from '@/services/driverAuth';
import { colors, spacing } from '@/theme';

function singleParameter(value: string | string[] | undefined) {
  return typeof value === 'string' ? value : null;
}

export default function SetupPasswordScreen() {
  const parameters = useLocalSearchParams<{ uid?: string | string[]; token?: string | string[] }>();
  const uid = singleParameter(parameters.uid);
  const token = singleParameter(parameters.token);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasSetupLink = Boolean(uid && token);

  async function submit() {
    if (!uid || !token || !newPassword || !confirmPassword) {
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      await setupDriverPassword(uid, token, newPassword, confirmPassword);
      setNewPassword('');
      setConfirmPassword('');
      router.replace({ pathname: '/', params: { setup: 'success' } });
    } catch (setupError) {
      setError(
        setupError instanceof ApiError
          ? setupError.message
          : 'Unable to set the Driver account password.',
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AppScreen
      title="Set your password"
      description="Choose a private password for your FTMS Driver Mobile account.">
      <View style={styles.form}>
        {!hasSetupLink ? (
          <Text accessibilityRole="alert" style={styles.error}>
            This account setup link is incomplete or invalid.
          </Text>
        ) : null}
        <Text style={styles.label}>New Password</Text>
        <TextInput
          autoCapitalize="none"
          autoComplete="new-password"
          editable={!isSubmitting && hasSetupLink}
          onChangeText={setNewPassword}
          placeholder="Enter new password"
          placeholderTextColor={colors.muted}
          secureTextEntry
          style={styles.input}
          value={newPassword}
        />
        <Text style={styles.label}>Confirm Password</Text>
        <TextInput
          autoCapitalize="none"
          autoComplete="new-password"
          editable={!isSubmitting && hasSetupLink}
          onChangeText={setConfirmPassword}
          onSubmitEditing={() => void submit()}
          placeholder="Confirm new password"
          placeholderTextColor={colors.muted}
          returnKeyType="done"
          secureTextEntry
          style={styles.input}
          value={confirmPassword}
        />
        {error ? (
          <Text accessibilityRole="alert" style={styles.error}>
            {error}
          </Text>
        ) : null}
        <AppButton
          disabled={isSubmitting || !hasSetupLink || !newPassword || !confirmPassword}
          label={isSubmitting ? 'Setting password…' : 'Set Password'}
          onPress={() => void submit()}
          style={
            isSubmitting || !hasSetupLink || !newPassword || !confirmPassword
              ? styles.disabled
              : undefined
          }
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
    color: colors.ink,
  },
  error: { color: colors.burgundy, fontSize: 13, lineHeight: 18, marginVertical: spacing.xs },
  disabled: { opacity: 0.55 },
});
