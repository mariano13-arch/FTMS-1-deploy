import { api } from "../../services/api";
import type { ManagedRole } from "../users/api";

export type PermissionEntry = { module: string; action: string };
export type PermissionMatrix = {
  definitions: Record<string, string[]>;
  roles: Record<ManagedRole, Record<string, string[]>>;
};

export function getRolePermissions(signal?: AbortSignal) {
  return api<PermissionMatrix>("/api/v1/auth/role-permissions/", { signal });
}

export function replaceRolePermissions(role: ManagedRole, permissions: PermissionEntry[]) {
  return api<PermissionMatrix>(`/api/v1/auth/role-permissions/${role}/`, {
    method: "PUT",
    body: JSON.stringify({ permissions }),
  });
}
