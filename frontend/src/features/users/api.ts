import { api } from "../../services/api";

export type ManagedRole = "FLEET_MANAGER" | "DISPATCHER";
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
