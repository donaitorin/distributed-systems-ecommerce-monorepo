import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import type { DeleteResult } from "../server/product-actions";
import { DeleteProductDialog } from "./delete-product-dialog";
import { withAppProviders } from "./story-support";

const meta = {
  title: "Backoffice/DeleteProductDialog",
  component: DeleteProductDialog,
  parameters: { layout: "fullscreen" },
  decorators: [withAppProviders()],
  args: {
    product: { sku: "RS-001", name: "Running shoes", version: 3 },
    deleteProduct: (): Promise<DeleteResult> => Promise.resolve({ ok: true }),
    onClose: () => undefined,
    onDeleted: () => undefined,
  },
} satisfies Meta<typeof DeleteProductDialog>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Open: Story = {};

export const Closed: Story = { args: { product: null } };

export const StaleVersion: Story = {
  args: {
    deleteProduct: () => Promise.resolve({ ok: false, status: 412, title: "Precondition failed", fieldErrors: {} }),
  },
  play: async ({ canvasElement }) => {
    const body = within(canvasElement.ownerDocument.body);
    await userEvent.click(await body.findByRole("button", { name: "Delete product" }));
    await expect(await body.findByText(/changed by someone else/, { selector: "p[role='alert']" })).toBeVisible();
  },
};

export const Unavailable: Story = {
  args: {
    deleteProduct: () => Promise.resolve({ ok: false, status: 503, title: "Down", fieldErrors: {}, retryAfterSeconds: 3 }),
  },
  play: async ({ canvasElement }) => {
    const body = within(canvasElement.ownerDocument.body);
    await userEvent.click(await body.findByRole("button", { name: "Delete product" }));
    await expect(await body.findByText(/Try again in 3 seconds/, { selector: "p[role='alert']" })).toBeVisible();
  },
};
