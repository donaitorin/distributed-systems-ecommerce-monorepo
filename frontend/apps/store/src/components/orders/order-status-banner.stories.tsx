import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { OrderStatusBanner } from "./order-status-banner";

const meta = {
  title: "Store/OrderStatusBanner",
  component: OrderStatusBanner,
  args: { order: { status: "PENDING", cancel_reason: null, refunded_at: null } },
} satisfies Meta<typeof OrderStatusBanner>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ReservingStock: Story = {};

export const PaymentInProgress: Story = { args: { order: { status: "STOCK_RESERVED", cancel_reason: null, refunded_at: null } } };

export const Confirmed: Story = { args: { order: { status: "CONFIRMED", cancel_reason: null, refunded_at: null } } };

export const OutOfStock: Story = { args: { order: { status: "CANCELLED", cancel_reason: "insufficient_stock", refunded_at: null } } };

export const PaymentDeclined: Story = { args: { order: { status: "CANCELLED", cancel_reason: "payment_failed", refunded_at: null } } };

export const PaymentTimedOut: Story = { args: { order: { status: "CANCELLED", cancel_reason: "saga_timeout", refunded_at: null } } };

export const RefundedAfterLatePayment: Story = {
  args: { order: { status: "CANCELLED", cancel_reason: "saga_timeout", refunded_at: "2026-10-17T10:02:00Z" } },
};

export const Mobile: Story = {
  args: { order: { status: "CANCELLED", cancel_reason: "saga_timeout", refunded_at: "2026-10-17T10:02:00Z" } },
  globals: { viewport: { value: "mobile", isRotated: false } },
};
