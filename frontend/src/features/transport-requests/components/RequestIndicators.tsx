import type { RequestStatus } from "../types";

const words = (value: string) => value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, character => character.toUpperCase());
const priorityIcon: Record<string, string> = { LOW: "↓", NORMAL: "–", HIGH: "↑", URGENT: "↑↑" };
const statusLabel: Record<RequestStatus, string> = {
  FOR_APPROVAL: "Awaiting Decision",
  NEEDS_MORE_DETAILS: "Needs More Details",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  READY_FOR_DISPATCH: "Ready for Dispatch",
  CANCELLED: "Cancelled",
};

export function PriorityChip({ value }: { value: string }) {
  return <span className={`priority-chip priority-chip--${value.toLowerCase()}`} data-indicator="priority"><span aria-hidden="true">{priorityIcon[value] ?? "•"}</span>{words(value)}</span>;
}

export function WorkflowStatusBadge({ value }: { value: RequestStatus }) {
  return <span className={`workflow-badge workflow-badge--${value.toLowerCase()}`} data-indicator="workflow-status">{statusLabel[value]}</span>;
}
