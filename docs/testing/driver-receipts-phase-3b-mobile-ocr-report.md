# Driver Receipts Phase 3B Mobile OCR Report

## Integration point

The existing Add Receipt screen now calls the Phase 3A preview endpoint after the driver selects an
image and explicitly taps `Analyze Receipt`:

`POST /api/v1/driver-trips/{trip_id}/receipts/ocr-preview/`

The receipt service sends only `expense_type` and `receipt_image` as multipart form data through
the existing authenticated API helper. It does not set a multipart boundary, send driver or
vehicle identifiers, or send final form values.

## Candidate mapping

The service maps the backend response into strict mobile types. Common candidates populate
merchant/operator, amount, receipt number, and a full transaction timestamp. Fuel previews can
populate liters, unit price, fuel type, and fuel grade. Toll previews can populate toll plaza.
Fuel candidates are applied only to Fuel forms, and toll candidates only to Toll forms.

Only empty fields are populated. Existing non-empty values remain unchanged. The transaction field
is initialized by the Phase 2 form, so OCR may replace that initial value only until the driver
manually edits it. Once edited, the driver's transaction value is preserved. All OCR-populated
controls remain editable, and final submission reads the current form state.

When the backend returns `transaction_date` without `transaction_at`, mobile shows the detected
date and asks the driver to confirm the transaction time. It does not combine the date with
midnight, noon, the current time, or another fabricated time.

## UI states and fallback

After image selection the screen shows `Analyze Receipt`. During the request the action is disabled
and reads `Analyzing receipt...`. A failed request shows `Retry Analysis` while preserving the
image and form values. Backend warnings are displayed as non-blocking text.

An empty candidate response is treated as a handled result and tells the driver to enter receipt
details manually. Replacing the image clears warnings and analysis status without clearing form
values or automatically starting another analysis. Changing Fuel/Toll type invalidates prior OCR
results, clears the existing incompatible fields, and asks the driver to analyze again.

Stale responses are ignored when the image or expense type changes during analysis. Duplicate OCR
requests for the same image/type state are blocked.

## Confirmation and privacy

OCR preview never calls the receipt creation endpoint. The existing `Confirm & Submit Receipt`
action remains the only path to `POST /api/v1/driver-trips/{trip_id}/receipts/`, using the values
currently visible in the editable form.

Mobile does not request, display, log, persist, or place raw OCR text in navigation state. No OCR
key or external OCR integration is included. Candidate data exists only in the active form state.

## Manual Android verification

Use fictional or synthetic receipt images, not personal financial receipts.

### Fuel

1. Sign in as a driver and open an eligible trip.
2. Open Receipts, add a receipt, and select Fuel.
3. Take or choose a synthetic fuel receipt image and verify its preview.
4. Tap `Analyze Receipt`; verify the disabled `Analyzing receipt...` state.
5. Verify returned common and fuel candidates populate empty editable fields.
6. Edit one populated value, tap `Confirm & Submit Receipt`, and open receipt detail.
7. Verify the saved receipt contains the driver-edited value.

### Toll

1. Repeat the flow with Toll selected and a synthetic toll receipt.
2. Verify toll plaza can populate and no fuel fields or fuel candidates appear.
3. Review, edit, submit, and inspect the saved receipt detail.

### Failure and manual fallback

1. Analyze a synthetic blank or unreadable image.
2. Verify warnings or the manual-entry fallback appears without losing the image.
3. Complete the fields manually and verify `Confirm & Submit Receipt` remains usable.
4. Disable connectivity temporarily, retry analysis, and verify the friendly error and retry action.

### Image and type changes

1. Analyze an image, then replace it; verify prior OCR warnings/status clear and no automatic scan
   starts.
2. Analyze Fuel, switch to Toll, and verify fuel-only fields clear and re-analysis is requested.

## Limitations

OCR accuracy depends on image quality and receipt layout. Candidate-level confidence is not
available. Date-only results require manual time entry. Mobile automated tests were not added
because this package has no configured test runner; validation uses TypeScript and Expo checks plus
the manual device procedure above.
