import { StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '@/theme';

type EmptyStateProps = {
  title: string;
  message: string;
};

export function EmptyState({ title, message }: EmptyStateProps) {
  return (
    <View style={styles.card}>
      <View style={styles.rule} />
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.message}>{message}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    minHeight: 180,
    justifyContent: 'center',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.xl,
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 12,
  },
  rule: { width: 40, height: 4, borderRadius: 2, backgroundColor: colors.burgundy },
  title: { color: colors.ink, fontSize: 18, fontWeight: '700', textAlign: 'center' },
  message: { color: colors.muted, fontSize: 14, lineHeight: 20, textAlign: 'center' },
});
