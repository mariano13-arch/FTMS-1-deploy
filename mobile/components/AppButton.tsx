import type { ComponentProps } from 'react';
import { Pressable, StyleSheet, Text } from 'react-native';

import { colors, spacing } from '@/theme';

type AppButtonProps = ComponentProps<typeof Pressable> & {
  label: string;
  variant?: 'primary' | 'secondary';
};

export function AppButton({ label, variant = 'primary', style, ...props }: AppButtonProps) {
  return (
    <Pressable
      accessibilityRole="button"
      style={(state) => [
        styles.button,
        variant === 'secondary' ? styles.secondary : styles.primary,
        state.pressed && styles.pressed,
        typeof style === 'function' ? style(state) : style,
      ]}
      {...props}>
      <Text style={variant === 'secondary' ? styles.secondaryLabel : styles.primaryLabel}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
    borderRadius: 10,
    borderWidth: 1,
  },
  primary: { backgroundColor: colors.burgundy, borderColor: colors.burgundy },
  secondary: { backgroundColor: colors.surface, borderColor: colors.burgundy },
  pressed: { opacity: 0.78 },
  primaryLabel: { color: colors.surface, fontSize: 15, fontWeight: '700' },
  secondaryLabel: { color: colors.burgundy, fontSize: 15, fontWeight: '700' },
});
