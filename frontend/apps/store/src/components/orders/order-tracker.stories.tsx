import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, fn, within } from "storybook/test";
import { OrderRequestError } from "../../lib/order-client";
import type { Order } from "../../lib/orders";
import { OrderTracker } from "./order-tracker";

const STORY_ORDER: Order = {
  id: "6f1c2f64-3f0e-4c1a-9d52-7a1b8c9d0e21",
  customer_id: "0f6c1f0e-7a52-4f33-9c2a-5d9c3b1e7a10",
  status: "CONFIRMED",
  total: "207.90",
  currency: "USD",
  card_last4: "1111",
  shipping_address: {
    recipient_name: "Ada Lovelace",
    line1: "12 Analytical St",
    line2: null,
    city: "London",
    region: null,
    postal_code: "N1 9GU",
    country: "GB",
    phone: null,
  },
  cancel_reason: null,
  refunded_at: null,
  created_at: "2026-10-17T10:00:00Z",
  updated_at: "2026-10-17T10:00:09Z",
  lines: [
    { sku: "RS-001", name: "Running shoes", quantity: 2, unit_price: "59.00", line_total: "118.00" },
    { sku: "RS-002", name: null, quantity: 1, unit_price: "89.90", line_total: "89.90" },
  ],
  history: [
    { from_status: null, to_status: "PENDING", reason: "order created", at: "2026-10-17T10:00:00Z" },
    { from_status: "PENDING", to_status: "STOCK_RESERVED", reason: "stock reserved", at: "2026-10-17T10:00:02Z" },
    { from_status: "STOCK_RESERVED", to_status: "PAID", reason: "payment succeeded", at: "2026-10-17T10:00:05Z" },
    { from_status: "PAID", to_status: "CONFIRMED", reason: "order confirmed", at: "2026-10-17T10:00:05Z" },
  ],
};
const pending: Order = {
  ...STORY_ORDER,
  status: "PENDING",
  updated_at: "2026-10-17T10:00:00Z",
  history: STORY_ORDER.history.slice(0, 1),
  lines: STORY_ORDER.lines.map((line) => ({ ...line, name: null })),
};

const meta = {
  title: "Store/OrderTracker",
  component: OrderTracker,
  parameters: { layout: "padded" },
  args: { initial: STORY_ORDER, fetchOrder: () => Promise.resolve(STORY_ORDER), onSessionExpired: fn() },
} satisfies Meta<typeof OrderTracker>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Confirmed: Story = {};

export const WaitingForStock: Story = { args: { initial: pending, fetchOrder: () => Promise.resolve(pending) } };

export const MovingToConfirmed: Story = {
  args: { initial: pending, fetchOrder: () => Promise.resolve({ ...STORY_ORDER, status: "STOCK_RESERVED" }) },
  play: async ({ canvasElement }) => {
    await expect(await within(canvasElement).findByText("Payment in progress", {}, { timeout: 4000 })).toBeVisible();
  },
};

export const PaymentDeclined: Story = {
  args: { initial: { ...STORY_ORDER, status: "CANCELLED", cancel_reason: "payment_failed" } },
};

export const RefundedAfterLatePayment: Story = {
  args: { initial: { ...STORY_ORDER, status: "CANCELLED", cancel_reason: "saga_timeout", refunded_at: "2026-10-17T10:02:00Z" } },
};

export const StatusUnavailable: Story = {
  args: { initial: pending, fetchOrder: () => Promise.reject(new OrderRequestError(null)) },
  play: async ({ canvasElement }) => {
    await expect(await within(canvasElement).findByText(/cannot refresh the status right now/, {}, { timeout: 8000 })).toBeVisible();
  },
};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
