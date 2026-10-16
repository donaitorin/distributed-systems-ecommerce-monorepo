import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import { useState } from "react";
import type { ProductSearchState } from "../../lib/product-search";
import { ProductFilters, type ProductFiltersProps } from "./product-filters";
import { STORY_CATEGORIES } from "../story-support";

const EMPTY: ProductSearchState = {
  q: null,
  category: null,
  min_price: null,
  max_price: null,
  in_stock: false,
  sort: null,
  limit: 24,
  cursor: null,
};

function Stateful(props: Omit<ProductFiltersProps, "onChange" | "onClear" | "state"> & { initial: ProductSearchState }) {
  const [state, setState] = useState(props.initial);
  return (
    <ProductFilters
      {...props}
      state={state}
      onChange={(patch) => {
        setState((current) => ({ ...current, ...patch }));
      }}
      onClear={() => {
        setState(EMPTY);
      }}
    />
  );
}

const meta = {
  title: "Backoffice/ProductFilters",
  component: Stateful,
  parameters: { layout: "padded" },
  args: { categories: STORY_CATEGORIES, initial: EMPTY },
} satisfies Meta<typeof Stateful>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const WithFilters: Story = {
  args: {
    initial: { ...EMPTY, q: "shoes", category: "sports", min_price: "10", max_price: "99.50", in_stock: true, sort: "price_asc" },
  },
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByRole("button", { name: "Clear filters" })).toBeVisible();
  },
};

export const InvalidPrice: Story = {
  play: async ({ canvasElement }) => {
    const input = within(canvasElement).getByLabelText("Minimum price");
    await userEvent.type(input, "abc");
    await expect(input).toBeInvalid();
  },
};

export const ServerError: Story = {
  args: { fieldErrors: { min_price: "must not be greater than max_price" }, initial: { ...EMPTY, min_price: "50", max_price: "10" } },
};

export const NoCategories: Story = { args: { categories: [] } };

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
