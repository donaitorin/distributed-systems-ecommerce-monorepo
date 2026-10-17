import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { STORY_ADD } from "../story-support";
import { AddToCartSlot } from "./add-to-cart-slot";

const meta = {
  title: "Store/AddToCartSlot",
  component: AddToCartSlot,
  args: { product: { sku: "RS-001", name: "Running shoes", stock: 10 }, add: STORY_ADD },
} satisfies Meta<typeof AddToCartSlot>;

export default meta;
type Story = StoryObj<typeof meta>;

export const InStock: Story = {};

export const OutOfStock: Story = { args: { product: { sku: "RS-001", name: "Running shoes", stock: 0 } } };
