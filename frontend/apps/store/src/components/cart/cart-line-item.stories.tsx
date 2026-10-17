import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import { STORY_CART } from "../story-support";
import { CartLineItem } from "./cart-line-item";

const LINE = STORY_CART.items[0] ?? { sku: "", name: "", quantity: 1, price: "0", line_total: "0", thumbnail_url: null, flags: [] };

const meta = {
  title: "Store/CartLineItem",
  component: CartLineItem,
  decorators: [
    (Story) => (
      <ul className="list-none">
        <Story />
      </ul>
    ),
  ],
  args: {
    line: LINE,
    disabled: false,
    onQuantity: () => undefined,
    onRemove: () => undefined,
    onAcceptPrice: () => undefined,
  },
} satisfies Meta<typeof CartLineItem>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const PriceChanged: Story = {
  args: {
    line: { ...LINE, flags: [{ type: "price_changed", old_price: "59.00", new_price: "64.50" }] },
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByText(/The price changed from \$59.00 to \$64.50/)).toBeVisible();
    await userEvent.click(canvas.getByRole("button", { name: "Accept new price of $64.50 for Running shoes" }));
  },
};

export const NoLongerAvailable: Story = {
  args: { line: { ...LINE, flags: [{ type: "unavailable" }] } },
};

export const LowStock: Story = {
  args: { line: { ...LINE, flags: [{ type: "insufficient_stock", available: 1 }] } },
};

export const OutOfStock: Story = {
  args: { line: { ...LINE, flags: [{ type: "insufficient_stock", available: 0 }] } },
};

export const NoImage: Story = { args: { line: { ...LINE, thumbnail_url: null } } };

export const LongName: Story = {
  args: {
    line: { ...LINE, name: "Ultra lightweight trail running shoes with reinforced toe cap and breathable mesh upper" },
  },
};

export const Disabled: Story = { args: { disabled: true } };

export const Mobile: Story = {
  args: {
    line: {
      ...LINE,
      flags: [
        { type: "price_changed", old_price: "59.00", new_price: "64.50" },
        { type: "insufficient_stock", available: 1 },
      ],
    },
  },
  globals: { viewport: { value: "mobile", isRotated: false } },
};
