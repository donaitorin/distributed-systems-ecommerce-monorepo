import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import type { Cart, CartActions } from "../../lib/cart";
import { STORY_CART, STORY_CART_ACTIONS } from "../story-support";
import { CartView } from "./cart-view";

const FLAGGED: Cart = {
  ...STORY_CART,
  items: [
    {
      ...(STORY_CART.items[0] ?? { sku: "", name: "", quantity: 1, price: "0", line_total: "0", thumbnail_url: null }),
      flags: [{ type: "price_changed", old_price: "59.00", new_price: "64.50" }],
    },
    { ...(STORY_CART.items[1] ?? { sku: "", name: "", quantity: 1, price: "0", line_total: "0", thumbnail_url: null }), flags: [{ type: "unavailable" }] },
  ],
};

const failing = (kind: "unavailable" | "cart_full" | "price_changed"): CartActions => ({
  ...STORY_CART_ACTIONS,
  setQuantity: () => Promise.resolve({ ok: false, kind, currentPrice: "66.00" }),
  removeItem: () => Promise.resolve({ ok: false, kind }),
});

const meta = {
  title: "Store/CartView",
  component: CartView,
  parameters: { layout: "padded" },
  args: { cart: STORY_CART, actions: STORY_CART_ACTIONS },
} satisfies Meta<typeof CartView>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Empty: Story = { args: { cart: { items: [], item_count: 0, subtotal: "0.00" } } };

export const WithNotices: Story = { args: { cart: FLAGGED } };

export const Removing: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "Remove Running shoes from your cart" }));
    await expect(await canvas.findByText("Running shoes removed from your cart.")).toBeVisible();
  },
};

export const ConfirmingClear: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Clear cart" }));
    await expect(await within(document.body).findByRole("dialog", { name: "Clear your cart?" })).toBeVisible();
  },
};

export const CartBusy: Story = {
  args: { actions: failing("unavailable") },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "Increase quantity of Running shoes" }));
    await expect(await canvas.findByRole("alert")).toHaveTextContent("Nothing was changed");
    await expect(canvas.getByRole("button", { name: "Try again" })).toBeEnabled();
  },
};

export const PriceChangedAgain: Story = {
  args: { cart: FLAGGED, actions: failing("price_changed") },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: /Accept new price/ }));
    await expect(await canvas.findByText(/The price changed from \$59.00 to \$66.00/)).toBeVisible();
  },
};

export const Mobile: Story = {
  args: { cart: FLAGGED },
  globals: { viewport: { value: "mobile", isRotated: false } },
};
