import "./zod-config";
import type { AccountsPaths } from "@ecommerce/api-client";
import { z } from "zod";
import { zodParser } from "./zod-parser";

export const USER_PAGE_SIZES = [25, 50, 100] as const;
export const DEFAULT_USER_PAGE_SIZE = 25;
export const ROLES = ["customer", "admin"] as const;

export const userSearchParsers = {
  email: zodParser(z.string().trim().min(1).max(254)),
  role: zodParser(z.enum(ROLES)),
  limit: zodParser(z.enum(["25", "50", "100"]).transform(Number)).withDefault(DEFAULT_USER_PAGE_SIZE),
  cursor: zodParser(z.string().min(1).max(512)),
};

export type UserSearchState = {
  email: string | null;
  role: (typeof ROLES)[number] | null;
  limit: number;
  cursor: string | null;
};

type ListQuery = NonNullable<AccountsPaths["/api/v1/accounts"]["get"]["parameters"]["query"]>;

export function toAccountsQuery(state: UserSearchState): ListQuery {
  return {
    ...(state.email ? { email: state.email } : {}),
    ...(state.role ? { role: state.role } : {}),
    limit: state.limit,
    ...(state.cursor ? { cursor: state.cursor } : {}),
  };
}

export function hasUserFilters(state: UserSearchState): boolean {
  return Boolean(state.email || state.role);
}
