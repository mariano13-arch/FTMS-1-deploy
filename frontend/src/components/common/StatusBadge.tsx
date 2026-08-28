export type StatusBadgeTone =
  | "neutral"
  | "info"
  | "warning"
  | "success"
  | "danger"
  | "attention";

type StatusBadgeProps = {
  status: string;
  label?: string;
  tone: StatusBadgeTone;
  className?: string;
};

function toTitleCase(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function StatusBadge({
  status,
  label,
  tone,
  className = "",
}: StatusBadgeProps) {
  return (
    <span
      className={`status-badge status-badge--${tone} ${className}`.trim()}
      data-status={status}
    >
      {label ?? toTitleCase(status)}
    </span>
  );
}

/* ---------- Tone maps per module ---------- */

export const vehicleStatusTone: Record<string, StatusBadgeTone> = {
  active: "success",
  inactive: "neutral",
};

export const dispatchStatusTone: Record<string, StatusBadgeTone> = {
  pending: "warning",
  confirmed: "success",
  ready: "info",
};

export const workflowStatusTone: Record<string, StatusBadgeTone> = {
  for_approval: "warning",
  needs_more_details: "attention",
  approved: "success",
  ready_for_dispatch: "info",
  rejected: "danger",
  cancelled: "neutral",
};

export const driverEmploymentTone: Record<string, StatusBadgeTone> = {
  ACTIVE: "success",
  INACTIVE: "neutral",
  SUSPENDED: "danger",
  PROBATION: "warning",
};

export const driverEligibilityTone: Record<string, StatusBadgeTone> = {
  ELIGIBLE: "success",
  INELIGIBLE: "danger",
  PENDING: "warning",
  REVIEW: "attention",
};

export const freshnessTone: Record<string, StatusBadgeTone> = {
  fresh: "success",
  stale: "warning",
};

export default StatusBadge;
