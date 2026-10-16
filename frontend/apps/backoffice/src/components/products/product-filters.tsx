"use client";

import { Button, Input, Select, type SelectOption } from "@ecommerce/ui";
import { useUrlText } from "../../lib/use-url-text";
import {
  hasActiveFilters,
  impliedSort,
  PAGE_SIZES,
  PRICE_FILTER,
  sortToStore,
  type ProductSearchState,
  type SortValue,
} from "../../lib/product-search";
import type { Category } from "../../lib/types";

const ALL = "all";
const AVAILABILITY: readonly SelectOption[] = [
  { value: "any", label: "Any availability" },
  { value: "in_stock", label: "In stock only" },
];
const SORTS: readonly SelectOption[] = [
  { value: "newest", label: "Newest first" },
  { value: "relevance", label: "Best match" },
  { value: "price_asc", label: "Price, low to high" },
  { value: "price_desc", label: "Price, high to low" },
];
const PRICE_ERROR = "Enter a price like 19.99";

export type ProductFiltersProps = {
  state: ProductSearchState;
  categories: readonly Category[];
  fieldErrors?: Record<string, string>;
  onChange: (patch: Partial<ProductSearchState>) => void;
  onClear: () => void;
};

function categoryOptions(categories: readonly Category[], selected: string | null): SelectOption[] {
  const options = [{ value: ALL, label: "All categories" }, ...categories.map(({ slug, name }) => ({ value: slug, label: name }))];
  return selected !== null && !categories.some(({ slug }) => slug === selected)
    ? [...options, { value: selected, label: selected }]
    : options;
}

function priceError(draft: string, serverError: string | undefined): string | undefined {
  const text = draft.trim();
  return text !== "" && !PRICE_FILTER.test(text) ? PRICE_ERROR : serverError;
}

export function ProductFilters({ state, categories, fieldErrors = {}, onChange, onClear }: ProductFiltersProps) {
  const [queryDraft, setQueryDraft] = useUrlText({
    value: state.q,
    commit: (q) => {
      onChange({ q });
    },
  });
  const [minDraft, setMinDraft] = useUrlText({
    value: state.min_price,
    accept: (text) => PRICE_FILTER.test(text),
    commit: (min_price) => {
      onChange({ min_price });
    },
  });
  const [maxDraft, setMaxDraft] = useUrlText({
    value: state.max_price,
    accept: (text) => PRICE_FILTER.test(text),
    commit: (max_price) => {
      onChange({ max_price });
    },
  });

  return (
    <form
      role="search"
      aria-label="Filter products"
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="sm:col-span-2">
          <Input
            label="Search"
            type="search"
            name="q"
            autoComplete="off"
            value={queryDraft}
            onChange={(event) => {
              setQueryDraft(event.target.value);
            }}
            hint="Name, description or SKU. Small typos are tolerated."
          />
        </div>
        <Select
          label="Category"
          options={categoryOptions(categories, state.category)}
          value={state.category ?? ALL}
          onValueChange={(value) => {
            onChange({ category: value === ALL ? null : value });
          }}
        />
        <Select
          label="Availability"
          options={AVAILABILITY}
          value={state.in_stock ? "in_stock" : "any"}
          onValueChange={(value) => {
            onChange({ in_stock: value === "in_stock" });
          }}
        />
        <Input
          label="Minimum price"
          name="min_price"
          inputMode="decimal"
          autoComplete="off"
          value={minDraft}
          error={priceError(minDraft, fieldErrors.min_price)}
          onChange={(event) => {
            setMinDraft(event.target.value);
          }}
        />
        <Input
          label="Maximum price"
          name="max_price"
          inputMode="decimal"
          autoComplete="off"
          value={maxDraft}
          error={priceError(maxDraft, fieldErrors.max_price)}
          onChange={(event) => {
            setMaxDraft(event.target.value);
          }}
        />
        <Select
          label="Sort by"
          options={SORTS}
          value={impliedSort(state)}
          onValueChange={(value) => {
            onChange({ sort: sortToStore(value as SortValue, state.q) });
          }}
        />
        <Select
          label="Results per page"
          options={PAGE_SIZES.map((size) => ({ value: String(size), label: `${size} per page` }))}
          value={String(state.limit)}
          onValueChange={(value) => {
            onChange({ limit: Number(value) });
          }}
        />
      </div>
      {hasActiveFilters(state) ? (
        <div>
          <Button variant="secondary" onClick={onClear}>
            Clear filters
          </Button>
        </div>
      ) : null}
    </form>
  );
}
