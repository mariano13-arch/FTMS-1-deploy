import { api, setCsrfToken } from "./api";

export type Role = "SUPER_ADMIN" | "FLEET_MANAGER" | "DISPATCHER";
export type StaffUser = {
  id: number; username: string; display_name: string; role: Role;
};
export type LoginResult =
  | { kind: "authenticated"; user: StaffUser }
  | { kind: "two_factor_required"; challengeToken: string };
export type TwoFactorStatus = {
  enabled: boolean; recovery_codes_remaining: number; enabled_at: string | null;
};

export async function bootstrapCsrf(signal?: AbortSignal) {
  const result = await api<{ csrf_token: string }>("/api/v1/auth/csrf/", { signal });
  setCsrfToken(result.csrf_token);
}
export async function login(username: string, password: string, signal?: AbortSignal) {
  await bootstrapCsrf(signal);
  const result = await api<
    | { user: StaffUser; csrf_token: string }
    | { two_factor_required: true; challenge_token: string }
  >(
    "/api/v1/auth/login/", { method: "POST", body: JSON.stringify({ username, password }), signal },
  );
  if ("two_factor_required" in result)
    return { kind: "two_factor_required", challengeToken: result.challenge_token } as LoginResult;
  setCsrfToken(result.csrf_token);
  return { kind: "authenticated", user: result.user } as LoginResult;
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
