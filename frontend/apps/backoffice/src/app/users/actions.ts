"use server";

import type { Failure } from "../../lib/failure";
import type { Role } from "../../lib/types";
import { changeUserRole, type RoleChanged } from "../../server/accounts";

export async function changeUserRoleAction(userId: string, role: Role): Promise<RoleChanged | Failure> {
  return changeUserRole(userId, role);
}
