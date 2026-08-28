import { ApiError } from "../../services/api";

export const safeError = (reason: unknown) => {
  if (!(reason instanceof ApiError) || !reason.body || typeof reason.body !== "object") return "The action could not be completed. Reload the request and try again.";
  const first = Object.values(reason.body as Record<string, unknown>)[0];
  return Array.isArray(first) ? String(first[0]) : typeof first === "string" ? first : "The action could not be completed.";
};
