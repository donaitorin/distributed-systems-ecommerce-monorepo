import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { FilterChips } from "./filter-chips";

const meta = {
  title: "Components/FilterChips",
  component: FilterChips,
  args: {
    chips: [
      { id: "q", label: "Search: running shoes" },
      { id: "category", label: "Category: Footwear" },
      { id: "price", label: "Price: $20 to $150" },
      { id: "in_stock", label: "In stock only" },
    ],
    onRemove: fn(),
    onClearAll: fn(),
  },
} satisfies Meta<typeof FilterChips>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  play: async ({ canvasElement, args }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Remove filter: Category: Footwear" }));
    await expect(args.onRemove).toHaveBeenCalledWith("category");
  },
};

export const SingleChip: Story = {
  args: { chips: [{ id: "in_stock", label: "In stock only" }], onClearAll: undefined },
};

export const Empty: Story = { args: { chips: [] } };
