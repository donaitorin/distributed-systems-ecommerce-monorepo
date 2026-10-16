"use client";

import { Button, Input, Select, type SelectOption } from "@ecommerce/ui";
import { useUrlText } from "@ecommerce/web-core/client";
import {
  ALL_CATEGORIES,
  categoryChoices,
  hasActiveFilters,
  impliedSort,
  PAGE_SIZES,
  PRICE_FILTER,
  priceFieldError,
  SORT_CHOICES,
  sortToStore,
  type ProductSearchState,
  type SortValue,
} from "@ecommerce/web-core";
import type { Category } from "../../lib/types";

const AVAILABILITY: readonly SelectOption[] = [
  { value: "any", label: "Any availability" },
  { value: "in_stock", label: "In stock only" },
];

export type ProductFiltersProps = {
  state: ProductSearchState;
  categories: readonly Category[];
  fieldErrors?: Record<string, string>;
  onChange: (patch: Partial<ProductSearchState>) => void;
  onClear: () => void;
};

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
          options={categoryChoices(categories, state.category)}
          value={state.category ?? ALL_CATEGORIES}
          onValueChange={(value) => {
            onChange({ category: value === ALL_CATEGORIES ? null : value });
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
          error={priceFieldError(minDraft, fieldErrors.min_price)}
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
          error={priceFieldError(maxDraft, fieldErrors.max_price)}
          onChange={(event) => {
            setMaxDraft(event.target.value);
          }}
        />
        <Select
          label="Sort by"
          options={SORT_CHOICES}
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
