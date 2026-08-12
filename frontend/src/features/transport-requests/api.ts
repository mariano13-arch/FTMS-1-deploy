import { api } from "../../services/api";
import type { CalendarResponse, PlaceDetails, PlaceSuggestions, RequestPage, Summary, TransportRequest, TransportRoute } from "./types";

const root = "/api/v1/transport-requests/";
export const getRequests = (query = "", signal?: AbortSignal) => api<RequestPage>(`${root}${query ? `?${query}` : ""}`, { signal });
export const getRequestSuggestions = (search: string, status = "", signal?: AbortSignal) => {
  const query = new URLSearchParams({ search, page_size: "5" });
  if (status) query.set("status", status);
  return getRequests(query.toString(), signal);
};
export const getRequest = (id: string, signal?: AbortSignal) => api<TransportRequest>(`${root}${encodeURIComponent(id)}/`, { signal });
export const getRequestRoute = (id: string, signal?: AbortSignal) => api<TransportRoute>(`${root}${encodeURIComponent(id)}/route/`, { signal });
export const suggestPlaces = (query: string, sessionId: string, signal?: AbortSignal) => api<PlaceSuggestions>(`${root}places/suggest/`, { method: "POST", body: JSON.stringify({ query, session_id: sessionId }), signal });
export const getPlaceDetails = (type: string, id: string, sessionId: string, signal?: AbortSignal) => api<PlaceDetails>(`${root}places/details/${encodeURIComponent(type)}/${encodeURIComponent(id)}/?session_id=${encodeURIComponent(sessionId)}`, { signal });
export const getSummary = (signal?: AbortSignal) => api<Summary>(`${root}summary/`, { signal });
export const getCalendar = (start: string, end: string, signal?: AbortSignal) => api<CalendarResponse>(`${root}calendar/?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`, { signal });
export const createRequest = (body: unknown, signal?: AbortSignal) => api<TransportRequest>(root, { method: "POST", body: JSON.stringify(body), signal });
export const editRequest = (id: string, body: unknown, signal?: AbortSignal) => api<TransportRequest>(`${root}${encodeURIComponent(id)}/`, { method: "PATCH", body: JSON.stringify(body), signal });
export const mutateRequest = (id: string, action: string, body: unknown = {}, signal?: AbortSignal) => api<TransportRequest>(`${root}${encodeURIComponent(id)}/${action}/`, { method: "POST", body: JSON.stringify(body), signal });
