import { api, setCsrfToken } from '@/services/api';
import type { DriverIdentity } from '@/types';

type DriverIdentityPayload = {
  user_id: number;
  username: string;
  driver_id: number;
  driver_code: string;
  display_name: string;
  email: string;
  employment_status: string;
  employment_status_label: string;
  license_number: string;
  license_expiry_date: string | null;
  medical_certificate_expiry_date: string | null;
  eligibility_status: 'ELIGIBLE' | 'RESTRICTED' | 'NOT_ELIGIBLE';
  eligibility_reasons: string[];
};

function mapDriverIdentity(payload: DriverIdentityPayload): DriverIdentity {
  return {
    userId: payload.user_id,
    username: payload.username,
    driverId: payload.driver_id,
    driverCode: payload.driver_code,
    displayName: payload.display_name,
    email: payload.email,
    employmentStatus: payload.employment_status,
    employmentStatusLabel: payload.employment_status_label,
    licenseNumber: payload.license_number,
    licenseExpiryDate: payload.license_expiry_date,
    medicalCertificateExpiryDate: payload.medical_certificate_expiry_date,
    eligibilityStatus: payload.eligibility_status,
    eligibilityReasons: payload.eligibility_reasons,
  };
}

export async function bootstrapDriverCsrf(signal?: AbortSignal) {
  const response = await api<{ csrf_token: string }>('/api/v1/driver-auth/csrf/', { signal });
  setCsrfToken(response.csrf_token);
}

export async function signInDriver(
  username: string,
  password: string,
  signal?: AbortSignal,
): Promise<DriverIdentity> {
  await bootstrapDriverCsrf(signal);
  const response = await api<{ driver: DriverIdentityPayload; csrf_token: string }>(
    '/api/v1/driver-auth/login/',
    {
      method: 'POST',
      body: JSON.stringify({ username, password }),
      signal,
    },
  );
  setCsrfToken(response.csrf_token);
  return mapDriverIdentity(response.driver);
}

export async function getCurrentDriver(signal?: AbortSignal): Promise<DriverIdentity> {
  const response = await api<{ driver: DriverIdentityPayload }>('/api/v1/driver-auth/me/', {
    signal,
  });
  return mapDriverIdentity(response.driver);
}

export async function signOutDriver(signal?: AbortSignal) {
  await api<null>('/api/v1/driver-auth/logout/', { method: 'POST', signal });
  setCsrfToken('');
}

export async function setupDriverPassword(
  uid: string,
  token: string,
  newPassword: string,
  confirmPassword: string,
  signal?: AbortSignal,
) {
  await bootstrapDriverCsrf(signal);
  await api<null>('/api/v1/driver-auth/setup-password/', {
    method: 'POST',
    body: JSON.stringify({
      uid,
      token,
      new_password: newPassword,
      confirm_password: confirmPassword,
    }),
    signal,
  });
}
