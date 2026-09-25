import { api } from "./api";

export type PartnerFuelGrade =
  | "UNLEADED_91"
  | "PREMIUM_95"
  | "PREMIUM_97"
  | "REGULAR_DIESEL"
  | "PREMIUM_DIESEL";
export type PartnerFuelPrice = {
  id:number;fuel_type:"GASOLINE"|"DIESEL";fuel_grade:PartnerFuelGrade;
  price_per_liter:string;currency:"PHP";provider:"ShellPH";
  source_mode:"MANUAL"|"EXTERNAL_CACHED";effective_at:string;
  recorded_at:string;is_active:boolean;
};
export type PartnerFuelProduct = {
  fuel_grade:PartnerFuelGrade;label:string;fuel_type:"GASOLINE"|"DIESEL";
  vehicle_count:number;current_price:PartnerFuelPrice|null;history:PartnerFuelPrice[];
};
export type PartnerFuelPriceSettings = {
  provider:"ShellPH";provider_label:"Shell";products:PartnerFuelProduct[];
};

const url = "/api/v1/vehicles/partner-fuel-prices/";
export const getPartnerFuelPrices = (signal?:AbortSignal) =>
  api<PartnerFuelPriceSettings>(url, { signal });
export const recordPartnerFuelPrice = (body:{
  fuel_grade:PartnerFuelGrade;price_per_liter:string;effective_at:string;
}) => api<PartnerFuelPrice>(url, { method:"POST", body:JSON.stringify(body) });
