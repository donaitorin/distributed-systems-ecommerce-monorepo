"use client";

import { Checkbox, Input, Select } from "@ecommerce/ui";
import {
  ALL_CATEGORIES,
  categoryChoices,
  PRICE_FILTER,
  priceFieldError,
  type Category,
  type ProductSearchState,
} from "@ecommerce/web-core";
import { useUrlText } from "@ecommerce/web-core/client";

export type FilterFieldsProps = {
  state: ProductSearchState;
  categories: readonly Category[];
  fieldErrors?: Record<string, string>;
  onChange: (patch: Partial<ProductSearchState>) => void;
};

export function FilterFields({ state, categories, fieldErrors = {}, onChange }: FilterFieldsProps) {
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
    <div className="flex flex-col gap-4">
      <Select
        label="Category"
        options={categoryChoices(categories, state.category)}
        value={state.category ?? ALL_CATEGORIES}
        onValueChange={(value) => {
          onChange({ category: value === ALL_CATEGORIES ? null : value });
        }}
      />
      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium text-primary">Price in USD</legend>
        <div className="grid grid-cols-2 gap-2">
          <Input
            label="Minimum"
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
            label="Maximum"
            name="max_price"
            inputMode="decimal"
            autoComplete="off"
            value={maxDraft}
            error={priceFieldError(maxDraft, fieldErrors.max_price)}
            onChange={(event) => {
              setMaxDraft(event.target.value);
            }}
          />
        </div>
      </fieldset>
      <Checkbox
        label="In stock only"
        checked={state.in_stock}
        onChange={(event) => {
          onChange({ in_stock: event.target.checked });
        }}
      />
    </div>
  );
}
