import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '@/theme';

export default function AuthLoadingScreen() {
  return (
    <View style={styles.container}>
      <ActivityIndicator color={colors.burgundy} size="large" />
      <Text style={styles.text}>Checking driver session…</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.md,
    backgroundColor: colors.canvas,
  },
  text: { color: colors.muted, fontSize: 14 },
});
