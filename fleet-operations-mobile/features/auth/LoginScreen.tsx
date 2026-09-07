import { useState } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import { AppButton } from '@/components/AppButton';
import { AppScreen } from '@/components/AppScreen';
import { useStaffAuth } from '@/features/auth/StaffAuthContext';
import { colors, spacing } from '@/theme';

export default function LoginScreen() {
  const auth = useStaffAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [method, setMethod] = useState<'totp' | 'recovery'>('totp');

  async function submitPassword() {
    if (!username.trim() || !password) return;
    const submittedPassword = password;
    setPassword('');
    try {
      await auth.signIn(username.trim(), submittedPassword);
    } catch {
      // Controlled error is exposed by the authentication context.
    }
  }

  async function submitCode() {
    if (!code.trim()) return;
    try {
      await auth.verifySecondFactor(method, code.trim());
      setCode('');
    } catch {
      // Controlled error is exposed by the authentication context.
    }
  }

  return (
    <AppScreen
      title={auth.challengeToken ? 'Verify your sign in' : 'Staff sign in'}
      description="Use an existing Fleet Operations staff account.">
      <View style={styles.card}>
        {auth.challengeToken ? (
          <>
            <Text style={styles.label}>
              {method === 'totp' ? 'Authenticator code' : 'Recovery code'}
            </Text>
            <TextInput
              autoCapitalize="characters"
              autoCorrect={false}
              editable={!auth.isSubmitting}
              keyboardType={method === 'totp' ? 'number-pad' : 'default'}
              onChangeText={setCode}
              onSubmitEditing={() => void submitCode()}
              placeholder={method === 'totp' ? 'Enter 6-digit code' : 'Enter recovery code'}
              placeholderTextColor={colors.muted}
              secureTextEntry
              style={styles.input}
              value={code}
            />
            <AppButton
              disabled={auth.isSubmitting || !code.trim()}
              label={auth.isSubmitting ? 'Verifying…' : 'Verify'}
              onPress={() => void submitCode()}
            />
            <AppButton
              label={method === 'totp' ? 'Use Recovery Code' : 'Use Authenticator Code'}
              onPress={() => {
                setCode('');
                setMethod(method === 'totp' ? 'recovery' : 'totp');
              }}
              variant="secondary"
            />
            <AppButton label="Cancel" onPress={auth.cancelSecondFactor} variant="secondary" />
          </>
        ) : (
          <>
            <Text style={styles.label}>Username</Text>
            <TextInput
              autoCapitalize="none"
              autoComplete="username"
              autoCorrect={false}
              editable={!auth.isSubmitting}
              onChangeText={setUsername}
              placeholder="Enter username"
              placeholderTextColor={colors.muted}
              style={styles.input}
              value={username}
            />
            <Text style={styles.label}>Password</Text>
            <TextInput
              autoCapitalize="none"
              autoComplete="current-password"
              editable={!auth.isSubmitting}
              onChangeText={setPassword}
              onSubmitEditing={() => void submitPassword()}
              placeholder="Enter password"
              placeholderTextColor={colors.muted}
              secureTextEntry
              style={styles.input}
              value={password}
            />
            <AppButton
              disabled={auth.isSubmitting || !username.trim() || !password}
              label={auth.isSubmitting ? 'Signing in…' : 'Sign In'}
              onPress={() => void submitPassword()}
            />
          </>
        )}
        {auth.error ? (
          <Text accessibilityRole="alert" style={styles.error}>
            {auth.error}
          </Text>
        ) : null}
      </View>
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
  label: { color: colors.ink, fontSize: 13, fontWeight: '700' },
  input: {
    minHeight: 48,
    paddingHorizontal: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    color: colors.ink,
    backgroundColor: colors.canvas,
  },
  error: { color: colors.danger, fontSize: 13, lineHeight: 18 },
});
