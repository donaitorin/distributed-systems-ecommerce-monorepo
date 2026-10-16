import type { Failure } from "@ecommerce/web-core";
import type { Role, UserPage } from "../lib/types";
import { toAccountsQuery, type UserSearchState } from "../lib/user-search";
import { gatewayApi } from "./gateway";
import { guarded } from "./guarded";

export type RoleChanged = { ok: true; userId: string; role: Role };

export async function loadUserPage(state: UserSearchState): Promise<UserPage | Failure> {
  return guarded(async () => {
    const { data } = await gatewayApi().get("/api/v1/accounts", { query: toAccountsQuery(state) });
    return data;
  });
}

export async function changeUserRole(userId: string, role: Role): Promise<RoleChanged | Failure> {
  return guarded(async () => {
    const { data } = await gatewayApi().patch("/api/v1/auth/users/{user_id}/role", {
      params: { user_id: userId },
      body: { role },
    });
    return { ok: true as const, userId: data.id, role: data.role };
  });
}
