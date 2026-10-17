import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { OrderStatusBadge } from "./order-status-badge";

const meta = {
  title: "Components/OrderStatusBadge",
  component: OrderStatusBadge,
  args: { status: "CONFIRMED" },
} satisfies Meta<typeof OrderStatusBadge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Confirmed: Story = {};

export const Cancelled: Story = { args: { status: "CANCELLED" } };

export const Pending: Story = { args: { status: "PENDING" } };

export const StockReserved: Story = { args: { status: "STOCK_RESERVED" } };

export const Paid: Story = { args: { status: "PAID" } };
