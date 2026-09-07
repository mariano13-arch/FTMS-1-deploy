import type { ComponentProps } from 'react';
import { Pressable, StyleSheet, Text } from 'react-native';

import { colors, spacing } from '@/theme';

type Props = ComponentProps<typeof Pressable> & {
  label: string;
  variant?: 'primary' | 'secondary' | 'danger';
};

export function AppButton({ label, variant = 'primary', style, disabled, ...props }: Props) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      style={(state) => [
        styles.button,
        styles[variant],
        state.pressed && styles.pressed,
        disabled && styles.disabled,
        typeof style === 'function' ? style(state) : style,
      ]}
      {...props}>
      <Text style={[styles.label, variant !== 'primary' && styles.secondaryLabel]}>{label}</Text>
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
  danger: { backgroundColor: colors.surface, borderColor: colors.danger },
  label: { color: colors.surface, fontSize: 15, fontWeight: '700' },
  secondaryLabel: { color: colors.burgundy },
  pressed: { opacity: 0.78 },
  disabled: { opacity: 0.5 },
});
