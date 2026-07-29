export type HealthResponse = {
  status: "ok";
  service: "ftms-backend";
  database: "ok";
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${apiBaseUrl}/api/health/`, { signal });
  if (!response.ok) {
    throw new Error("Backend health check failed");
  }
  return response.json() as Promise<HealthResponse>;
}
