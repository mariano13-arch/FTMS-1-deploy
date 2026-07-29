import { api, setCsrfToken } from "./api";

export type Role = "SUPER_ADMIN" | "FLEET_MANAGER" | "DISPATCHER";
export type StaffUser = {
  id: number; username: string; display_name: string; role: Role;
};

export async function bootstrapCsrf(signal?: AbortSignal) {
  const result = await api<{ csrf_token: string }>("/api/v1/auth/csrf/", { signal });
  setCsrfToken(result.csrf_token);
}
export async function login(username: string, password: string, signal?: AbortSignal) {
  await bootstrapCsrf(signal);
  const result = await api<{ user: StaffUser; csrf_token: string }>(
    "/api/v1/auth/login/", { method: "POST", body: JSON.stringify({ username, password }), signal },
  );
  setCsrfToken(result.csrf_token);
  return result.user;
}
export async function me(signal?: AbortSignal) {
  return (await api<{ user: StaffUser }>("/api/v1/auth/me/", { signal })).user;
}
export async function logout(signal?: AbortSignal) {
  await api<null>("/api/v1/auth/logout/", { method: "POST", signal });
  setCsrfToken("");
}
