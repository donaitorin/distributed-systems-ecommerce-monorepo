import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, screen, userEvent, within } from "storybook/test";
import { Select } from "./select";

const CATEGORIES = [
  { value: "footwear", label: "Footwear" },
  { value: "toys", label: "Toys" },
  { value: "books", label: "Books", disabled: true },
];

const meta = {
  title: "Components/Select",
  component: Select,
  args: { label: "Category", options: CATEGORIES },
} satisfies Meta<typeof Select>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("combobox", { name: "Category" }));
    await userEvent.click(await screen.findByRole("option", { name: "Toys" }));
    await expect(within(canvasElement).getByRole("combobox")).toHaveTextContent("Toys");
  },
};

export const WithValue: Story = { args: { defaultValue: "footwear", hint: "Used for filtering" } };

export const WithError: Story = { args: { error: "Category is required" } };

export const Disabled: Story = { args: { disabled: true, defaultValue: "toys" } };
