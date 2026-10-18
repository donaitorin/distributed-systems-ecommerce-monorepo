import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import NotFound from "./not-found";

const meta = { title: "Store/NotFound", component: NotFound, parameters: { layout: "padded" } } satisfies Meta<typeof NotFound>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
