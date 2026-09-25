import { getApiConfiguration } from '@/services/apiConfig';

let csrfToken = '';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export function setCsrfToken(value: string) {
  csrfToken = value;
}

export function getApiUrl(path: string): string {
  const configuration = getApiConfiguration();
  if (configuration.status === 'missing') {
    throw new ApiError('The mobile API base URL is not configured.', 0);
  }
  if (configuration.status === 'invalid') {
    throw new ApiError('The mobile API base URL is invalid.', 0);
  }
  return new URL(path, `${configuration.baseUrl}/`).toString();
}

function buildHeaders(options: RequestInit, method: string) {
  const headers = new Headers(options.headers);
  const body = options.body;
  headers.set('Accept', headers.get('Accept') ?? 'application/json');
  if (body !== undefined && !(body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) {
    headers.set('X-CSRFToken', csrfToken);
  }
  return headers;
}

function responseMessage(payload: unknown): string {
  if (
    payload &&
    typeof payload === 'object' &&
    'detail' in payload &&
    typeof payload.detail === 'string'
  ) {
    return payload.detail;
  }
  return 'The FTMS service could not complete the request.';
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase();
  const headers = buildHeaders(options, method);

  let response: Response;
  try {
    response = await fetch(getApiUrl(path), {
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

export async function apiResponse(path: string, options: RequestInit = {}): Promise<Response> {
  const method = (options.method ?? 'GET').toUpperCase();
  const headers = buildHeaders(options, method);

  try {
    const response = await fetch(getApiUrl(path), {
      ...options,
      method,
      headers,
      credentials: 'include',
    });
    if (!response.ok) {
      let payload: unknown = null;
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }
      throw new ApiError(responseMessage(payload), response.status);
    }
    return response;
  } catch (error) {
    if (error instanceof ApiError || (error instanceof Error && error.name === 'AbortError')) {
      throw error;
    }
    throw new ApiError('Unable to reach the FTMS service.', 0);
  }
}
