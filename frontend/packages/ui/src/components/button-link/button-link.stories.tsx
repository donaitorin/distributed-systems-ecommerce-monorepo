import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { ButtonLink } from "./button-link";

const meta = {
  title: "Components/ButtonLink",
  component: ButtonLink,
  args: { href: "/products/new", children: "New product" },
} satisfies Meta<typeof ButtonLink>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {};

export const Secondary: Story = { args: { variant: "secondary", children: "Back to products" } };

export const Danger: Story = { args: { variant: "danger", children: "Leave without saving" } };
