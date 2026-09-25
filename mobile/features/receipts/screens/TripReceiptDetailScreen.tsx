import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Image, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';

import { AppButton } from '@/components/AppButton';
import { AppScreen } from '@/components/AppScreen';
import {
  formatPeso,
  formatReceiptDate,
  receiptErrorMessage,
  receiptTypeLabel,
} from '@/features/receipts/receiptUtils';
import { getDriverReceipt, getDriverReceiptImageDataUri } from '@/services/driverReceipts';
import { colors, spacing } from '@/theme';
import type { TripExpenseReceipt } from '@/types';

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.fact}>
      <Text style={styles.factLabel}>{label}</Text>
      <Text style={styles.factValue}>{value}</Text>
    </View>
  );
}

export default function TripReceiptDetailScreen() {
  const params = useLocalSearchParams<{ receiptId?: string | string[] }>();
  const receiptIdParam = Array.isArray(params.receiptId) ? params.receiptId[0] : params.receiptId;
  const receiptId = receiptIdParam ? Number(receiptIdParam) : NaN;
  const [receipt, setReceipt] = useState<TripExpenseReceipt | null>(null);
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(Boolean(receiptIdParam));
  const [error, setError] = useState<string | null>(null);

  const loadReceipt = useCallback(
    async (signal?: AbortSignal) => {
      if (!Number.isFinite(receiptId)) {
        setError('No receipt was selected.');
        setIsLoading(false);
        return;
      }
      setIsLoading(true);
      setError(null);
      try {
        const nextReceipt = await getDriverReceipt(receiptId, signal);
        setReceipt(nextReceipt);
        setImageUri(await getDriverReceiptImageDataUri(nextReceipt.imageUrl, signal));
      } catch (loadError) {
        if (loadError instanceof Error && loadError.name === 'AbortError') return;
        setReceipt(null);
        setImageUri(null);
        setError(receiptErrorMessage(loadError));
      } finally {
        if (!signal?.aborted) setIsLoading(false);
      }
    },
    [receiptId],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadReceipt(controller.signal);
    return () => controller.abort();
  }, [loadReceipt]);

  return (
    <AppScreen title="Receipt Detail" description={receipt ? receiptTypeLabel(receipt.expenseType) : undefined}>
      {isLoading ? (
        <View style={styles.stateCard}>
          <ActivityIndicator color={colors.burgundy} size="large" />
          <Text style={styles.stateText}>Loading receipt...</Text>
        </View>
      ) : error ? (
        <View style={styles.stateCard}>
          <Text style={styles.errorTitle}>Receipt unavailable</Text>
          <Text style={styles.stateText}>{error}</Text>
          <AppButton label="Retry" onPress={() => void loadReceipt()} />
        </View>
      ) : receipt ? (
        <>
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Private Image</Text>
            {imageUri ? (
              <Image source={{ uri: imageUri }} style={styles.image} accessibilityLabel="Receipt image" />
            ) : (
              <Text style={styles.bodyText}>Receipt image unavailable.</Text>
            )}
          </View>
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Receipt Values</Text>
            <View style={styles.factsGrid}>
              <Fact label="Type" value={receiptTypeLabel(receipt.expenseType)} />
              <Fact label="Amount" value={formatPeso(receipt.amount)} />
              <Fact label="Transaction" value={formatReceiptDate(receipt.transactionAt)} />
              <Fact label="Merchant / Operator" value={receipt.merchantOrOperator || 'Not provided'} />
              <Fact label="Receipt Number" value={receipt.receiptNumber || 'Not provided'} />
              <Fact label="Submitted" value={formatReceiptDate(receipt.createdAt)} />
              {receipt.expenseType === 'FUEL' ? (
                <>
                  <Fact label="Liters" value={receipt.liters ?? 'Not provided'} />
                  <Fact label="Unit Price" value={receipt.unitPrice ?? 'Not provided'} />
                  <Fact label="Fuel Type" value={receipt.fuelType || 'Not provided'} />
                  <Fact label="Fuel Grade" value={receipt.fuelGrade || 'Not provided'} />
                </>
              ) : (
                <Fact label="Toll Plaza" value={receipt.tollPlaza || 'Not provided'} />
              )}
            </View>
          </View>
        </>
      ) : null}
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  stateCard: {
    minHeight: 180,
    justifyContent: 'center',
    gap: spacing.md,
    padding: spacing.xl,
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 12,
  },
  stateText: { color: colors.muted, fontSize: 14, lineHeight: 20, textAlign: 'center' },
  errorTitle: { color: colors.ink, fontSize: 18, fontWeight: '700', textAlign: 'center' },
  section: {
    padding: spacing.lg,
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 12,
  },
  sectionTitle: { color: colors.ink, fontSize: 16, fontWeight: '800' },
  image: { width: '100%', height: 280, borderRadius: 8, backgroundColor: colors.canvas },
  bodyText: { color: colors.ink, fontSize: 14, lineHeight: 20 },
  factsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  fact: {
    flexGrow: 1,
    flexBasis: '46%',
    minWidth: 130,
    gap: 3,
    padding: spacing.md,
    backgroundColor: colors.canvas,
    borderRadius: 8,
  },
  factLabel: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  factValue: { color: colors.ink, fontSize: 14, fontWeight: '700', lineHeight: 19 },
});
