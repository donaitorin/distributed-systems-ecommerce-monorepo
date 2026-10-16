import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { PriceTag } from "./price-tag";

const meta = {
  title: "Components/PriceTag",
  component: PriceTag,
  args: { amount: "59.00", currency: "USD" },
} satisfies Meta<typeof PriceTag>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const LargeAmount: Story = { args: { amount: "1234567.89", currency: "USD" } };

export const OtherCurrency: Story = { args: { amount: "49.90", currency: "EUR" } };

export const Unavailable: Story = { args: { amount: "", currency: "USD" } };
