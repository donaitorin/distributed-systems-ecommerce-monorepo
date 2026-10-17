import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import type { OrderSummary } from "../../lib/orders";
import { OrderHistory } from "./order-history";

const base: OrderSummary = {
  id: "6f1c2f64-3f0e-4c1a-9d52-7a1b8c9d0e21",
  customer_id: "0f6c1f0e-7a52-4f33-9c2a-5d9c3b1e7a10",
  status: "CONFIRMED",
  total: "207.90",
  currency: "USD",
  item_count: 3,
  created_at: "2026-10-17T10:00:00Z",
  updated_at: "2026-10-17T10:00:09Z",
};

const items: OrderSummary[] = [
  base,
  { ...base, id: "7a2d3e75-4f1f-4d2b-8e63-8b2c9d0e1f32", status: "CANCELLED", item_count: 1, total: "59.00", created_at: "2026-10-16T09:30:00Z" },
  { ...base, id: "8b3e4f86-5a20-4e3c-9f74-9c3d0e1f2a43", status: "STOCK_RESERVED", item_count: 12, total: "1204.50", created_at: "2026-10-15T08:15:00Z" },
  { ...base, id: "9c4f5a97-6b31-4f4d-8a85-0d4e1f2a3b54", status: "PENDING", item_count: 1, total: "9.99", created_at: "2026-10-14T07:00:00Z" },
];

const meta = {
  title: "Store/OrderHistory",
  component: OrderHistory,
  parameters: { layout: "padded" },
  args: { page: { items, next_cursor: "next" }, cursor: null },
} satisfies Meta<typeof OrderHistory>;

export default meta;
type Story = StoryObj<typeof meta>;

export const FirstPage: Story = {};

export const LaterPage: Story = { args: { page: { items, next_cursor: null }, cursor: "abc" } };

export const Empty: Story = { args: { page: { items: [], next_cursor: null } } };

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
