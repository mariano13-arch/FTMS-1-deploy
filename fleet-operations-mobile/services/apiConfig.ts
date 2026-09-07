export function getApiBaseUrl(): string {
  const value = process.env.EXPO_PUBLIC_API_BASE_URL?.trim();
  if (!value) {
    throw new Error('The Fleet Operations API base URL is not configured.');
  }
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
    throw new Error('The Fleet Operations API base URL is invalid.');
  }
  return url.toString().replace(/\/$/, '');
}
