export const apiBaseUrl =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

let csrfToken = "";
export const setCsrfToken = (token: string) => { csrfToken = token; };

export class ApiError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`API request failed (${status})`);
  }
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const method = init.method?.toUpperCase() ?? "GET";
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken) {
    headers.set("X-CSRFToken", csrfToken);
  }
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init, method, headers, credentials: "include",
  });
  const body = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event("ftms:session-expired"));
    throw new ApiError(response.status, body);
  }
  return body as T;
}
