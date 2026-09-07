const DEVICE_ID_PATTERN = /^[A-Z0-9][A-Z0-9._-]{0,63}$/;

export function parseTelemetryDeviceQr(value: string): string | null {
  const deviceId = value.trim();
  return DEVICE_ID_PATTERN.test(deviceId) ? deviceId : null;
}
