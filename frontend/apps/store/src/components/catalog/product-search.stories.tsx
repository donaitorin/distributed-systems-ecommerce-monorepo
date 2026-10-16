import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, screen, userEvent, within } from "storybook/test";
import { ProductSearch } from "./product-search";
import { STORY_CATEGORIES, STORY_PAGE, withUrl } from "../story-support";

const meta = {
  title: "Store/ProductSearch",
  component: ProductSearch,
  parameters: { layout: "padded" },
  decorators: [withUrl()],
  args: { categories: STORY_CATEGORIES, page: STORY_PAGE, failure: null },
} satisfies Meta<typeof ProductSearch>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const WithFilters: Story = {
  decorators: [withUrl("?q=shoes&category=footwear&min_price=20&max_price=150&in_stock=true")],
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByRole("region", { name: "Active filters" })).toBeVisible();
  },
};

export const ExactTotal: Story = {
  args: { page: { ...STORY_PAGE, total: 4, total_exact: true, next_cursor: null } },
};

export const Empty: Story = {
  decorators: [withUrl("?q=zzzz&in_stock=true")],
  args: { page: { ...STORY_PAGE, items: [], total: 0, total_exact: true, next_cursor: null } },
};

export const NoProductsYet: Story = {
  args: { page: { ...STORY_PAGE, items: [], total: 0, total_exact: true, next_cursor: null } },
};

export const Failed: Story = {
  args: { page: null, failure: { ok: false, status: 503, title: "Unavailable", fieldErrors: {} } },
};

export const StaleCursor: Story = {
  decorators: [withUrl("?cursor=OLD")],
  args: { page: null, failure: { ok: false, status: 422, title: "Invalid", fieldErrors: { cursor: "mismatch" } } },
};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
  play: async ({ canvasElement }) => {
    const opener = within(canvasElement).getByRole("button", { name: "Filters" });
    await userEvent.click(opener);
    await expect(await screen.findByRole("dialog", { name: "Filters" })).toBeVisible();
    await userEvent.keyboard("{Escape}");
    await expect(opener).toHaveFocus();
  },
};
