import type { PropsWithChildren } from 'react';
import { SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '@/theme';

type AppScreenProps = PropsWithChildren<{
  title: string;
  eyebrow?: string;
  description?: string;
  scroll?: boolean;
}>;

export function AppScreen({
  title,
  eyebrow = 'FTMS Driver',
  description,
  scroll = true,
  children,
}: AppScreenProps) {
  const content = (
    <View style={styles.content}>
      <View style={styles.heading}>
        <Text style={styles.eyebrow}>{eyebrow}</Text>
        <Text style={styles.title}>{title}</Text>
        {description ? <Text style={styles.description}>{description}</Text> : null}
      </View>
      {children}
    </View>
  );

  return (
    <SafeAreaView style={styles.safeArea}>
      {scroll ? (
        <ScrollView contentContainerStyle={styles.scrollContent}>{content}</ScrollView>
      ) : (
        content
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.canvas },
  scrollContent: { flexGrow: 1 },
  content: {
    flex: 1,
    width: '100%',
    maxWidth: 720,
    alignSelf: 'center',
    padding: spacing.lg,
    gap: spacing.lg,
  },
  heading: { gap: spacing.xs },
  eyebrow: {
    color: colors.burgundy,
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  title: { color: colors.ink, fontSize: 28, fontWeight: '800' },
  description: { color: colors.muted, fontSize: 15, lineHeight: 21 },
});
