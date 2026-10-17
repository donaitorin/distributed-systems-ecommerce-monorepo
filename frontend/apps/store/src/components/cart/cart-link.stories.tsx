import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, within } from "storybook/test";
import { CartLink } from "./cart-link";

const meta = {
  title: "Store/CartLink",
  component: CartLink,
  args: { count: 3 },
} satisfies Meta<typeof CartLink>;

export default meta;
type Story = StoryObj<typeof meta>;

export const WithItems: Story = {
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByRole("link", { name: "Cart 3 items in your cart" })).toHaveAttribute("href", "/cart");
  },
};

export const SingleItem: Story = { args: { count: 1 } };

export const Empty: Story = { args: { count: 0 } };

export const CountUnknown: Story = { args: { count: null } };
