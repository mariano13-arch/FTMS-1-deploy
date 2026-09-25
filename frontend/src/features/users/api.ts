import { api } from "../../services/api";

export type ManagedRole = "FLEET_MANAGER" | "DISPATCHER" | "FLEET_STAFF";
export type SetupStatus = "pending" | "complete";
export type InvitationDelivery = "SENT" | "NOT_SENT_ERROR";

export type StaffRecord = {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: ManagedRole;
  is_active: boolean;
  setup_status: SetupStatus;
  date_joined: string;
  last_login: string | null;
};

export type CreateStaffInput = Pick<
  StaffRecord,
  "username" | "email" | "first_name" | "last_name" | "role"
>;

export async function listStaff(signal?: AbortSignal) {
  return (
    await api<{ results: StaffRecord[] }>("/api/v1/auth/staff/", { signal })
  ).results;
}

export function createStaff(input: CreateStaffInput) {
  return api<StaffRecord & { invitation_delivery: InvitationDelivery }>(
    "/api/v1/auth/staff/",
    { method: "POST", body: JSON.stringify(input) },
  );
}

export function updateStaffRole(userId: number, role: ManagedRole) {
  return api<StaffRecord>(`/api/v1/auth/staff/${userId}/role/`, {
    method: "PATCH",
    body: JSON.stringify({ role }),
  });
}

export function updateStaffStatus(userId: number, isActive: boolean) {
  return api<StaffRecord>(`/api/v1/auth/staff/${userId}/status/`, {
    method: "PATCH",
    body: JSON.stringify({ is_active: isActive }),
  });
}

export function resendStaffInvitation(userId: number) {
  return api<{ invitation_delivery: InvitationDelivery }>(
    `/api/v1/auth/staff/${userId}/resend-invitation/`,
    { method: "POST" },
  );
}

export type AuditOutcome = "SUCCESS" | "FAILURE" | "DENIED";
export type AuditEvent = {
  id: number;
  occurred_at: string;
  actor: number | null;
  actor_display: string;
  actor_type: string;
  action: string;
  target_type: string;
  target_id: string;
  target_label: string;
  outcome: AuditOutcome;
  source: string;
  ip_address: string | null;
  user_agent: string;
  changes: Record<string, unknown>;
  metadata: Record<string, unknown>;
};

export type AuditLogResponse = {
  count: number;
  next: string | null;
  previous: string | null;
  results: AuditEvent[];
};

export type AuditLogFilters = {
  occurred_after?: string;
  occurred_before?: string;
  actor?: string;
  action?: string;
  outcome?: string;
  page?: number;
};

export function listAuditLogs(filters: AuditLogFilters = {}, signal?: AbortSignal) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  const query = params.toString();
  return api<AuditLogResponse>(`/api/v1/auth/audit-logs/${query ? `?${query}` : ""}`, { signal });
}
