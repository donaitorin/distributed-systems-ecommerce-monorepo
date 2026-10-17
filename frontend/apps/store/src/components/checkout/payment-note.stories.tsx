import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { PaymentNote } from "./payment-note";

const meta = { title: "Store/PaymentNote", component: PaymentNote } satisfies Meta<typeof PaymentNote>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
