import { StyleSheet, Text, View } from 'react-native';

import { AppButton } from '@/components/AppButton';
import { AppScreen } from '@/components/AppScreen';
import { useDriverAuth } from '@/features/auth/DriverAuthContext';
import { getApiConfiguration } from '@/services/apiConfig';
import { colors, spacing } from '@/theme';

function formatDate(value: string | null) {
  if (!value) {
    return 'Not recorded';
  }
  const [year, month, day] = value.split('-').map(Number);
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(new Date(year, month - 1, day, 12));
}

function isExpired(value: string | null) {
  if (!value) {
    return false;
  }
  const today = new Date();
  const localToday = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  return value < localToday;
}

type ProfileRowProps = {
  label: string;
  value: string;
  warning?: boolean;
};

function ProfileRow({ label, value, warning = false }: ProfileRowProps) {
  return (
    <View style={styles.row}>
      <Text style={styles.label}>{label}</Text>
      <Text style={[styles.value, warning && styles.warningValue]}>{value}</Text>
    </View>
  );
}

export default function ProfileScreen() {
  const { driver, error, isSubmitting, signOut } = useDriverAuth();
  const apiConfiguration = getApiConfiguration();

  return (
    <AppScreen title="Profile" description="Your FTMS driver identity and readiness record.">
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Driver account</Text>
        <ProfileRow label="Name" value={driver?.displayName ?? ''} />
        <ProfileRow label="Driver code" value={driver?.driverCode ?? ''} />
        <ProfileRow label="Username" value={driver?.username ?? ''} />
        <ProfileRow label="Email" value={driver?.email || 'Not recorded'} />
      </View>

      <View style={styles.card}>
        <View style={styles.statusHeader}>
          <Text style={styles.sectionTitle}>Driver readiness</Text>
          <View
            style={[
              styles.statusBadge,
              driver?.eligibilityStatus === 'ELIGIBLE'
                ? styles.eligibleBadge
                : styles.attentionBadge,
            ]}>
            <Text
              style={[
                styles.statusText,
                driver?.eligibilityStatus === 'ELIGIBLE'
                  ? styles.eligibleText
                  : styles.attentionText,
              ]}>
              {driver?.eligibilityStatus === 'NOT_ELIGIBLE'
                ? 'Not eligible'
                : driver?.eligibilityStatus === 'RESTRICTED'
                  ? 'Restricted'
                  : 'Eligible'}
            </Text>
          </View>
        </View>
        <ProfileRow label="Employment" value={driver?.employmentStatusLabel ?? ''} />
        <ProfileRow label="License number" value={driver?.licenseNumber || 'Not recorded'} />
        <ProfileRow
          label="License expiry"
          value={formatDate(driver?.licenseExpiryDate ?? null)}
          warning={isExpired(driver?.licenseExpiryDate ?? null)}
        />
        <ProfileRow
          label="Medical certificate expiry"
          value={formatDate(driver?.medicalCertificateExpiryDate ?? null)}
          warning={isExpired(driver?.medicalCertificateExpiryDate ?? null)}
        />
        {driver?.eligibilityReasons.length ? (
          <View style={styles.reasons}>
            {driver.eligibilityReasons.map((reason) => (
              <Text key={reason} style={styles.reason}>
                • {reason}
              </Text>
            ))}
          </View>
        ) : null}
      </View>

      <View style={styles.connectionCard}>
        <Text style={styles.label}>FTMS connection</Text>
        <Text style={styles.secondary}>
          {apiConfiguration.status === 'configured' ? 'Configured' : 'Not configured'}
        </Text>
        {apiConfiguration.status === 'invalid' ? (
          <Text style={styles.warning}>The configured API base URL is invalid.</Text>
        ) : null}
      </View>
      {error ? (
        <Text accessibilityRole="alert" style={styles.warning}>
          {error}
        </Text>
      ) : null}
      <AppButton
        disabled={isSubmitting}
        label={isSubmitting ? 'Signing out…' : 'Sign Out'}
        variant="secondary"
        onPress={() => void signOut().catch(() => undefined)}
        style={isSubmitting ? styles.disabled : undefined}
      />
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
  connectionCard: {
    gap: spacing.xs,
    padding: spacing.md,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  sectionTitle: { color: colors.ink, fontSize: 17, fontWeight: '800' },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: spacing.md,
    paddingTop: spacing.sm,
    borderTopColor: colors.border,
    borderTopWidth: 1,
  },
  label: { color: colors.muted, fontSize: 12, fontWeight: '700', textTransform: 'uppercase' },
  value: { flex: 1, color: colors.ink, fontSize: 14, fontWeight: '700', textAlign: 'right' },
  secondary: { color: colors.muted, fontSize: 13 },
  warning: { color: colors.warning, fontSize: 13, lineHeight: 18 },
  warningValue: { color: colors.burgundy },
  statusHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing.sm,
  },
  statusBadge: { paddingHorizontal: spacing.sm, paddingVertical: spacing.xs, borderRadius: 999 },
  eligibleBadge: { backgroundColor: '#e4f3ec' },
  attentionBadge: { backgroundColor: colors.burgundySoft },
  statusText: { fontSize: 11, fontWeight: '800' },
  eligibleText: { color: colors.positive },
  attentionText: { color: colors.burgundy },
  reasons: { gap: spacing.xs, padding: spacing.md, borderRadius: 8, backgroundColor: colors.canvas },
  reason: { color: colors.warning, fontSize: 13, lineHeight: 18 },
  disabled: { opacity: 0.55 },
});
