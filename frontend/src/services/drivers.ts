import { api } from "./api";

export const employmentStatuses = ["ACTIVE", "ON_LEAVE", "SUSPENDED", "TERMINATED"] as const;
export const eligibilityStatuses = ["ELIGIBLE", "RESTRICTED", "NOT_ELIGIBLE"] as const;
export const driverDocumentTypes = ["DRIVER_LICENSE", "MEDICAL_CERTIFICATE", "TRAINING_CERTIFICATE", "OTHER"] as const;
export type Driver = {
  id:number; driver_code:string; external_hr_id:string|null; first_name:string; middle_name:string;
  last_name:string; full_name:string; contact_number:string; email:string; photo_url:string|null;
  employment_status:typeof employmentStatuses[number]; date_hired:string|null; linked_user:number|null;
  linked_user_display:string|null; license_number:string; license_category:string; license_codes:string;
  license_issue_date:string|null; license_expiry_date:string|null; medical_certificate_expiry_date:string|null;
  eligibility_status:typeof eligibilityStatuses[number]; eligibility_reasons:string[];
  safety_score:null; safety_score_status:"NOT_SCORED"; created_at:string; updated_at:string;
};
export type DriverPage={count:number;next:string|null;previous:string|null;results:Driver[]};
export type DriverDocument={id:number;driver:number;document_type:typeof driverDocumentTypes[number];title:string;reference_number:string;issuer_name:string;issued_date:string|null;effective_date:string|null;expiry_date:string|null;file_name:string;download_url:string;uploaded_by:number;uploaded_by_name:string;created_at:string;updated_at:string};
export type DriverDocumentPage={count:number;next:string|null;previous:string|null;results:DriverDocument[]};
export const getDrivers=(query="",signal?:AbortSignal)=>api<DriverPage>(`/api/v1/drivers/${query?`?${query}`:""}`,{signal});
export const createDriver=(body:FormData,signal?:AbortSignal)=>api<Driver>("/api/v1/drivers/",{method:"POST",body,signal});
export const editDriver=(id:number,body:FormData,signal?:AbortSignal)=>api<Driver>(`/api/v1/drivers/${id}/`,{method:"PATCH",body,signal});
export const getDriverDocuments=(id:number,signal?:AbortSignal)=>api<DriverDocumentPage>(`/api/v1/drivers/${id}/documents/`,{signal});
export const createDriverDocument=(id:number,body:FormData,signal?:AbortSignal)=>api<DriverDocument>(`/api/v1/drivers/${id}/documents/`,{method:"POST",body,signal});
