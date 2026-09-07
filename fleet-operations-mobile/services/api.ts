import { getApiBaseUrl } from '@/services/apiConfig';

let csrfToken = '';

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'ApiError';
  }
}

export function setCsrfToken(value: string) {
  csrfToken = value;
}

function responseMessage(payload: unknown): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = payload.detail;
    if (typeof detail === 'string') {
      return detail;
    }
  }
  return 'The FTMS service could not complete the request.';
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase();
  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json');
  if (options.body !== undefined) {
    headers.set('Content-Type', 'application/json');
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) {
    headers.set('X-CSRFToken', csrfToken);
  }
  let response: Response;
  try {
    response = await fetch(new URL(path, `${getApiBaseUrl()}/`).toString(), {
      ...options,
      method,
      headers,
      credentials: 'include',
    });
  } catch (error) {
    if (error instanceof ApiError || (error instanceof Error && error.name === 'AbortError')) {
      throw error;
    }
    throw new ApiError('Unable to reach the FTMS service.', 0);
  }
  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }
  if (!response.ok) {
    throw new ApiError(responseMessage(payload), response.status);
  }
  return payload as T;
}
