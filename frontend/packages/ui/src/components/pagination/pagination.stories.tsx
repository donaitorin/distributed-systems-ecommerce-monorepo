import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { Pagination } from "./pagination";

const meta = {
  title: "Components/Pagination",
  component: Pagination,
  parameters: { layout: "padded" },
  args: {
    hasPrevious: true,
    hasNext: true,
    onPrevious: fn(),
    onNext: fn(),
    total: 1240,
    totalExact: true,
  },
} satisfies Meta<typeof Pagination>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  play: async ({ canvasElement, args }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Next" }));
    await expect(args.onNext).toHaveBeenCalledTimes(1);
  },
};

export const FirstPage: Story = { args: { hasPrevious: false } };

export const LastPage: Story = { args: { hasNext: false } };

export const ApproximateTotal: Story = { args: { total: 200500, totalExact: false } };

export const Loading: Story = { args: { loading: true } };

export const Empty: Story = { args: { hasPrevious: false, hasNext: false, total: 0 } };
