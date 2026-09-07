export const apiBaseUrl =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

let csrfToken = "";
export const setCsrfToken = (token: string) => {
  csrfToken = token;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(`API request failed (${status})`);
  }
}

const SESSION_EXPIRED_MESSAGE = "Your session expired. Please sign in again.";

function sessionExpirationMessage(body: unknown) {
  if (
    typeof body === "object" &&
    body !== null &&
    "detail" in body &&
    typeof body.detail === "string" &&
    (body.detail.includes("session expired") || body.detail.includes("signed in from another"))
  ) return body.detail;
  return SESSION_EXPIRED_MESSAGE;
}

async function refreshCsrfToken() {
  const response = await fetch(`${apiBaseUrl}/api/v1/auth/csrf/`, {
    credentials: "include",
  });
  const body = (await response.json().catch(() => null)) as {
    csrf_token?: unknown;
  } | null;
  if (!response.ok || typeof body?.csrf_token !== "string") {
    throw new ApiError(response.status, body);
  }
  setCsrfToken(body.csrf_token);
}

function isCsrfFailure(status: number, body: unknown) {
  return (
    status === 403 &&
    typeof body === "object" &&
    body !== null &&
    "detail" in body &&
    typeof body.detail === "string" &&
    body.detail.startsWith("CSRF Failed:")
  );
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
  retryCsrf = true,
): Promise<T> {
  const method = init.method?.toUpperCase() ?? "GET";
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken) {
    headers.set("X-CSRFToken", csrfToken);
  }
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    method,
    headers,
    credentials: "include",
  });
  const body =
    response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    if (
      retryCsrf &&
      !["GET", "HEAD", "OPTIONS"].includes(method) &&
      isCsrfFailure(response.status, body)
    ) {
      try {
        await refreshCsrfToken();
        return api<T>(path, init, false);
      } catch (refreshError) {
        if (refreshError instanceof ApiError) throw refreshError;
      }
    }
    if (
      response.status === 401 &&
      !path.endsWith("/auth/login/") &&
      !path.endsWith("/auth/me/") &&
      !path.endsWith("/auth/2fa/verify/")
    ) {
      window.dispatchEvent(new CustomEvent("ftms:session-expired", {
        detail: { message: sessionExpirationMessage(body) },
      }));
    }
    throw new ApiError(response.status, body);
  }
  return body as T;
}
