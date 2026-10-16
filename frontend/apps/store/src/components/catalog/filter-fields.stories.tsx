import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import { useState } from "react";
import type { ProductSearchState } from "@ecommerce/web-core";
import { STORY_CATEGORIES } from "../story-support";
import { FilterFields, type FilterFieldsProps } from "./filter-fields";

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

function Stateful(props: Omit<FilterFieldsProps, "onChange" | "state"> & { initial: ProductSearchState }) {
  const [state, setState] = useState(props.initial);
  return (
    <div className="w-72">
      <FilterFields
        {...props}
        state={state}
        onChange={(patch) => {
          setState((current) => ({ ...current, ...patch }));
        }}
      />
    </div>
  );
}

const meta = {
  title: "Store/FilterFields",
  component: Stateful,
  args: { categories: STORY_CATEGORIES, initial: EMPTY },
} satisfies Meta<typeof Stateful>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const WithFilters: Story = {
  args: { initial: { ...EMPTY, category: "footwear", min_price: "20", max_price: "150", in_stock: true } },
};

export const InvalidPrice: Story = {
  play: async ({ canvasElement }) => {
    const input = within(canvasElement).getByLabelText("Minimum");
    await userEvent.type(input, "abc");
    await expect(input).toBeInvalid();
  },
};

export const ServerError: Story = {
  args: {
    fieldErrors: { min_price: "must not be greater than max_price" },
    initial: { ...EMPTY, min_price: "50", max_price: "10" },
  },
};

export const NoCategories: Story = { args: { categories: [] } };
