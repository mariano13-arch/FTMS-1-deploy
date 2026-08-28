import type { RequestStatus } from "../types";
import { StatusBadge, workflowStatusTone } from "../../../components/common/StatusBadge";
import { humanize as words } from "../../../utils/text";

const statusLabel: Record<RequestStatus, string> = {
  FOR_APPROVAL: "Awaiting Decision",
  NEEDS_MORE_DETAILS: "Needs More Details",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  READY_FOR_DISPATCH: "Ready for Dispatch",
  CANCELLED: "Cancelled",
};

export function PriorityChip({ value }: { value: string }) {
  return <span className={`badge priority-chip priority-chip--${value.toLowerCase()}`} data-indicator="priority">{words(value)}</span>;
}

export function WorkflowStatusBadge({ value }: { value: RequestStatus }) {
  const key = value.toLowerCase() as keyof typeof workflowStatusTone;
  return (
    <span data-indicator="workflow-status">
      <StatusBadge
        status={value.toLowerCase()}
        label={statusLabel[value]}
        tone={workflowStatusTone[key] ?? "neutral"}
      />
    </span>
  );
}
