import { api } from "./api";

export type NumberCodingRule = {
  id:number; authority:string; jurisdiction:string; weekday:number; weekday_label:string;
  restricted_last_digits:number[]; start_time:string|null; end_time:string|null;
  effective_from:string; effective_until:string|null; is_active:boolean;
  source_reference:string; notes:string; created_at:string; updated_at:string;
};
export type NumberCodingSuspension = {
  id:number; authority:string; jurisdiction:string; starts_at:string; ends_at:string;
  reason:string; source_reference:string; is_active:boolean; created_by:number;
  created_by_name:string; created_at:string; updated_at:string;
};
export type VehicleCodingExemption = {
  id:number; vehicle:number; vehicle_display_name:string; plate_number:string;
  authority:string; jurisdiction:string; starts_at:string; ends_at:string; reason:string;
  source_reference:string; is_active:boolean; verified_by:number; verified_by_name:string;
  created_at:string; updated_at:string;
};

const root = "/api/v1/vehicles/number-coding/";
export const getNumberCodingRules = (signal?:AbortSignal) => api<NumberCodingRule[]>(`${root}rules/`, { signal });
export const saveNumberCodingRule = (body:unknown, id?:number) => api<NumberCodingRule>(`${root}rules/${id ? `${id}/` : ""}`, { method:id ? "PATCH" : "POST", body:JSON.stringify(body) });
export const getNumberCodingSuspensions = (signal?:AbortSignal) => api<NumberCodingSuspension[]>(`${root}suspensions/`, { signal });
export const saveNumberCodingSuspension = (body:unknown, id?:number) => api<NumberCodingSuspension>(`${root}suspensions/${id ? `${id}/` : ""}`, { method:id ? "PATCH" : "POST", body:JSON.stringify(body) });
export const getVehicleCodingExemptions = (signal?:AbortSignal) => api<VehicleCodingExemption[]>(`${root}exemptions/`, { signal });
export const saveVehicleCodingExemption = (body:unknown, id?:number) => api<VehicleCodingExemption>(`${root}exemptions/${id ? `${id}/` : ""}`, { method:id ? "PATCH" : "POST", body:JSON.stringify(body) });
