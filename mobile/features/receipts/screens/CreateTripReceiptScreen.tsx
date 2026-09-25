import { useMemo, useRef, useState } from 'react';
import { Image, Platform, StyleSheet, Text, TextInput, View } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { useLocalSearchParams, useRouter } from 'expo-router';
import type { Href } from 'expo-router';

import { AppButton } from '@/components/AppButton';
import { AppScreen } from '@/components/AppScreen';
import {
  FUEL_GRADES,
  FUEL_TYPES,
  MAX_RECEIPT_IMAGE_BYTES,
  formatPeso,
  receiptErrorMessage,
  receiptOcrErrorMessage,
  receiptTypeLabel,
} from '@/features/receipts/receiptUtils';
import { analyzeTripReceipt, createDriverTripReceipt } from '@/services/driverReceipts';
import { colors, spacing } from '@/theme';
import type {
  CreateTripExpenseReceiptInput,
  ReceiptImageInput,
  TripReceiptExpenseType,
  TripReceiptFuelGrade,
  TripReceiptFuelType,
} from '@/types';

type SubmissionState = 'idle' | 'submitting' | 'success' | 'error';
type AnalysisState = 'idle' | 'analyzing' | 'analyzed' | 'error';

const MIME_BY_EXTENSION: Record<string, ReceiptImageInput['type']> = {
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
};

function nowForInput() {
  return new Date().toISOString().slice(0, 16);
}

function isoFromInput(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString();
}

function imageFromAsset(asset: ImagePicker.ImagePickerAsset): ReceiptImageInput | string {
  const extension = (asset.fileName?.split('.').pop() ?? asset.uri.split('.').pop() ?? '').toLowerCase();
  const type = asset.mimeType === 'image/png' ? 'image/png' : MIME_BY_EXTENSION[extension] ?? 'image/jpeg';
  if (type !== 'image/jpeg' && type !== 'image/png') {
    return 'Only JPEG and PNG receipt images are allowed.';
  }
  if (asset.fileSize && asset.fileSize > MAX_RECEIPT_IMAGE_BYTES) {
    return 'Receipt image must not exceed 5 MB.';
  }
  return {
    uri: asset.uri,
    name: asset.fileName || `receipt-${Date.now()}.${type === 'image/png' ? 'png' : 'jpg'}`,
    type,
    size: asset.fileSize,
  };
}

function Field({
  label,
  value,
  onChangeText,
  keyboardType,
  placeholder,
}: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  keyboardType?: 'default' | 'decimal-pad';
  placeholder?: string;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        style={styles.input}
        value={value}
        onChangeText={onChangeText}
        keyboardType={keyboardType}
        placeholder={placeholder}
        placeholderTextColor={colors.muted}
      />
    </View>
  );
}

export default function CreateTripReceiptScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ tripId?: string | string[]; requestNumber?: string | string[] }>();
  const tripId = Array.isArray(params.tripId) ? params.tripId[0] : params.tripId;
  const requestNumber = Array.isArray(params.requestNumber) ? params.requestNumber[0] : params.requestNumber;
  const [expenseType, setExpenseType] = useState<TripReceiptExpenseType>('FUEL');
  const [image, setImage] = useState<ReceiptImageInput | null>(null);
  const [transactionAt, setTransactionAt] = useState(nowForInput());
  const [amount, setAmount] = useState('');
  const [receiptNumber, setReceiptNumber] = useState('');
  const [merchantOrOperator, setMerchantOrOperator] = useState('');
  const [liters, setLiters] = useState('');
  const [unitPrice, setUnitPrice] = useState('');
  const [fuelType, setFuelType] = useState<TripReceiptFuelType | ''>('');
  const [fuelGrade, setFuelGrade] = useState<TripReceiptFuelGrade | ''>('');
  const [tollPlaza, setTollPlaza] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [submissionState, setSubmissionState] = useState<SubmissionState>('idle');
  const [analysisState, setAnalysisState] = useState<AnalysisState>('idle');
  const [analysisNotice, setAnalysisNotice] = useState<string | null>(null);
  const [ocrWarnings, setOcrWarnings] = useState<string[]>([]);
  const submitting = useRef(false);
  const analysisVersion = useRef(0);
  const analyzingVersion = useRef<number | null>(null);
  const transactionAtEdited = useRef(false);

  const estimatedFuelTotal = useMemo(() => {
    const litersValue = Number(liters);
    const unitPriceValue = Number(unitPrice);
    if (!Number.isFinite(litersValue) || !Number.isFinite(unitPriceValue) || !liters || !unitPrice) {
      return null;
    }
    return (litersValue * unitPriceValue).toFixed(2);
  }, [liters, unitPrice]);

  const selectType = (type: TripReceiptExpenseType) => {
    if (type === expenseType) return;
    const shouldPromptForAnalysis = image && analysisState !== 'idle';
    analysisVersion.current += 1;
    setExpenseType(type);
    setMessage(null);
    setAnalysisState('idle');
    setOcrWarnings([]);
    setAnalysisNotice(
      shouldPromptForAnalysis ? 'Analyze the receipt again after changing receipt type.' : null,
    );
    if (type === 'FUEL') {
      setTollPlaza('');
    } else {
      setLiters('');
      setUnitPrice('');
      setFuelType('');
      setFuelGrade('');
    }
  };

  const applyPickerResult = (result: ImagePicker.ImagePickerResult) => {
    if (result.canceled) {
      return;
    }
    const selected = result.assets[0];
    if (!selected) {
      setMessage('No receipt image was selected.');
      return;
    }
    const nextImage = imageFromAsset(selected);
    if (typeof nextImage === 'string') {
      setMessage(nextImage);
      return;
    }
    setImage(nextImage);
    setMessage(null);
    analysisVersion.current += 1;
    setAnalysisState('idle');
    setAnalysisNotice(null);
    setOcrWarnings([]);
  };

  const takePhoto = async () => {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) {
      setMessage('Camera permission denied. Enable camera access to take a receipt photo.');
      return;
    }
    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ['images'],
      quality: 0.9,
    });
    applyPickerResult(result);
  };

  const chooseFromGallery = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setMessage('Gallery permission denied. Enable photo access to choose a receipt image.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 1,
    });
    applyPickerResult(result);
  };

  const analyzeReceipt = async () => {
    if (!tripId || !image) {
      setAnalysisState('error');
      setAnalysisNotice('Add a receipt photo before analyzing.');
      return;
    }
    const version = analysisVersion.current;
    if (analyzingVersion.current === version) return;
    analyzingVersion.current = version;
    const requestedType = expenseType;
    setAnalysisState('analyzing');
    setAnalysisNotice('Analyzing receipt...');
    setOcrWarnings([]);
    try {
      const preview = await analyzeTripReceipt(tripId, requestedType, image);
      if (analysisVersion.current !== version || preview.expenseType !== requestedType) return;
      const candidates = preview.candidates;
      setMerchantOrOperator((current) => current.trim() || candidates.merchantOrOperator || '');
      setAmount((current) => current.trim() || candidates.amount || '');
      setReceiptNumber((current) => current.trim() || candidates.receiptNumber || '');
      if (candidates.transactionAt && !transactionAtEdited.current) {
        setTransactionAt(candidates.transactionAt);
      }
      if (requestedType === 'FUEL') {
        setLiters((current) => current.trim() || candidates.liters || '');
        setUnitPrice((current) => current.trim() || candidates.unitPrice || '');
        setFuelType((current) => current || candidates.fuelType || '');
        setFuelGrade((current) => current || candidates.fuelGrade || '');
      } else {
        setTollPlaza((current) => current.trim() || candidates.tollPlaza || '');
      }

      const hasCandidates = Object.values(candidates).some(
        (value) => typeof value === 'string' && value.trim().length > 0,
      );
      setOcrWarnings(preview.warnings);
      setAnalysisState('analyzed');
      if (!hasCandidates) {
        setAnalysisNotice("We couldn't identify receipt details. You can enter them manually.");
      } else if (candidates.transactionDate && !candidates.transactionAt) {
        setAnalysisNotice(
          `Receipt date ${candidates.transactionDate} detected. Please confirm the transaction time.`,
        );
      } else {
        setAnalysisNotice(
          preview.warnings.length > 0
            ? 'Receipt analyzed with warnings. Review all values before submitting.'
            : 'Receipt analyzed. Review all values before submitting.',
        );
      }
    } catch (analysisError) {
      if (analysisVersion.current !== version) return;
      setAnalysisState('error');
      setAnalysisNotice(receiptOcrErrorMessage(analysisError));
      setOcrWarnings([]);
    } finally {
      if (analyzingVersion.current === version) analyzingVersion.current = null;
    }
  };

  const buildInput = (): CreateTripExpenseReceiptInput | null => {
    if (!image) {
      setMessage('Add a receipt photo before submitting.');
      return null;
    }
    if (!amount.trim() || !transactionAt.trim()) {
      setMessage('Amount and transaction date/time are required.');
      return null;
    }
    return {
      expenseType,
      transactionAt: isoFromInput(transactionAt),
      amount: amount.trim(),
      receiptNumber: receiptNumber.trim(),
      merchantOrOperator: merchantOrOperator.trim(),
      receiptImage: image,
      liters: liters.trim(),
      unitPrice: unitPrice.trim(),
      fuelType,
      fuelGrade,
      tollPlaza: tollPlaza.trim(),
    };
  };

  const submitReceipt = async () => {
    if (!tripId || submitting.current) return;
    const input = buildInput();
    if (!input) return;
    submitting.current = true;
    setSubmissionState('submitting');
    setMessage('Submitting receipt...');
    try {
      await createDriverTripReceipt(tripId, input);
      setSubmissionState('success');
      setMessage('Receipt submitted.');
      router.replace({
        pathname: '/trip-receipts',
        params: { tripId, requestNumber: requestNumber ?? '' },
      } as unknown as Href);
    } catch (submitError) {
      setSubmissionState('error');
      setMessage(receiptErrorMessage(submitError));
    } finally {
      submitting.current = false;
    }
  };

  return (
    <AppScreen title="Add Receipt" description={requestNumber}>
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Receipt Type</Text>
        <View style={styles.segmentRow}>
          {(['FUEL', 'TOLL'] as const).map((type) => (
            <AppButton
              key={type}
              label={receiptTypeLabel(type)}
              variant={expenseType === type ? 'primary' : 'secondary'}
              onPress={() => selectType(type)}
            />
          ))}
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Receipt Photo</Text>
        {image ? (
          <Image source={{ uri: image.uri }} style={styles.preview} accessibilityLabel="Receipt image preview" />
        ) : (
          <View style={styles.emptyPreview}>
            <Text style={styles.mutedText}>No image selected.</Text>
          </View>
        )}
        <View style={styles.buttonRow}>
          <AppButton label={image ? 'Replace Photo' : 'Take Photo'} onPress={() => void takePhoto()} />
          <AppButton label="Choose From Gallery" variant="secondary" onPress={() => void chooseFromGallery()} />
        </View>
        {image ? (
          <AppButton
            label={
              analysisState === 'analyzing'
                ? 'Analyzing receipt...'
                : analysisState === 'error'
                  ? 'Retry Analysis'
                  : 'Analyze Receipt'
            }
            disabled={analysisState === 'analyzing' || !tripId}
            onPress={() => void analyzeReceipt()}
          />
        ) : null}
        {analysisNotice ? (
          <Text style={analysisState === 'error' ? styles.errorText : styles.mutedText}>
            {analysisNotice}
          </Text>
        ) : null}
        {ocrWarnings.map((warning) => (
          <Text key={warning} style={styles.warningText}>
            {warning}
          </Text>
        ))}
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Transaction Details</Text>
        <Field
          label="Transaction Date/Time"
          value={transactionAt}
          onChangeText={(value) => {
            transactionAtEdited.current = true;
            setTransactionAt(value);
          }}
          placeholder="YYYY-MM-DDTHH:mm"
        />
        <Field label="Amount" value={amount} onChangeText={setAmount} keyboardType="decimal-pad" placeholder="0.00" />
        <Field label="Merchant / Operator" value={merchantOrOperator} onChangeText={setMerchantOrOperator} />
        <Field label="Receipt Number" value={receiptNumber} onChangeText={setReceiptNumber} />
      </View>

      {expenseType === 'FUEL' ? (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Fuel Details</Text>
          <Field label="Liters" value={liters} onChangeText={setLiters} keyboardType="decimal-pad" />
          <Field label="Unit Price" value={unitPrice} onChangeText={setUnitPrice} keyboardType="decimal-pad" />
          {estimatedFuelTotal ? (
            <Text style={styles.mutedText}>Liters x unit price: {formatPeso(estimatedFuelTotal)}</Text>
          ) : null}
          <Text style={styles.label}>Fuel Type</Text>
          <View style={styles.optionWrap}>
            {FUEL_TYPES.map((type) => (
              <AppButton key={type} label={type} variant={fuelType === type ? 'primary' : 'secondary'} onPress={() => setFuelType(type)} />
            ))}
          </View>
          <Text style={styles.label}>Fuel Grade</Text>
          <View style={styles.optionWrap}>
            {FUEL_GRADES.map((grade) => (
              <AppButton key={grade} label={grade} variant={fuelGrade === grade ? 'primary' : 'secondary'} onPress={() => setFuelGrade(grade)} />
            ))}
          </View>
        </View>
      ) : (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Toll Details</Text>
          <Field label="Toll Plaza" value={tollPlaza} onChangeText={setTollPlaza} />
        </View>
      )}

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Review & Submit</Text>
        {image ? <Image source={{ uri: image.uri }} style={styles.reviewImage} /> : null}
        <Text style={styles.reviewLine}>{receiptTypeLabel(expenseType)}</Text>
        <Text style={styles.reviewLine}>Amount: {amount ? formatPeso(amount) : 'Required'}</Text>
        <Text style={styles.reviewLine}>Transaction: {transactionAt || 'Required'}</Text>
        <Text style={styles.reviewLine}>Merchant / Operator: {merchantOrOperator || 'Not provided'}</Text>
        <Text style={styles.reviewLine}>Receipt Number: {receiptNumber || 'Not provided'}</Text>
        {expenseType === 'FUEL' ? (
          <>
            <Text style={styles.reviewLine}>Liters: {liters || 'Not provided'}</Text>
            <Text style={styles.reviewLine}>Unit Price: {unitPrice || 'Not provided'}</Text>
            <Text style={styles.reviewLine}>Fuel Type: {fuelType || 'Not provided'}</Text>
            <Text style={styles.reviewLine}>Fuel Grade: {fuelGrade || 'Not provided'}</Text>
          </>
        ) : (
          <Text style={styles.reviewLine}>Toll Plaza: {tollPlaza || 'Not provided'}</Text>
        )}
        {message ? (
          <Text style={submissionState === 'error' ? styles.errorText : styles.mutedText}>{message}</Text>
        ) : null}
        <AppButton
          label={submissionState === 'submitting' ? 'Submitting...' : 'Confirm & Submit Receipt'}
          disabled={submissionState === 'submitting' || !tripId}
          onPress={() => void submitReceipt()}
        />
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  section: {
    padding: spacing.lg,
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 12,
  },
  sectionTitle: { color: colors.ink, fontSize: 16, fontWeight: '800' },
  segmentRow: { gap: spacing.sm },
  buttonRow: { gap: spacing.sm },
  optionWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  preview: { width: '100%', height: 260, borderRadius: 8, backgroundColor: colors.canvas },
  reviewImage: { width: '100%', height: 160, borderRadius: 8, backgroundColor: colors.canvas },
  emptyPreview: {
    height: 160,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.canvas,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 8,
  },
  field: { gap: spacing.xs },
  label: { color: colors.ink, fontSize: 13, fontWeight: '700' },
  input: {
    minHeight: 46,
    paddingHorizontal: spacing.md,
    paddingVertical: Platform.OS === 'ios' ? spacing.md : spacing.sm,
    color: colors.ink,
    backgroundColor: colors.canvas,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 8,
    fontSize: 15,
  },
  mutedText: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  errorText: { color: colors.burgundy, fontSize: 13, lineHeight: 19 },
  warningText: { color: colors.ink, fontSize: 13, lineHeight: 19 },
  reviewLine: { color: colors.ink, fontSize: 14, lineHeight: 20 },
});
