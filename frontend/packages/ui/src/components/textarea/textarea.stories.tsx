import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import { Textarea } from "./textarea";

const meta = {
  title: "Components/Textarea",
  component: Textarea,
  args: { label: "Description" },
} satisfies Meta<typeof Textarea>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  play: async ({ canvasElement }) => {
    const field = within(canvasElement).getByLabelText("Description");
    await userEvent.type(field, "Light and breathable");
    await expect(field).toHaveValue("Light and breathable");
  },
};

export const WithHint: Story = { args: { hint: "Up to 5000 characters" } };

export const WithError: Story = {
  args: { error: "Description must be at most 5000 characters" },
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByLabelText("Description")).toBeInvalid();
  },
};

export const Disabled: Story = { args: { disabled: true, defaultValue: "Locked" } };
