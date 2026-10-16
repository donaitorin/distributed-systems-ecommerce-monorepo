import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { ConflictDialog } from "./conflict-dialog";

const meta = {
  title: "Backoffice/ConflictDialog",
  component: ConflictDialog,
  parameters: { layout: "fullscreen" },
  args: {
    open: true,
    latestAvailable: true,
    differences: [
      { label: "Name", mine: "My shoes", latest: "Boots" },
      { label: "Price", mine: "59.00", latest: "75.00" },
    ],
    onLoadLatest: () => undefined,
    onKeepMine: () => undefined,
    onDismiss: () => undefined,
  },
} satisfies Meta<typeof ConflictDialog>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const NoDifferentFields: Story = { args: { differences: [] } };

export const LatestUnavailable: Story = { args: { latestAvailable: false, differences: [] } };

export const EmptyValues: Story = {
  args: { differences: [{ label: "Description", mine: "", latest: "Now has a description" }] },
};

export const Closed: Story = { args: { open: false } };
