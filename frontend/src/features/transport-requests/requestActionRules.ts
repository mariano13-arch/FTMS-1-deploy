import type { RequestStatus } from "./types";

export type TransportRequestRole = "FLEET_ADMIN" | "FLEET_MANAGER" | "DISPATCHER" | "FLEET_STAFF" | string | null | undefined;

export const isRequestManager = (role: TransportRequestRole) => role === "FLEET_ADMIN" || role === "FLEET_MANAGER";
export const isRequestOperator = (role: TransportRequestRole) => isRequestManager(role) || role === "DISPATCHER";
export const canEditRequest = (status: RequestStatus, role: TransportRequestRole) => isRequestOperator(role) && ["FOR_APPROVAL", "NEEDS_MORE_DETAILS"].includes(status);
export const canResubmitRequest = (status: RequestStatus, role: TransportRequestRole) => isRequestOperator(role) && status === "NEEDS_MORE_DETAILS";
export const canPrepareRequest = (status: RequestStatus, role: TransportRequestRole) => isRequestOperator(role) && status === "APPROVED";
export const canCancelRequest = (status: RequestStatus, role: TransportRequestRole) => isRequestManager(role) && ["FOR_APPROVAL", "NEEDS_MORE_DETAILS", "APPROVED", "READY_FOR_DISPATCH"].includes(status);
