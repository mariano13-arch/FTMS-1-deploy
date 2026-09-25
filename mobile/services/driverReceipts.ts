import { api, apiResponse } from '@/services/api';
import type {
  CreateTripExpenseReceiptInput,
  ReceiptImageInput,
  ReceiptOcrPreviewResponse,
  TripExpenseReceipt,
  TripReceiptExpenseType,
  TripReceiptFuelGrade,
  TripReceiptFuelType,
} from '@/types';

type TripExpenseReceiptPayload = {
  id: number;
  expense_type: TripReceiptExpenseType;
  assignment_id: number;
  trip_id: string;
  vehicle_display: string;
  transaction_at: string;
  amount: string;
  receipt_number: string;
  merchant_or_operator: string;
  liters: string | null;
  unit_price: string | null;
  fuel_type: TripReceiptFuelType | '';
  fuel_grade: TripReceiptFuelGrade | '';
  toll_plaza: string;
  confirmed_at: string | null;
  created_at: string;
  image_url: string;
  duplicate_warning: boolean;
};

type ReceiptListPayload = {
  receipts: TripExpenseReceiptPayload[];
};

type ReceiptOcrPreviewPayload = {
  expense_type: TripReceiptExpenseType;
  candidates: {
    merchant_or_operator: string | null;
    transaction_at: string | null;
    transaction_date: string | null;
    amount: string | null;
    receipt_number: string | null;
    liters?: string | null;
    unit_price?: string | null;
    fuel_type?: TripReceiptFuelType | null;
    fuel_grade?: TripReceiptFuelGrade | null;
    toll_plaza?: string | null;
  };
  warnings: string[];
};

function mapReceipt(payload: TripExpenseReceiptPayload): TripExpenseReceipt {
  return {
    id: payload.id,
    expenseType: payload.expense_type,
    assignmentId: payload.assignment_id,
    tripId: payload.trip_id,
    vehicleDisplay: payload.vehicle_display,
    transactionAt: payload.transaction_at,
    amount: payload.amount,
    receiptNumber: payload.receipt_number,
    merchantOrOperator: payload.merchant_or_operator,
    liters: payload.liters,
    unitPrice: payload.unit_price,
    fuelType: payload.fuel_type,
    fuelGrade: payload.fuel_grade,
    tollPlaza: payload.toll_plaza,
    confirmedAt: payload.confirmed_at,
    createdAt: payload.created_at,
    imageUrl: payload.image_url,
    duplicateWarning: payload.duplicate_warning,
  };
}

function appendIfPresent(formData: FormData, key: string, value: string | undefined) {
  if (value !== undefined && value !== '') {
    formData.append(key, value);
  }
}

function appendReceiptImage(formData: FormData, image: ReceiptImageInput) {
  formData.append('receipt_image', {
    uri: image.uri,
    name: image.name,
    type: image.type,
  } as unknown as Blob);
}

export async function getDriverTripReceipts(
  tripId: string,
  signal?: AbortSignal,
): Promise<TripExpenseReceipt[]> {
  const response = await api<ReceiptListPayload>(
    `/api/v1/driver-trips/${encodeURIComponent(tripId)}/receipts/`,
    { signal },
  );
  return response.receipts.map(mapReceipt);
}

export async function getDriverReceipt(
  receiptId: number,
  signal?: AbortSignal,
): Promise<TripExpenseReceipt> {
  const response = await api<TripExpenseReceiptPayload>(
    `/api/v1/driver-receipts/${encodeURIComponent(String(receiptId))}/`,
    { signal },
  );
  return mapReceipt(response);
}

export async function createDriverTripReceipt(
  tripId: string,
  input: CreateTripExpenseReceiptInput,
): Promise<TripExpenseReceipt> {
  const formData = new FormData();
  formData.append('expense_type', input.expenseType);
  formData.append('transaction_at', input.transactionAt);
  formData.append('amount', input.amount);
  appendIfPresent(formData, 'receipt_number', input.receiptNumber);
  appendIfPresent(formData, 'merchant_or_operator', input.merchantOrOperator);
  appendReceiptImage(formData, input.receiptImage);

  if (input.expenseType === 'FUEL') {
    appendIfPresent(formData, 'liters', input.liters);
    appendIfPresent(formData, 'unit_price', input.unitPrice);
    appendIfPresent(formData, 'fuel_type', input.fuelType);
    appendIfPresent(formData, 'fuel_grade', input.fuelGrade);
  } else {
    appendIfPresent(formData, 'toll_plaza', input.tollPlaza);
  }

  const response = await api<TripExpenseReceiptPayload>(
    `/api/v1/driver-trips/${encodeURIComponent(tripId)}/receipts/`,
    { method: 'POST', body: formData },
  );
  return mapReceipt(response);
}

export async function analyzeTripReceipt(
  tripId: string,
  expenseType: TripReceiptExpenseType,
  receiptImage: ReceiptImageInput,
): Promise<ReceiptOcrPreviewResponse> {
  const formData = new FormData();
  formData.append('expense_type', expenseType);
  appendReceiptImage(formData, receiptImage);

  const response = await api<ReceiptOcrPreviewPayload>(
    `/api/v1/driver-trips/${encodeURIComponent(tripId)}/receipts/ocr-preview/`,
    { method: 'POST', body: formData },
  );
  return {
    expenseType: response.expense_type,
    candidates: {
      merchantOrOperator: response.candidates.merchant_or_operator,
      transactionAt: response.candidates.transaction_at,
      transactionDate: response.candidates.transaction_date,
      amount: response.candidates.amount,
      receiptNumber: response.candidates.receipt_number,
      liters: response.candidates.liters,
      unitPrice: response.candidates.unit_price,
      fuelType: response.candidates.fuel_type,
      fuelGrade: response.candidates.fuel_grade,
      tollPlaza: response.candidates.toll_plaza,
    },
    warnings: response.warnings,
  };
}

export async function getDriverReceiptImageDataUri(
  imageUrl: string,
  signal?: AbortSignal,
): Promise<string> {
  const response = await apiResponse(imageUrl, { signal });
  const blob = await response.blob();
  return await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Unable to read the receipt image.'));
    reader.onloadend = () => {
      if (typeof reader.result === 'string') {
        resolve(reader.result);
      } else {
        reject(new Error('Unable to read the receipt image.'));
      }
    };
    reader.readAsDataURL(blob);
  });
}
