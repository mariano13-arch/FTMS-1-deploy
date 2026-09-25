import { ApiError, api, setCsrfToken } from "./api";

export type Role = "FLEET_ADMIN" | "FLEET_MANAGER" | "DISPATCHER" | "FLEET_STAFF";
const ROLE_LABELS: Record<Role, string> = {
  FLEET_ADMIN: "Fleet Admin",
  FLEET_MANAGER: "Fleet Manager",
  DISPATCHER: "Dispatcher",
  FLEET_STAFF: "Fleet Staff",
};

export function roleLabel(role: Role | null | undefined): string {
  return role ? ROLE_LABELS[role] : "User";
}

export type StaffUser = {
  id: number; username: string; display_name: string; role: Role; capabilities?: string[];
};
export function hasCapability(user: StaffUser | null | undefined, module: string, action: string) {
  return Boolean(user?.capabilities?.includes(`${module}.${action}`));
}
export type LoginResult =
  | { kind: "authenticated"; user: StaffUser }
  | { kind: "two_factor_required"; challengeToken: string }
  | { kind: "mfa_enrollment_required"; challengeToken: string; setup: TwoFactorSetup };
export class LoginTemporarilyLockedError extends Error {
  code = "temporarily_locked" as const;

  constructor(
    message = "Too many failed sign-in attempts. Please wait before trying again.",
    public retryAfterSeconds: number | null = null,
  ) {
    super(message);
  }
}
export function isLoginTemporarilyLockedError(error: unknown) {
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    (error as { code?: unknown }).code === "temporarily_locked"
  );
}
export type TwoFactorStatus = {
  enabled: boolean; required: boolean; recovery_codes_remaining: number; enabled_at: string | null;
};

export async function bootstrapCsrf(signal?: AbortSignal) {
  const result = await api<{ csrf_token: string }>("/api/v1/auth/csrf/", { signal });
  setCsrfToken(result.csrf_token);
}
export async function login(username: string, password: string, signal?: AbortSignal) {
  await bootstrapCsrf(signal);
  let result:
    | { user: StaffUser; csrf_token: string }
    | { two_factor_required: true; challenge_token: string }
    | { mfa_enrollment_required: true; challenge_token: string; setup: TwoFactorSetup };
  try {
    result = await api<
      | { user: StaffUser; csrf_token: string }
      | { two_factor_required: true; challenge_token: string }
      | { mfa_enrollment_required: true; challenge_token: string; setup: TwoFactorSetup }
    >(
      "/api/v1/auth/login/", { method: "POST", body: JSON.stringify({ username, password }), signal },
    );
  } catch (error) {
    if (
      error instanceof ApiError &&
      typeof error.body === "object" &&
      error.body !== null &&
      "code" in error.body &&
      error.body.code === "temporarily_locked"
    ) {
      const retryAfterSeconds = "retry_after_seconds" in error.body &&
        typeof error.body.retry_after_seconds === "number"
        ? Math.max(0, Math.ceil(error.body.retry_after_seconds))
        : null;
      const detail = "detail" in error.body && typeof error.body.detail === "string"
        ? error.body.detail
        : undefined;
      throw new LoginTemporarilyLockedError(detail, retryAfterSeconds);
    }
    throw error;
  }
  if ("two_factor_required" in result)
    return { kind: "two_factor_required", challengeToken: result.challenge_token } as LoginResult;
  if ("mfa_enrollment_required" in result)
    return {
      kind: "mfa_enrollment_required",
      challengeToken: result.challenge_token,
      setup: result.setup,
    } as LoginResult;
  setCsrfToken(result.csrf_token);
  return { kind: "authenticated", user: result.user } as LoginResult;
}
export async function requestPasswordReset(email: string, signal?: AbortSignal) {
  await bootstrapCsrf(signal);
  return api<{ detail: string }>("/api/v1/auth/forgot-password/", {
    method: "POST", body: JSON.stringify({ email }), signal,
  });
}
export async function resetPassword(
  uid: string, token: string, newPassword: string, confirmPassword: string, signal?: AbortSignal,
) {
  await bootstrapCsrf(signal);
  await api<null>("/api/v1/auth/reset-password/", {
    method: "POST",
    body: JSON.stringify({ uid, token, new_password: newPassword, confirm_password: confirmPassword }),
    signal,
  });
}
export async function changePassword(
  currentPassword: string, newPassword: string, confirmPassword: string, signal?: AbortSignal,
) {
  await api<null>("/api/v1/auth/change-password/", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword, confirm_password: confirmPassword }),
    signal,
  });
  clearClientAuthentication();
  window.dispatchEvent(new Event("ftms:password-changed"));
}
export async function verifyTwoFactor(
  challengeToken: string, method: "totp" | "recovery", code: string, signal?: AbortSignal,
) {
  const result = await api<{ user: StaffUser; csrf_token: string }>("/api/v1/auth/2fa/verify/", {
    method: "POST", body: JSON.stringify({ challenge_token: challengeToken, method, code }), signal,
  });
  setCsrfToken(result.csrf_token);
  return result.user;
}
export async function confirmRequiredMfaEnrollment(
  challengeToken: string, code: string, signal?: AbortSignal,
) {
  const result = await api<{
    user: StaffUser; csrf_token: string; recovery_codes: string[];
  }>("/api/v1/auth/2fa/enrollment/confirm/", {
    method: "POST",
    body: JSON.stringify({ challenge_token: challengeToken, code }),
    signal,
  });
  setCsrfToken(result.csrf_token);
  return { user: result.user, recoveryCodes: result.recovery_codes };
}
export async function twoFactorStatus(signal?: AbortSignal) {
  return api<TwoFactorStatus>("/api/v1/auth/2fa/status/", { signal });
}
export type TwoFactorSetup = {
  provisioning_uri: string; manual_setup_key: string; issuer: string; account_label: string;
};
export async function startTwoFactorSetup(signal?: AbortSignal) {
  return api<TwoFactorSetup>("/api/v1/auth/2fa/setup/", { method: "POST", body: JSON.stringify({}), signal });
}
export async function confirmTwoFactor(code: string, signal?: AbortSignal) {
  return api<{ recovery_codes: string[] }>("/api/v1/auth/2fa/confirm/", {
    method: "POST", body: JSON.stringify({ code }), signal,
  });
}
export async function disableTwoFactor(
  currentPassword: string, method: "totp" | "recovery", code: string, signal?: AbortSignal,
) {
  return api<null>("/api/v1/auth/2fa/disable/", {
    method: "POST", body: JSON.stringify({ current_password: currentPassword, method, code }), signal,
  });
}
export async function me(signal?: AbortSignal) {
  return (await api<{ user: StaffUser }>("/api/v1/auth/me/", { signal })).user;
}
export async function logout(signal?: AbortSignal) {
  await api<null>("/api/v1/auth/logout/", { method: "POST", signal });
  setCsrfToken("");
}
export async function reportActivity(signal?: AbortSignal) {
  await api<null>("/api/v1/auth/activity/", {
    method: "POST", body: JSON.stringify({}), signal,
  });
}
export function clearClientAuthentication() {
  setCsrfToken("");
}
