import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Button } from "../button/button";
import { EmptyState } from "./empty-state";

const meta = {
  title: "Components/EmptyState",
  component: EmptyState,
  args: {
    title: "No products match these filters",
    description: "Try removing a filter or searching for something else.",
    action: <Button variant="secondary">Clear all filters</Button>,
  },
} satisfies Meta<typeof EmptyState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const TitleOnly: Story = { args: { description: undefined, action: undefined } };
