import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { StockBadge } from "./stock-badge";

const meta = {
  title: "Components/StockBadge",
  component: StockBadge,
  args: { stock: 24 },
} satisfies Meta<typeof StockBadge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const InStock: Story = {};

export const LowStock: Story = { args: { stock: 3 } };

export const OutOfStock: Story = { args: { stock: 0 } };
