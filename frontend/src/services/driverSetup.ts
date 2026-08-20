import { api, setCsrfToken } from "./api";

export type DriverPasswordSetup = {
  uid: string;
  token: string;
  new_password: string;
  confirm_password: string;
};

export async function bootstrapDriverCsrf(signal?: AbortSignal) {
  const result = await api<{ csrf_token: string }>("/api/v1/driver-auth/csrf/", { signal });
  setCsrfToken(result.csrf_token);
}

export async function setupDriverPassword(
  payload: DriverPasswordSetup,
  signal?: AbortSignal,
) {
  await bootstrapDriverCsrf(signal);
  await api<null>("/api/v1/driver-auth/setup-password/", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}
