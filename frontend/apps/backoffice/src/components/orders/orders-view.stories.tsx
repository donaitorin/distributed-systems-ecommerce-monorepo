import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, within } from "storybook/test";
import type { OrderRow } from "../../lib/types";
import { withAppProviders } from "../story-support";
import { OrdersView } from "./orders-view";

const CONFIRMED: OrderRow = {
  id: "6f1c2f64-3f0e-4c1a-9d52-7a1b8c9d0e21",
  customer_id: "0f6c1f0e-7a52-4f33-9c2a-5d9c3b1e7a10",
  customer_email: "ada@example.com",
  status: "CONFIRMED",
  total: "137.50",
  currency: "USD",
  item_count: 3,
  created_at: "2026-10-17T10:00:00Z",
  updated_at: "2026-10-17T10:00:09Z",
};
const CANCELLED: OrderRow = { ...CONFIRMED, id: "7a2d3e75-4f1f-4d2b-8e63-8b2c9d0e1f32", status: "CANCELLED", total: "19.50", item_count: 1, customer_email: null };
const RESERVED: OrderRow = { ...CONFIRMED, id: "8b3e4f86-5a20-4e3c-9f74-9c3d0e1f2a43", status: "STOCK_RESERVED", total: "1204.50", item_count: 12 };

const meta = {
  title: "Backoffice/OrdersView",
  component: OrdersView,
  parameters: { layout: "padded" },
  args: { page: { items: [CONFIRMED, CANCELLED, RESERVED], next_cursor: "NEXT" }, failure: null },
} satisfies Meta<typeof OrdersView>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  decorators: [withAppProviders()],
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByRole("status")).toHaveTextContent("3 orders on this page");
  },
};

export const WithFilters: Story = { decorators: [withAppProviders("?status=CANCELLED&from=2026-10-01&to=2026-10-17")] };

export const LastPage: Story = { decorators: [withAppProviders()], args: { page: { items: [CONFIRMED], next_cursor: null } } };

export const Empty: Story = { decorators: [withAppProviders()], args: { page: { items: [], next_cursor: null } } };

export const Failed: Story = {
  decorators: [withAppProviders()],
  args: { page: null, failure: { ok: false, status: 503, title: "Down", fieldErrors: {} } },
};

export const StaleCursor: Story = {
  decorators: [withAppProviders()],
  args: { page: null, failure: { ok: false, status: 422, title: "Invalid", fieldErrors: { cursor: "no match" } } },
};

export const EndBeforeStart: Story = {
  decorators: [withAppProviders("?from=2026-10-17&to=2026-10-01")],
  args: { page: null },
};

export const Mobile: Story = {
  decorators: [withAppProviders()],
  globals: { viewport: { value: "mobile", isRotated: false } },
};
