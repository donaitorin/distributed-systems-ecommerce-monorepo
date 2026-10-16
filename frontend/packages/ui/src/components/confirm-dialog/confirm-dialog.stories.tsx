import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, within } from "storybook/test";
import { ConfirmDialog } from "./confirm-dialog";

const meta = {
  title: "Components/ConfirmDialog",
  component: ConfirmDialog,
  parameters: { layout: "fullscreen" },
  args: {
    open: true,
    onOpenChange: () => undefined,
    onConfirm: () => undefined,
    title: "Delete product?",
    description: "RS-001 Running shoes will be hidden from the store.",
    confirmLabel: "Delete product",
    variant: "danger",
  },
} satisfies Meta<typeof ConfirmDialog>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  play: async ({ canvasElement }) => {
    const body = within(canvasElement.ownerDocument.body);
    await expect(await body.findByRole("dialog", { name: "Delete product?" })).toBeVisible();
  },
};

export const Pending: Story = { args: { pending: true } };

export const WithError: Story = { args: { error: "The product was changed by someone else." } };

export const Primary: Story = {
  args: { variant: "primary", title: "Change role?", confirmLabel: "Change role", description: "This user becomes an admin." },
};
