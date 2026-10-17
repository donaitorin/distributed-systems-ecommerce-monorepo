import "@ecommerce/web-core/zod-config";
import type { OrdersPaths } from "@ecommerce/api-client";
import { ORDER_STATUSES } from "@ecommerce/ui";
import { z } from "zod";
import { zodParser } from "@ecommerce/web-core";

export const ORDER_PAGE_SIZES = [25, 50, 100] as const;
export const DEFAULT_ORDER_PAGE_SIZE = 25;
const DAY_MS = 86_400_000;
const DAY = /^\d{4}-\d{2}-\d{2}$/;

function isRealDay(value: string): boolean {
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().startsWith(value);
}

const day = z.string().regex(DAY).refine(isRealDay);

export const orderSearchParsers = {
  status: zodParser(z.enum(ORDER_STATUSES)),
  from: zodParser(day),
  to: zodParser(day),
  limit: zodParser(z.enum(["25", "50", "100"]).transform(Number)).withDefault(DEFAULT_ORDER_PAGE_SIZE),
  cursor: zodParser(z.string().min(1).max(512)),
};

export type OrderSearchState = {
  status: (typeof ORDER_STATUSES)[number] | null;
  from: string | null;
  to: string | null;
  limit: number;
  cursor: string | null;
};

type ListQuery = NonNullable<OrdersPaths["/api/v1/admin/orders"]["get"]["parameters"]["query"]>;

export const RANGE_ERROR = "The end date must be on or after the start date.";

export function dateRangeError(state: Pick<OrderSearchState, "from" | "to">): string | null {
  return state.from !== null && state.to !== null && state.to < state.from ? RANGE_ERROR : null;
}

function startOfDay(value: string): string {
  return `${value}T00:00:00Z`;
}

function startOfNextDay(value: string): string {
  return new Date(Date.parse(startOfDay(value)) + DAY_MS).toISOString().replace(".000Z", "Z");
}

export function toOrdersQuery(state: OrderSearchState): ListQuery {
  return {
    ...(state.status ? { status: state.status } : {}),
    ...(state.from ? { created_from: startOfDay(state.from) } : {}),
    ...(state.to ? { created_to: startOfNextDay(state.to) } : {}),
    limit: state.limit,
    ...(state.cursor ? { cursor: state.cursor } : {}),
  };
}

export function hasOrderFilters(state: Pick<OrderSearchState, "status" | "from" | "to">): boolean {
  return Boolean(state.status || state.from || state.to);
}
