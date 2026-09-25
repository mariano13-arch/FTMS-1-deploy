export type TripReceiptExpenseType = 'FUEL' | 'TOLL';
export type TripReceiptFuelType = 'GASOLINE' | 'DIESEL';
export type TripReceiptFuelGrade =
  | 'UNLEADED_91'
  | 'PREMIUM_95'
  | 'PREMIUM_97'
  | 'REGULAR_DIESEL'
  | 'PREMIUM_DIESEL';

export type TripExpenseReceipt = {
  id: number;
  expenseType: TripReceiptExpenseType;
  assignmentId: number;
  tripId: string;
  vehicleDisplay: string;
  transactionAt: string;
  amount: string;
  receiptNumber: string;
  merchantOrOperator: string;
  liters: string | null;
  unitPrice: string | null;
  fuelType: TripReceiptFuelType | '';
  fuelGrade: TripReceiptFuelGrade | '';
  tollPlaza: string;
  confirmedAt: string | null;
  createdAt: string;
  imageUrl: string;
  duplicateWarning: boolean;
};

export type ReceiptImageInput = {
  uri: string;
  name: string;
  type: 'image/jpeg' | 'image/png';
  size?: number;
};

export type CreateTripExpenseReceiptInput = {
  expenseType: TripReceiptExpenseType;
  transactionAt: string;
  amount: string;
  receiptNumber: string;
  merchantOrOperator: string;
  receiptImage: ReceiptImageInput;
  liters?: string;
  unitPrice?: string;
  fuelType?: TripReceiptFuelType | '';
  fuelGrade?: TripReceiptFuelGrade | '';
  tollPlaza?: string;
};

export type ReceiptOcrCandidates = {
  merchantOrOperator: string | null;
  transactionAt: string | null;
  transactionDate: string | null;
  amount: string | null;
  receiptNumber: string | null;
  liters?: string | null;
  unitPrice?: string | null;
  fuelType?: TripReceiptFuelType | null;
  fuelGrade?: TripReceiptFuelGrade | null;
  tollPlaza?: string | null;
};

export type ReceiptOcrPreviewResponse = {
  expenseType: TripReceiptExpenseType;
  candidates: ReceiptOcrCandidates;
  warnings: string[];
};
