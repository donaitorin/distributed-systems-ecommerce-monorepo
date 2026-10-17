import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import type { AddResult } from "../../lib/cart";
import { STORY_ADD } from "../story-support";
import { AddToCartForm } from "./add-to-cart-form";

const failing = (kind: "cart_full" | "unavailable" | "not_found") => (): Promise<AddResult> =>
  Promise.resolve({ ok: false, kind });

const meta = {
  title: "Store/AddToCartForm",
  component: AddToCartForm,
  args: {
    sku: "RS-001",
    name: "Running shoes",
    stock: 24,
    add: STORY_ADD,
  },
} satisfies Meta<typeof AddToCartForm>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "Add to cart" }));
    await expect(await canvas.findByText(/Added to your cart/)).toBeVisible();
    await expect(canvas.getByRole("link", { name: "View cart" })).toHaveAttribute("href", "/cart");
  },
};

export const LowStock: Story = { args: { stock: 3 } };

export const OutOfStock: Story = {
  args: { stock: 0 },
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByRole("button", { name: "Add to cart" })).toBeDisabled();
  },
};

export const Adding: Story = {
  args: { add: () => new Promise<AddResult>(() => undefined) },
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Add to cart" }));
    await expect(await within(canvasElement).findByRole("button", { name: "Add to cart" })).toBeDisabled();
  },
};

export const CartFull: Story = {
  args: { add: failing("cart_full") },
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Add to cart" }));
    await expect(await within(canvasElement).findByRole("alert")).toHaveTextContent("100 different products");
  },
};

export const Unavailable: Story = {
  args: { add: failing("unavailable") },
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Add to cart" }));
    await expect(await within(canvasElement).findByRole("alert")).toHaveTextContent("Try again in a moment");
  },
};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
