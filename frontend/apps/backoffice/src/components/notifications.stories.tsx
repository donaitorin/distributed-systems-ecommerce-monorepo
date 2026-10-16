import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import { Button } from "@ecommerce/ui";
import { NotificationsProvider, useNotify } from "./notifications";

function Demo() {
  const notify = useNotify();
  return (
    <div className="flex gap-2">
      <Button
        onClick={() => {
          notify({ title: "Product saved", description: "RS-001 was updated.", variant: "success" });
        }}
      >
        Success
      </Button>
      <Button
        variant="danger"
        onClick={() => {
          notify({ title: "The product was not saved", description: "Some fields need attention.", variant: "error" });
        }}
      >
        Error
      </Button>
      <Button
        variant="secondary"
        onClick={() => {
          notify({ title: "Latest version loaded" });
        }}
      >
        Info
      </Button>
    </div>
  );
}

const meta = {
  title: "Backoffice/Notifications",
  component: NotificationsProvider,
  parameters: { layout: "padded" },
  args: { children: <Demo /> },
} satisfies Meta<typeof NotificationsProvider>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Idle: Story = {};

export const Success: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Success" }));
    await expect(await within(canvasElement.ownerDocument.body).findByText("RS-001 was updated.")).toBeVisible();
  },
};

export const ErrorToast: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Error" }));
    await expect(await within(canvasElement.ownerDocument.body).findByText("Some fields need attention.")).toBeVisible();
  },
};

export const Info: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Info" }));
    await expect(await within(canvasElement.ownerDocument.body).findByText("Latest version loaded")).toBeVisible();
  },
};
