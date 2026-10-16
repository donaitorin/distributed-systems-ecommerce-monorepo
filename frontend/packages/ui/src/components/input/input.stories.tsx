import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import { Input } from "./input";

const meta = {
  title: "Components/Input",
  component: Input,
  args: { label: "Product name" },
} satisfies Meta<typeof Input>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  play: async ({ canvasElement }) => {
    const input = within(canvasElement).getByLabelText("Product name");
    await userEvent.type(input, "Running shoes");
    await expect(input).toHaveValue("Running shoes");
  },
};

export const WithHint: Story = { args: { hint: "Shown in search results" } };

export const WithError: Story = {
  args: { defaultValue: "", error: "Product name is required" },
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByLabelText("Product name")).toBeInvalid();
  },
};

export const Disabled: Story = { args: { disabled: true, defaultValue: "Locked" } };
