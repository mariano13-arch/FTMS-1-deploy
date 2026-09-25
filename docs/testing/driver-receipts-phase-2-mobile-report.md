# Driver Receipts Phase 2 Mobile Report

## Mobile routes and screens

- Entry points: accepted trip detail screen and active trip screen.
- Receipt list: `mobile/app/trip-receipts.tsx`.
- Receipt create/review: `mobile/app/trip-receipt-new.tsx`.
- Receipt detail: `mobile/app/trip-receipt-detail.tsx`.

## Dependency

- Added `expo-image-picker` using `npx expo install expo-image-picker`.
- Installed version: `57.0.20`.
- Purpose: launch the system camera and media library with Expo SDK 57-compatible APIs.

## Camera and gallery flow

- `Take Photo` requests camera permission only when tapped.
- `Choose From Gallery` requests media library permission only when tapped.
- Permission denial leaves the form intact and shows a friendly message.
- Picker cancellation returns without showing an error.
- The selected local image URI is previewed before submission.
- `Replace Photo` reopens the camera flow and does not submit automatically.

## Form fields

- Common fields: `expense_type`, `transaction_at`, `amount`, `receipt_number`, `merchant_or_operator`, and `receipt_image`.
- Fuel-only fields: `liters`, `unit_price`, `fuel_type`, and `fuel_grade`.
- Toll-only field: `toll_plaza`.
- Switching to Toll clears fuel-only values.
- Switching to Fuel clears toll-only values.
- Fuel values use the backend-supported `GASOLINE`, `DIESEL`, `UNLEADED_91`, `PREMIUM_95`, `PREMIUM_97`, `REGULAR_DIESEL`, and `PREMIUM_DIESEL` values.

## Multipart submission

- Receipt upload is centralized in `mobile/services/driverReceipts.ts`.
- The shared API helper avoids setting `Content-Type` for `FormData`, allowing React Native to provide the multipart boundary.
- The client submits only receipt fields and the trip URL context.
- The client does not send driver ID, vehicle ID, assignment ID, or server-authoritative fields.

## Private image handling

- Receipt detail loads image bytes through the authenticated private `image_url` endpoint.
- The screen does not construct or display a public media URL.
- The authenticated response is converted to a local data URI for React Native `<Image>`.

## Error and loading states

- List/detail screens show loading, retry, and friendly error states.
- Create screen tracks idle, submitting, success, and error states.
- Duplicate submit taps are blocked with an in-flight guard and disabled submit button.
- Backend validation or network failure preserves the selected image and entered form state for retry.

## Manual confirmation

- Image capture or selection never submits the receipt.
- The driver must review the image and visible values, then press `Confirm & Submit Receipt`.
- This confirmation step is the Phase 3 OCR integration point: OCR candidates should populate this same editable form, with driver confirmation still required.

## Tests and validation

- Mobile typecheck: `npm run typecheck`.
- Expo check: `npm run validate`.
- Whitespace check: `git diff --check`.
- Focused automated mobile tests were not added because the mobile package currently has no configured `npm test` script or test runner.

## Limitations

- No OCR is implemented.
- No offline queue or restart persistence is implemented.
- No image compression is implemented; mobile blocks oversized images only when picker file size metadata is available, while backend validation remains authoritative.
