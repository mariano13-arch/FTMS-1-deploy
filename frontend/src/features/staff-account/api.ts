import { api } from "../../services/api";
import { bootstrapCsrf } from "../../services/auth";

export type StaffPasswordSetupInput = {
  uid: string;
  token: string;
  new_password: string;
  confirm_password: string;
};

export async function setupStaffPassword(input: StaffPasswordSetupInput, signal?: AbortSignal) {
  await bootstrapCsrf(signal);
  await api<null>("/api/v1/auth/staff/setup-password/", {
    method: "POST",
    body: JSON.stringify(input),
    signal,
  });
}
