export type ApiConfiguration =
  | { status: 'missing'; baseUrl: null }
  | { status: 'invalid'; baseUrl: null }
  | { status: 'configured'; baseUrl: string };

function normalizeApiBaseUrl(value: string): string | null {
  try {
    const url = new URL(value.trim());

    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
      return null;
    }

    return url.toString().replace(/\/$/, '');
  } catch {
    return null;
  }
}

export function getApiConfiguration(): ApiConfiguration {
  const configuredValue = process.env.EXPO_PUBLIC_API_BASE_URL?.trim();

  if (!configuredValue) {
    return { status: 'missing', baseUrl: null };
  }

  const baseUrl = normalizeApiBaseUrl(configuredValue);
  return baseUrl
    ? { status: 'configured', baseUrl }
    : { status: 'invalid', baseUrl: null };
}
