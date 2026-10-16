import "./zod-config";
import { parseAsBoolean } from "nuqs/server";
import { z } from "zod";
import type { CatalogPaths } from "@ecommerce/api-client";
import { zodParser } from "./zod-parser";

export const PAGE_SIZES = [12, 24, 48] as const;
export const DEFAULT_PAGE_SIZE = 24;
export const SORT_VALUES = ["relevance", "price_asc", "price_desc", "newest"] as const;
export type SortValue = (typeof SORT_VALUES)[number];

const QUERY_MAX_LENGTH = 100;
const CATEGORY_SLUG = /^[a-z0-9][a-z0-9-]{0,119}$/;
const CURSOR_MAX_LENGTH = 512;
export const PRICE_FILTER = /^\d{1,10}(\.\d{1,2})?$/;

export const productSearchParsers = {
  q: zodParser(z.string().trim().min(1).max(QUERY_MAX_LENGTH)),
  category: zodParser(z.string().regex(CATEGORY_SLUG)),
  min_price: zodParser(z.string().regex(PRICE_FILTER)),
  max_price: zodParser(z.string().regex(PRICE_FILTER)),
  in_stock: parseAsBoolean.withDefault(false),
  sort: zodParser(z.enum(SORT_VALUES)),
  limit: zodParser(z.enum(["12", "24", "48"]).transform(Number)).withDefault(DEFAULT_PAGE_SIZE),
  cursor: zodParser(z.string().min(1).max(CURSOR_MAX_LENGTH)),
};

export type ProductSearchState = {
  q: string | null;
  category: string | null;
  min_price: string | null;
  max_price: string | null;
  in_stock: boolean;
  sort: SortValue | null;
  limit: number;
  cursor: string | null;
};

type ListQuery = NonNullable<CatalogPaths["/api/v1/products"]["get"]["parameters"]["query"]>;

export function toCatalogQuery(state: ProductSearchState): ListQuery {
  return {
    ...(state.q ? { q: state.q } : {}),
    ...(state.category ? { category: state.category } : {}),
    ...(state.min_price ? { min_price: state.min_price } : {}),
    ...(state.max_price ? { max_price: state.max_price } : {}),
    ...(state.in_stock ? { in_stock: true } : {}),
    ...(state.sort ? { sort: state.sort } : {}),
    limit: state.limit,
    ...(state.cursor ? { cursor: state.cursor } : {}),
  };
}

export function impliedSort(state: Pick<ProductSearchState, "q" | "sort">): SortValue {
  return state.sort ?? (state.q ? "relevance" : "newest");
}

export function sortToStore(value: SortValue, q: string | null): SortValue | null {
  const implied: SortValue = q ? "relevance" : "newest";
  return value === implied ? null : value;
}

export function hasActiveFilters(state: ProductSearchState): boolean {
  return Boolean(state.q || state.category || state.min_price || state.max_price || state.in_stock);
}
