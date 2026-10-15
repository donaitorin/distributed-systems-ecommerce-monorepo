import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import { Button } from "../button/button";
import { Toast, ToastProvider, type ToastProps } from "./toast";

function ToastDemo(args: ToastProps) {
  const [open, setOpen] = useState(args.open);
  return (
    <ToastProvider>
      <Button
        onClick={() => {
          setOpen(true);
        }}
      >
        Show toast
      </Button>
      <Toast {...args} open={open} onOpenChange={setOpen} />
    </ToastProvider>
  );
}

const meta = {
  title: "Components/Toast",
  component: Toast,
  render: (args) => <ToastDemo {...args} />,
  args: {
    open: true,
    onOpenChange: () => {},
    title: "Product saved",
    description: "Your changes are live.",
    duration: 600000,
  },
} satisfies Meta<typeof Toast>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Success: Story = { args: { variant: "success" } };

export const ErrorToast: Story = {
  args: { variant: "error", title: "Could not save", description: "The server is unavailable." },
};

export const Info: Story = {
  args: { variant: "info", title: "Import queued", description: "88 rows will be processed." },
};

export const Dismissible: Story = {
  args: { variant: "success" },
  play: async ({ canvasElement }) => {
    const body = within(canvasElement.ownerDocument.body);
    await userEvent.click(await body.findByRole("button", { name: "Dismiss" }));
    await expect(body.queryByText("Product saved")).not.toBeInTheDocument();
  },
};
