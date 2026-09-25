import { ApiError } from '@/services/api';
import type { TripExpenseReceipt, TripReceiptExpenseType } from '@/types';

export const MAX_RECEIPT_IMAGE_BYTES = 5 * 1024 * 1024;

export const FUEL_TYPES = ['GASOLINE', 'DIESEL'] as const;
export const FUEL_GRADES = [
  'UNLEADED_91',
  'PREMIUM_95',
  'PREMIUM_97',
  'REGULAR_DIESEL',
  'PREMIUM_DIESEL',
] as const;

export function receiptTypeLabel(type: TripReceiptExpenseType) {
  return type === 'FUEL' ? 'Fuel Receipt' : 'Toll Receipt';
}

export function formatReceiptDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value));
}

export function formatPeso(value: string) {
  return `PHP ${value}`;
}

export function receiptErrorMessage(error: unknown) {
  if (error instanceof ApiError && error.status === 0) {
    return error.message || 'Network unavailable. Check your connection and try again.';
  }
  if (error instanceof ApiError && error.status === 401) {
    return 'Your driver session has expired. Sign in again before managing receipts.';
  }
  if (error instanceof ApiError && error.status === 403) {
    return 'This trip is no longer eligible for receipt updates.';
  }
  if (error instanceof ApiError && error.status === 404) {
    return 'This receipt or trip is no longer available for your driver account.';
  }
  if (error instanceof ApiError) {
    return error.message;
  }
  return 'Unable to complete the receipt request. Please try again.';
}

export function receiptOcrErrorMessage(error: unknown) {
  if (error instanceof ApiError && error.status === 400) {
    return 'This image could not be analyzed. Use a valid JPEG or PNG under 5 MB.';
  }
  if (error instanceof ApiError && error.status === 404) {
    return 'This trip is no longer available or eligible for receipt analysis.';
  }
  return receiptErrorMessage(error);
}

export function receiptSummary(receipt: TripExpenseReceipt) {
  const merchant = receipt.merchantOrOperator || receipt.tollPlaza || 'Merchant unavailable';
  const number = receipt.receiptNumber ? ` · ${receipt.receiptNumber}` : '';
  return `${merchant}${number}`;
}
