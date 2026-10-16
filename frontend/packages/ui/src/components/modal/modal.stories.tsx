import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, screen, userEvent, within } from "storybook/test";
import { Button } from "../button/button";
import { Modal } from "./modal";

const meta = {
  title: "Components/Modal",
  component: Modal,
  args: {
    title: "Delete product",
    description: "This removes the product from the catalog.",
    trigger: <Button variant="danger">Delete product</Button>,
    children: <p className="text-sm">Orders that already include it are not affected.</p>,
    footer: (
      <>
        <Button variant="secondary">Cancel</Button>
        <Button variant="danger">Delete</Button>
      </>
    ),
  },
} satisfies Meta<typeof Modal>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  play: async ({ canvasElement }) => {
    const trigger = within(canvasElement).getByRole("button", { name: "Delete product" });
    await userEvent.click(trigger);
    await expect(await screen.findByRole("dialog", { name: "Delete product" })).toBeVisible();
    await userEvent.keyboard("{Escape}");
    await expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await expect(trigger).toHaveFocus();
  },
};

export const Open: Story = { args: { open: true } };

export const WithoutDescription: Story = { args: { open: true, description: undefined } };

export const Drawer: Story = {
  args: {
    variant: "drawer",
    title: "Filters",
    description: undefined,
    trigger: <Button variant="secondary">Filters</Button>,
    children: <p className="text-sm">Filter controls go here.</p>,
    footer: <Button>Show results</Button>,
  },
  play: async ({ canvasElement }) => {
    const trigger = within(canvasElement).getByRole("button", { name: "Filters" });
    await userEvent.click(trigger);
    await expect(await screen.findByRole("dialog", { name: "Filters" })).toBeVisible();
    await userEvent.keyboard("{Escape}");
    await expect(trigger).toHaveFocus();
  },
};

export const DrawerOpen: Story = { args: { ...Drawer.args, open: true } };
