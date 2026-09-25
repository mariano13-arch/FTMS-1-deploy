import { api } from "./api";
import type { AssignedVehicle, TransportRequestListItem } from "../features/transport-requests/types";
import type { FleetActiveRoute } from "../features/live-fleet/api";

export type DispatchDriver = { id:number; driver_code:string; full_name:string; eligibility_status:"ELIGIBLE" };
export type NumberCodingStatus = "CLEAR"|"RESTRICTED"|"EXEMPT"|"SUSPENDED"|"UNKNOWN";
export type DispatchVehicle = AssignedVehicle & { current_location_available?:boolean; number_coding?:{status:NumberCodingStatus;reason:string;plate_last_digit:number|null} };
export type DispatchAssignment = {
  id:number; plan_id?:number|null; transport_request_id:string; request_number:string; vehicle:AssignedVehicle;
  driver:DispatchDriver; selection_mode:"OPTIMIZED"|"MANUAL"; override_reason:string;
  confirmed_by:string; confirmed_at:string; is_accepted:boolean; accepted_at:string|null;
  execution_status:"ASSIGNED"|"EN_ROUTE_TO_PICKUP"|"AT_PICKUP"|"IN_TRANSIT"|"AT_DESTINATION"|"COMPLETED";
  execution_status_label:string; completed_at:string|null; created_at:string; updated_at:string;
};
export type OperationalDispatchAssignment = DispatchAssignment & {
  transport_request: TransportRequestListItem;
};
export type OperationalAssignmentPage = {
  count:number; next:string|null; previous:string|null;
  results:OperationalDispatchAssignment[];
};
export type ConsolidationStop={sequence:number;request_id:string;request_number:string;stop_type:"PICKUP"|"DELIVERY";label:string;latitude:string;longitude:string;load_change_kg:string};
export type ConsolidationMetrics={vehicles:number;travel_time_seconds:number;distance_meters:number};
export type ConsolidationRecommendation={request_ids:string[];requests:TransportRequestListItem[];driver:DispatchDriver;vehicle:AssignedVehicle;route:{stops:ConsolidationStop[];peak_load_kg:string;capacity_kg:string;capacity_utilization_percent:number;separate:ConsolidationMetrics;consolidated:ConsolidationMetrics;difference:ConsolidationMetrics};explanation:string[];recommendation_token:string;geometry:null};
export type ConsolidationResponse={generated_at:string;optimizer:string;routing_source:string;candidate_limit:number;recommendation:ConsolidationRecommendation|null;exclusions:string[]};
export type DispatchPlan={id:number;plan_type:"CONSOLIDATED";vehicle:AssignedVehicle;driver:DispatchDriver;stops:Array<{sequence:number;transport_request_id:string;request_number:string;stop_type:string;label:string}>;confirmed_by:string;confirmed_at:string};
export type DispatchBoardData = {
  summary:{approved_requests:number;awaiting_assignment:number;confirmed_assignments:number;ready_for_dispatch:number;optimizer_eligible:number;needs_attention:number;no_eligible_driver:number;no_gis_vehicle:number;schedule_conflict:number;number_coding_blocked?:number};
  requests:TransportRequestListItem[]; assignments:DispatchAssignment[];
  eligible_drivers:DispatchDriver[]; active_vehicles:DispatchVehicle[];
  manual_candidates:Record<string,{drivers:DispatchDriver[];vehicles:DispatchVehicle[]}>;
  assignment_audit:Record<string,DispatchAuditEvent[]>;
  recommendation_fingerprints:Record<string,string>;
};
export type DispatchAuditEvent={kind:"ASSIGNMENT_CONFIRMED"|"ASSIGNMENT_CHANGED"|"PREPARED_FOR_DISPATCH"|"DRIVER_ACCEPTED";driver?:DispatchDriver;vehicle?:AssignedVehicle;selection_mode?:"OPTIMIZED"|"MANUAL";reason:string;operator:string;timestamp:string};
export type ScheduleContext={selected:{start:string;end:string};driver:{status:"AVAILABLE"|"CONFLICT";windows:{request_number:string;start:string;end:string}[]};vehicle:{status:"AVAILABLE"|"CONFLICT";windows:{request_number:string;start:string;end:string}[]}};
export type FuelRateBasis="CURRENT_AI"|"HISTORICAL_AI_BASELINE"|"FLEET_REFERENCE_BASELINE"|"UNAVAILABLE";
export type FuelEstimate={
  status:"AVAILABLE"|"UNAVAILABLE";reason:string|null;
  fuel_rate_basis:FuelRateBasis|null;fuel_rate_basis_label?:string|null;
  fuel_rate_lph:string|null;travel_time_seconds:string|null;
  estimated_fuel_liters:string|null;fuel_type:string|null;fuel_grade:string|null;
  price_per_liter:string|null;currency:string|null;price_provider:string|null;
  price_source_mode:string|null;price_effective_at:string|null;
  estimated_fuel_cost_php:string|null;fuel_source_timestamp:string|null;
  history_sample_count:number|null;fuel_rate_provenance?:string|null;
};
export type CandidateComparison={driver:DispatchDriver;vehicle:AssignedVehicle;travel_time_seconds:number|null;distance_meters:number|null;traffic_delay_seconds:number|null;result:"RECOMMENDED"|"FEASIBLE"|"MANUAL_ONLY";fuel_estimate:FuelEstimate};
export type Recommendation = {
  transport_request_id:string;request_number:string;recommended_vehicle:AssignedVehicle;
  recommended_driver:DispatchDriver;travel_time_seconds:number;distance_meters:number;
  traffic_delay_seconds:number;recommendation_token:string;
  planning_fingerprint:string;
  fuel_estimate:FuelEstimate;
  airport_pickup_timing?:{status:"AVAILABLE"|"BLOCKED";message:string;arrival_basis:"ACTUAL"|"ESTIMATED"|"SCHEDULED"|null;passenger_ready_at:string|null;recommended_departure_at:string|null}|null;
  explanation:string[];schedule_context:ScheduleContext;gis_preview:{status:string;vehicle_location:{vehicle_id:string;latitude:number;longitude:number}|null;pickup:{latitude:string;longitude:string;label:string};destination:{latitude:string;longitude:string;label:string};geometry:null};
};
export type RecommendationResponse = {
  generated_at:string;optimizer:"GOOGLE_OR_TOOLS";routing_source:"TOMTOM";
  requests_considered:number;requests_recommended:number;recommendations:Recommendation[];
  unassigned:{transport_request_id:string;request_number:string;reason:string}[];
  candidate_comparison:Record<string,CandidateComparison[]>;
  excluded_candidates:Record<string,{kind:"DRIVER"|"VEHICLE";name:string;code:string;reason:string;details:string[]}[]>;
  comparison_scope:{limit:number;limited:boolean};
};
const root="/api/v1/transport-requests/dispatch-board/";
export const getDispatchBoard=(signal?:AbortSignal)=>api<DispatchBoardData>(root,{signal});
export const getOperationalAssignments=(scope:"active"|"completed",page=1,search="",signal?:AbortSignal)=>{
  const query=new URLSearchParams({scope,page:String(page),page_size:"15"});
  if(search.trim()) query.set("search",search.trim());
  return api<OperationalAssignmentPage>(`/api/v1/transport-requests/dispatch-assignments/?${query}`,{signal});
};
export const runDispatchOptimization=(requestId:string,signal?:AbortSignal)=>api<RecommendationResponse>(`${root}recommendations/`,{method:"POST",body:JSON.stringify({request_ids:[requestId]}),signal});
export const getRecommendationRoute=(recommendation:Recommendation,signal?:AbortSignal)=>api<{route:FleetActiveRoute}>(`${root}recommendation-route/`,{method:"POST",body:JSON.stringify({transport_request_id:recommendation.transport_request_id,vehicle_id:recommendation.recommended_vehicle.id,driver_id:recommendation.recommended_driver.id,recommendation_token:recommendation.recommendation_token}),signal});
export const confirmDispatchAssignment=(body:unknown,signal?:AbortSignal)=>api<DispatchAssignment>(`${root}confirm/`,{method:"POST",body:JSON.stringify(body),signal});
export const analyzeConsolidation=(requestId:string,signal?:AbortSignal)=>api<ConsolidationResponse>(`${root}consolidation-recommendations/`,{method:"POST",body:JSON.stringify({selected_request_id:requestId}),signal});
export const confirmConsolidation=(recommendationToken:string)=>api<DispatchPlan>(`${root}consolidations/confirm/`,{method:"POST",body:JSON.stringify({recommendation_token:recommendationToken})});
export const prepareConsolidation=(planId:number)=>api<DispatchPlan>(`${root}consolidations/${planId}/prepare/`,{method:"POST",body:"{}"});
