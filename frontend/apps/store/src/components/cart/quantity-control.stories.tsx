import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import { QuantityControl } from "./quantity-control";

const meta = {
  title: "Store/QuantityControl",
  component: QuantityControl,
  args: { name: "Running shoes", value: 2, onChange: () => undefined },
} satisfies Meta<typeof QuantityControl>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const AtMinimum: Story = {
  args: { value: 1 },
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByRole("button", { name: "Decrease quantity of Running shoes" })).toBeDisabled();
  },
};

export const AtMaximum: Story = {
  args: { value: 99 },
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByRole("button", { name: "Increase quantity of Running shoes" })).toBeDisabled();
  },
};

export const Disabled: Story = { args: { disabled: true } };

export const InvalidInput: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const input = canvas.getByRole("textbox", { name: "Quantity of Running shoes" });
    await userEvent.clear(input);
    await userEvent.type(input, "abc");
    await userEvent.tab();
    await expect(await canvas.findByRole("alert")).toHaveTextContent("Enter a whole number from 1 to 99.");
    await expect(input).toBeInvalid();
  },
};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
