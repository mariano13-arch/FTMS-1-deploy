import { api, ApiError, setCsrfToken } from '@/services/api';
import type { StaffIdentity, StaffRole } from '@/types';

type UserPayload = {
  id: number;
  username: string;
  display_name: string;
  role: string;
};

type LoginResponse =
  | { user: UserPayload; csrf_token: string }
  | { two_factor_required: true; challenge_token: string };

const allowedRoles = new Set<StaffRole>(['FLEET_ADMIN', 'FLEET_MANAGER', 'FLEET_STAFF']);

function mapStaff(payload: UserPayload): StaffIdentity {
  if (!allowedRoles.has(payload.role as StaffRole)) {
    throw new ApiError('This app requires an authorized Fleet Operations staff account.', 403);
  }
  return {
    id: payload.id,
    username: payload.username,
    displayName: payload.display_name,
    role: payload.role as StaffRole,
  };
}

async function requireFleetRole(payload: UserPayload): Promise<StaffIdentity> {
  try {
    return mapStaff(payload);
  } catch (error) {
    try {
      await signOutStaff();
    } catch {
      setCsrfToken('');
    }
    throw error;
  }
}

export async function bootstrapCsrf(signal?: AbortSignal) {
  const response = await api<{ csrf_token: string }>('/api/v1/auth/csrf/', { signal });
  setCsrfToken(response.csrf_token);
}

export async function signInStaff(
  username: string,
  password: string,
): Promise<{ staff?: StaffIdentity; challengeToken?: string }> {
  await bootstrapCsrf();
  const response = await api<LoginResponse>('/api/v1/auth/login/', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  if ('two_factor_required' in response) {
    return { challengeToken: response.challenge_token };
  }
  setCsrfToken(response.csrf_token);
  const staff = await requireFleetRole(response.user);
  return { staff };
}

export async function verifyStaffSecondFactor(
  challengeToken: string,
  method: 'totp' | 'recovery',
  code: string,
): Promise<StaffIdentity> {
  const response = await api<{ user: UserPayload; csrf_token: string }>(
    '/api/v1/auth/2fa/verify/',
    {
      method: 'POST',
      body: JSON.stringify({ challenge_token: challengeToken, method, code }),
    },
  );
  setCsrfToken(response.csrf_token);
  return requireFleetRole(response.user);
}

export async function getCurrentStaff(signal?: AbortSignal): Promise<StaffIdentity> {
  const response = await api<{ user: UserPayload }>('/api/v1/auth/me/', { signal });
  return requireFleetRole(response.user);
}

export async function signOutStaff() {
  await api<null>('/api/v1/auth/logout/', { method: 'POST' });
  setCsrfToken('');
}
