import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, within } from "storybook/test";
import { ProductsView } from "./products-view";
import { STORY_CATEGORIES, STORY_PRODUCT, withAppProviders } from "../story-support";

const PAGE = {
  items: [
    STORY_PRODUCT,
    { ...STORY_PRODUCT, sku: "TY-002", name: "Toy robot", price: "19.50", stock: 3, category: null, version: 1 },
    { ...STORY_PRODUCT, sku: "BK-003", name: "Paperback novel", price: "12.00", stock: 0, version: 2 },
  ],
  next_cursor: "NEXT",
  prev_cursor: null,
  total: 3,
  total_exact: true,
};

const meta = {
  title: "Backoffice/ProductsView",
  component: ProductsView,
  parameters: { layout: "padded" },
  decorators: [withAppProviders("?q=shoes")],
  args: {
    categories: STORY_CATEGORIES,
    page: PAGE,
    failure: null,
    deleteProduct: () => Promise.resolve({ ok: true }),
  },
} satisfies Meta<typeof ProductsView>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByRole("status")).toHaveTextContent("3 results");
  },
};

export const ApproximateTotal: Story = {
  args: { page: { ...PAGE, total: 200500, total_exact: false, prev_cursor: "PREV" } },
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByRole("status")).toHaveTextContent("About 200,500 results");
  },
};

export const Empty: Story = {
  args: { page: { items: [], next_cursor: null, prev_cursor: null, total: 0, total_exact: true } },
};

export const Failed: Story = {
  args: {
    page: null,
    failure: { ok: false, status: 503, title: "Search timeout", fieldErrors: {} },
  },
};

export const StaleCursor: Story = {
  args: {
    page: null,
    failure: { ok: false, status: 422, title: "Validation failed", fieldErrors: { cursor: "does not match" } },
  },
};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
