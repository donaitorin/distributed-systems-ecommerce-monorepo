import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import type { OrderDetail, Payment } from "../../lib/types";
import { OrderDetailView } from "./order-detail-view";

const ORDER: OrderDetail = {
  id: "6f1c2f64-3f0e-4c1a-9d52-7a1b8c9d0e21",
  customer_id: "0f6c1f0e-7a52-4f33-9c2a-5d9c3b1e7a10",
  customer_email: "ada@example.com",
  status: "CONFIRMED",
  total: "137.50",
  currency: "USD",
  card_last4: "1111",
  shipping_address: {
    recipient_name: "Ada Lovelace",
    line1: "12 Analytical St",
    line2: "Floor 2",
    city: "London",
    region: "Greater London",
    postal_code: "N1 9GU",
    country: "GB",
    phone: "+442071234567",
  },
  cancel_reason: null,
  refunded_at: null,
  created_at: "2026-10-17T10:00:00Z",
  updated_at: "2026-10-17T10:00:09Z",
  lines: [
    { sku: "RS-001", name: "Running shoes", quantity: 2, unit_price: "59.00", line_total: "118.00" },
    { sku: "TY-002", name: null, quantity: 1, unit_price: "19.50", line_total: "19.50" },
  ],
  history: [
    { from_status: null, to_status: "PENDING", reason: "order created", at: "2026-10-17T10:00:00Z" },
    { from_status: "PENDING", to_status: "STOCK_RESERVED", reason: "stock reserved", at: "2026-10-17T10:00:02Z" },
    { from_status: "STOCK_RESERVED", to_status: "CONFIRMED", reason: "order confirmed", at: "2026-10-17T10:00:09Z" },
  ],
};

const PAYMENT: Payment = {
  id: "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa",
  order_id: ORDER.id,
  status: "SUCCEEDED",
  amount: "137.50",
  currency: "USD",
  card_last4: "1111",
  failure_reason: null,
  refunded_at: null,
  created_at: "2026-10-17T10:00:03Z",
  updated_at: "2026-10-17T10:00:08Z",
};

const meta = {
  title: "Backoffice/OrderDetailView",
  component: OrderDetailView,
  parameters: { layout: "padded" },
  args: { order: ORDER, payment: { payment: PAYMENT } },
} satisfies Meta<typeof OrderDetailView>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Confirmed: Story = {};

export const OldOrderWithoutEmail: Story = { args: { order: { ...ORDER, customer_email: null } } };

export const PaymentDeclined: Story = {
  args: {
    order: { ...ORDER, status: "CANCELLED", cancel_reason: "payment_failed", card_last4: "0000" },
    payment: { payment: { ...PAYMENT, status: "FAILED", failure_reason: "card_declined", card_last4: "0000" } },
  },
};

export const RefundedAfterLatePayment: Story = {
  args: {
    order: { ...ORDER, status: "CANCELLED", cancel_reason: "saga_timeout", refunded_at: "2026-10-17T10:02:00Z" },
    payment: { payment: { ...PAYMENT, status: "REFUNDED", refunded_at: "2026-10-17T10:02:00Z" } },
  },
};

export const NoPaymentRecorded: Story = {
  args: { order: { ...ORDER, status: "CANCELLED", cancel_reason: "insufficient_stock" }, payment: { payment: null, unavailable: false } },
};

export const PaymentUnavailable: Story = { args: { payment: { payment: null, unavailable: true } } };

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
