import type { Href } from 'expo-router';
import { router } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { AppButton } from '@/components/AppButton';
import { colors, spacing } from '@/theme';

type WorkflowDestination = { label: string; href: Href };

export function PlannedWorkflow({ destinations }: { destinations: WorkflowDestination[] }) {
  return (
    <View style={styles.card}>
      <Text style={styles.label}>Development screen preview</Text>
      <Text style={styles.note}>
        Navigation only. No assignment, trip, or backend action is created.
      </Text>
      <View style={styles.actions}>
        {destinations.map((destination) => (
          <AppButton
            key={destination.label}
            label={destination.label}
            variant="secondary"
            onPress={() => router.push(destination.href)}
          />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  label: { color: colors.warning, fontSize: 12, fontWeight: '800', textTransform: 'uppercase' },
  note: { color: colors.muted, fontSize: 13, lineHeight: 18 },
  actions: { gap: spacing.sm, marginTop: spacing.xs },
});
