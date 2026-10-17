import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import type { PlaceOrderResult } from "../../lib/checkout";
import { STORY_ADDRESS, STORY_CART, STORY_OTHER_ADDRESS } from "../story-support";
import { CheckoutView, type CheckoutActions } from "./checkout-view";

const actions: CheckoutActions = {
  placeOrder: () => Promise.resolve({ ok: true, orderId: "6f1c2f64-3f0e-4c1a-9d52-7a1b8c9d0e21" }),
  newAttemptKey: () => Promise.resolve("fresh-attempt-key-0002"),
  addAddress: () => Promise.resolve({ ok: true, address: STORY_OTHER_ADDRESS }),
};

const rejecting = (result: PlaceOrderResult): CheckoutActions => ({ ...actions, placeOrder: () => Promise.resolve(result) });

const first = STORY_CART.items[0];
const FLAGGED = {
  ...STORY_CART,
  items: [
    ...(first ? [{ ...first, flags: [{ type: "price_changed" as const, old_price: "59.00", new_price: "64.50" }] }] : []),
    ...STORY_CART.items.slice(1),
  ],
};

async function typeCardAndPlace(canvasElement: HTMLElement) {
  const canvas = within(canvasElement);
  await userEvent.type(canvas.getByLabelText("Card number"), "4111111111111111");
  await userEvent.click(canvas.getByRole("button", { name: "Place order" }));
  return canvas;
}

const meta = {
  title: "Store/CheckoutView",
  component: CheckoutView,
  parameters: { layout: "padded" },
  args: { cart: STORY_CART, addresses: [STORY_ADDRESS], attemptKey: "first-attempt-key-0001", actions, onPlaced: fn() },
} satisfies Meta<typeof CheckoutView>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const SeveralAddresses: Story = { args: { addresses: [STORY_ADDRESS, STORY_OTHER_ADDRESS] } };

export const NoSavedAddress: Story = { args: { addresses: [] } };

export const BlockedByCartNotices: Story = { args: { cart: FLAGGED } };

export const TypingTheCard: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(canvas.getByLabelText("Card number"), "4111111111111111");
    await expect(canvas.getByLabelText("Card number")).toHaveValue("4111 1111 1111 1111");
  },
};

export const InvalidCard: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(canvas.getByLabelText("Card number"), "4111");
    await userEvent.click(canvas.getByRole("button", { name: "Place order" }));
    await expect(await canvas.findByLabelText("Card number")).toBeInvalid();
  },
};

export const AddressMissing: Story = {
  args: { addresses: [STORY_ADDRESS, STORY_OTHER_ADDRESS] },
  play: async ({ canvasElement }) => {
    const canvas = await typeCardAndPlace(canvasElement);
    await expect(await canvas.findByText("Choose a shipping address, or add a new one, to continue.")).toBeVisible();
  },
};

export const Placing: Story = {
  args: { actions: { ...actions, placeOrder: () => new Promise<PlaceOrderResult>(() => undefined) } },
  play: async ({ canvasElement }) => {
    const canvas = await typeCardAndPlace(canvasElement);
    await expect(await canvas.findByRole("button", { name: "Place order" })).toBeDisabled();
  },
};

export const ServiceUnavailable: Story = {
  args: { actions: rejecting({ ok: false, kind: "unavailable" }) },
  play: async ({ canvasElement }) => {
    const canvas = await typeCardAndPlace(canvasElement);
    await expect(await canvas.findByRole("alert")).toHaveTextContent("could not reach the order service");
  },
};

export const CartChanged: Story = {
  args: { actions: rejecting({ ok: false, kind: "cart_changed" }) },
  play: async ({ canvasElement }) => {
    const canvas = await typeCardAndPlace(canvasElement);
    await expect(await canvas.findByRole("link", { name: "Reload checkout" })).toBeVisible();
  },
};

export const RateLimited: Story = {
  args: { actions: rejecting({ ok: false, kind: "rate_limited", retryAfterSeconds: 30 }) },
  play: async ({ canvasElement }) => {
    const canvas = await typeCardAndPlace(canvasElement);
    await expect(await canvas.findByRole("alert")).toHaveTextContent("Wait 30 seconds");
  },
};

export const Mobile: Story = {
  args: { addresses: [STORY_ADDRESS, STORY_OTHER_ADDRESS] },
  globals: { viewport: { value: "mobile", isRotated: false } },
};
