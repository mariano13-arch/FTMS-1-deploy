import { api } from "./api";

export const employmentStatuses = [
  "ACTIVE",
  "ON_LEAVE",
  "SUSPENDED",
  "TERMINATED",
] as const;
export const eligibilityStatuses = [
  "ELIGIBLE",
  "RESTRICTED",
  "NOT_ELIGIBLE",
] as const;
export const driverDocumentTypes = [
  "DRIVER_LICENSE",
  "MEDICAL_CERTIFICATE",
  "TRAINING_CERTIFICATE",
  "OTHER",
] as const;
export type Driver = {
  id: number;
  driver_code: string;
  external_hr_id: string | null;
  first_name: string;
  middle_name: string;
  last_name: string;
  full_name: string;
  contact_number: string;
  email: string;
  photo_url: string | null;
  employment_status: (typeof employmentStatuses)[number];
  date_hired: string | null;
  linked_user: number | null;
  linked_user_display: string | null;
  license_number: string;
  license_category: string;
  license_codes: string;
  license_issue_date: string | null;
  license_expiry_date: string | null;
  medical_certificate_expiry_date: string | null;
  work_shift: "DAY" | "NIGHT";
  shift_label: "Day Shift" | "Night Shift";
  shift_hours: string;
  weekly_rest_days: string[];
  schedule_status: "ON_SHIFT" | "OFF_SHIFT" | "REST_DAY";
  eligibility_status: (typeof eligibilityStatuses)[number];
  eligibility_reasons: string[];
  safety_score: number | null;
  safety_score_status: "NOT_SCORED" | "DEMO_SCORED" | "REAL_SCORED";
  safety_score_source: "DEMO_SEED" | "REAL" | null;
  safety_completed_trips: number;
  safety_driving_hours: number;
  safety_event_count: number;
  safety_events_per_hour: number | null;
  safety_event_counts: Record<string, number>;
  safety_history: Array<{
    id: number;
    occurred_at: string;
    event_type: "HARSH_ACCELERATION" | "HARSH_BRAKING" | "SHARP_TURN";
    event_label: string;
    source: "DEMO_SEED";
  }>;
  created_at: string;
  updated_at: string;
};
export type DriverPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: Driver[];
};
export type DriverOnboarding = {
  account_provisioned: true;
  email_status: "SENT" | "NOT_SENT_MISSING_EMAIL" | "NOT_SENT_ERROR";
};
export type DriverCreateResult = Driver & { onboarding: DriverOnboarding };
export type DriverDocument = {
  id: number;
  driver: number;
  document_type: (typeof driverDocumentTypes)[number];
  title: string;
  reference_number: string;
  issuer_name: string;
  issued_date: string | null;
  effective_date: string | null;
  expiry_date: string | null;
  file_name: string;
  download_url: string;
  uploaded_by: number;
  uploaded_by_name: string;
  created_at: string;
  updated_at: string;
};
export type DriverDocumentPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: DriverDocument[];
};
export const getDrivers = (query = "", signal?: AbortSignal) =>
  api<DriverPage>(`/api/v1/drivers/${query ? `?${query}` : ""}`, { signal });
export const createDriver = (body: FormData, signal?: AbortSignal) =>
  api<DriverCreateResult>("/api/v1/drivers/", { method: "POST", body, signal });
export const editDriver = (id: number, body: FormData, signal?: AbortSignal) =>
  api<Driver>(`/api/v1/drivers/${id}/`, { method: "PATCH", body, signal });
export const getDriverDocuments = (id: number, signal?: AbortSignal) =>
  api<DriverDocumentPage>(`/api/v1/drivers/${id}/documents/`, { signal });
export const createDriverDocument = (
  id: number,
  body: FormData,
  signal?: AbortSignal,
) =>
  api<DriverDocument>(`/api/v1/drivers/${id}/documents/`, {
    method: "POST",
    body,
    signal,
  });
