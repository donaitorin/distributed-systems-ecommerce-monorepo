import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { AddToCartSlot } from "./add-to-cart-slot";

const meta = {
  title: "Store/AddToCartSlot",
  component: AddToCartSlot,
  args: { product: { sku: "RS-001", stock: 10 } },
} satisfies Meta<typeof AddToCartSlot>;

export default meta;
type Story = StoryObj<typeof meta>;

export const InStock: Story = {};

export const OutOfStock: Story = { args: { product: { sku: "RS-001", stock: 0 } } };
