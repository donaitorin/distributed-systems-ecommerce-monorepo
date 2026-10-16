import { createLoader } from "nuqs/server";
import type { Category } from "./catalog-types";
import type { Failure } from "./failure";
import {
  PRICE_FILTER,
  productSearchParsers,
  type ProductSearchState,
  type SortValue,
} from "./product-search";

export const PRICE_ERROR = "Enter a price like 19.99";
export const ALL_CATEGORIES = "all";

export type SelectChoice = { value: string; label: string };

export const SORT_CHOICES: readonly SelectChoice[] = [
  { value: "newest", label: "Newest first" },
  { value: "relevance", label: "Best match" },
  { value: "price_asc", label: "Price, low to high" },
  { value: "price_desc", label: "Price, high to low" },
];

export const CLEARED_FILTERS: Partial<ProductSearchState> = {
  q: null,
  category: null,
  min_price: null,
  max_price: null,
  in_stock: false,
  sort: null,
  cursor: null,
};

export type SearchParamsRecord = Record<string, string | string[] | undefined>;

export function toSearchParams(record: SearchParamsRecord): URLSearchParams {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(record)) {
    for (const item of Array.isArray(value) ? value : value === undefined ? [] : [value]) {
      search.append(name, item);
    }
  }
  return search;
}

const loadSearch = createLoader(productSearchParsers);

export function loadProductSearch(record: SearchParamsRecord): ProductSearchState {
  return loadSearch(toSearchParams(record));
}

export function displayedSort(state: Pick<ProductSearchState, "q" | "sort">): SortValue {
  if (state.q) {
    return state.sort ?? "relevance";
  }
  return state.sort === null || state.sort === "relevance" ? "newest" : state.sort;
}

export function categoryChoices(categories: readonly Category[], selected: string | null): SelectChoice[] {
  const choices = [
    { value: ALL_CATEGORIES, label: "All categories" },
    ...categories.map(({ slug, name }) => ({ value: slug, label: name })),
  ];
  return selected !== null && !categories.some(({ slug }) => slug === selected)
    ? [...choices, { value: selected, label: selected }]
    : choices;
}

export function priceFieldError(draft: string, serverError: string | undefined): string | undefined {
  const text = draft.trim();
  return text !== "" && !PRICE_FILTER.test(text) ? PRICE_ERROR : serverError;
}

export type FilterChip = {
  id: "q" | "category" | "price" | "in_stock";
  label: string;
  patch: Partial<ProductSearchState>;
};

function priceChipLabel(min: string | null, max: string | null): string {
  if (min !== null && max !== null) {
    return `$${min} to $${max}`;
  }
  return min !== null ? `From $${min}` : `Up to $${max}`;
}

export function activeFilterChips(state: ProductSearchState, categories: readonly Category[]): FilterChip[] {
  const chips: FilterChip[] = [];
  if (state.q) {
    chips.push({
      id: "q",
      label: `Search: ${state.q}`,
      patch: { q: null },
    });
  }
  if (state.category) {
    const name = categories.find(({ slug }) => slug === state.category)?.name ?? state.category;
    chips.push({
      id: "category",
      label: `Category: ${name}`,
      patch: { category: null },
    });
  }
  if (state.min_price || state.max_price) {
    const label = priceChipLabel(state.min_price, state.max_price);
    chips.push({
      id: "price",
      label: `Price: ${label}`,
      patch: { min_price: null, max_price: null },
    });
  }
  if (state.in_stock) {
    chips.push({
      id: "in_stock",
      label: "In stock only",
      patch: { in_stock: false },
    });
  }
  return chips;
}

export function searchFailureMessage(failure: Failure): string {
  if (failure.status === 422) {
    return failure.fieldErrors.cursor !== undefined
      ? "This page link no longer matches the current filters."
      : "Some filters are not valid. Adjust them and try again.";
  }
  if (failure.status === 503 || failure.status === null) {
    return "The product search is not available right now. Try again in a moment.";
  }
  return failure.detail ?? failure.title;
}
