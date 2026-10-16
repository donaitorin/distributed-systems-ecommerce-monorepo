import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import { AppShell } from "./app-shell";

const meta = {
  title: "Components/AppShell",
  component: AppShell,
  parameters: { layout: "fullscreen" },
  args: {
    brand: { label: "Store", href: "/" },
    navigation: [
      { label: "Products", href: "/products" },
      { label: "Account", href: "/account" },
    ],
    navigationLabel: "Main",
    footer: "Distributed systems e-commerce challenge",
    children: <h1 className="text-3xl font-semibold">Welcome</h1>,
  },
} satisfies Meta<typeof AppShell>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.tab();
    await expect(within(canvasElement).getByRole("link", { name: "Skip to content" })).toHaveFocus();
  },
};

export const WithoutNavigation: Story = { args: { navigation: [] } };

export const Backoffice: Story = {
  args: {
    brand: { label: "Backoffice", href: "/admin" },
    navigationLabel: "Admin",
    navigation: [
      { label: "Products", href: "/admin/products" },
      { label: "Imports", href: "/admin/imports" },
    ],
  },
};

export const WithActions: Story = {
  args: { actions: <button type="button" className="min-h-11 rounded-md border border-border-strong px-4 text-sm font-medium">Sign out</button> },
};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
