import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import type { Href } from 'expo-router';

import { AppButton } from '@/components/AppButton';
import { AppScreen } from '@/components/AppScreen';
import { EmptyState } from '@/components/EmptyState';
import {
  formatPeso,
  formatReceiptDate,
  receiptErrorMessage,
  receiptSummary,
  receiptTypeLabel,
} from '@/features/receipts/receiptUtils';
import { getDriverTripReceipts } from '@/services/driverReceipts';
import { colors, spacing } from '@/theme';
import type { TripExpenseReceipt } from '@/types';

export default function TripReceiptListScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ tripId?: string | string[]; requestNumber?: string | string[] }>();
  const tripId = Array.isArray(params.tripId) ? params.tripId[0] : params.tripId;
  const requestNumber = Array.isArray(params.requestNumber) ? params.requestNumber[0] : params.requestNumber;
  const [receipts, setReceipts] = useState<TripExpenseReceipt[]>([]);
  const [isLoading, setIsLoading] = useState(Boolean(tripId));
  const [error, setError] = useState<string | null>(null);

  const loadReceipts = useCallback(
    async (signal?: AbortSignal) => {
      if (!tripId) {
        setError('No trip was selected.');
        setIsLoading(false);
        return;
      }
      setIsLoading(true);
      setError(null);
      try {
        setReceipts(await getDriverTripReceipts(tripId, signal));
      } catch (loadError) {
        if (loadError instanceof Error && loadError.name === 'AbortError') return;
        setError(receiptErrorMessage(loadError));
      } finally {
        if (!signal?.aborted) setIsLoading(false);
      }
    },
    [tripId],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadReceipts(controller.signal);
    return () => controller.abort();
  }, [loadReceipts]);

  useFocusEffect(
    useCallback(() => {
      void loadReceipts();
    }, [loadReceipts]),
  );

  return (
    <AppScreen title="Trip Receipts" description={requestNumber}>
      {isLoading ? (
        <View style={styles.stateCard}>
          <ActivityIndicator color={colors.burgundy} size="large" />
          <Text style={styles.stateText}>Loading receipts...</Text>
        </View>
      ) : error ? (
        <View style={styles.stateCard}>
          <Text style={styles.errorTitle}>Receipts unavailable</Text>
          <Text style={styles.stateText}>{error}</Text>
          <AppButton label="Retry" onPress={() => void loadReceipts()} />
        </View>
      ) : (
        <>
          <AppButton
            label="Add Receipt"
            onPress={() =>
              tripId
                ? router.push({
                    pathname: '/trip-receipt-new',
                    params: { tripId, requestNumber: requestNumber ?? '' },
                  } as unknown as Href)
                : undefined
            }
          />
          {receipts.length === 0 ? (
            <EmptyState
              title="No receipts submitted"
              message="Fuel and toll receipts for this trip will appear here after upload."
            />
          ) : (
            <View style={styles.list}>
              {receipts.map((receipt) => (
                <Pressable
                  key={receipt.id}
                  accessibilityRole="button"
                  accessibilityLabel={`Open ${receiptTypeLabel(receipt.expenseType)}`}
                  style={({ pressed }) => [styles.receiptCard, pressed && styles.pressed]}
                  onPress={() =>
                    router.push({
                      pathname: '/trip-receipt-detail',
                      params: { receiptId: String(receipt.id), tripId: tripId ?? '' },
                    } as unknown as Href)
                  }>
                  <View style={styles.receiptHeader}>
                    <Text style={styles.receiptType}>{receiptTypeLabel(receipt.expenseType)}</Text>
                    <Text style={styles.amount}>{formatPeso(receipt.amount)}</Text>
                  </View>
                  <Text style={styles.meta}>{formatReceiptDate(receipt.transactionAt)}</Text>
                  <Text style={styles.summary}>{receiptSummary(receipt)}</Text>
                </Pressable>
              ))}
            </View>
          )}
        </>
      )}
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
  list: { gap: spacing.md },
  receiptCard: {
    gap: spacing.xs,
    padding: spacing.lg,
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 12,
  },
  pressed: { opacity: 0.78 },
  receiptHeader: { flexDirection: 'row', gap: spacing.md, justifyContent: 'space-between' },
  receiptType: { color: colors.ink, fontSize: 16, fontWeight: '800' },
  amount: { color: colors.burgundy, fontSize: 16, fontWeight: '800' },
  meta: { color: colors.muted, fontSize: 13 },
  summary: { color: colors.ink, fontSize: 14, lineHeight: 20 },
});
