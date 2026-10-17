import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import { MAX_ADDRESSES } from "../../lib/addresses";
import { STORY_ADDRESS, STORY_OTHER_ADDRESS } from "../story-support";
import { AddressBook, type AddressBookActions } from "./address-book";

const actions: AddressBookActions = {
  add: () => Promise.resolve({ ok: true, address: STORY_OTHER_ADDRESS }),
  remove: () => Promise.resolve({ ok: true }),
};

const meta = {
  title: "Store/AddressBook",
  component: AddressBook,
  args: { addresses: [STORY_ADDRESS, STORY_OTHER_ADDRESS], actions },
} satisfies Meta<typeof AddressBook>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Empty: Story = { args: { addresses: [] } };

export const AtTheLimit: Story = {
  args: {
    addresses: Array.from({ length: MAX_ADDRESSES }, (_value, index) => ({
      ...STORY_ADDRESS,
      id: `00000000-0000-4000-8000-${String(index).padStart(12, "0")}`,
    })),
  },
};

export const Adding: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Add an address" }));
    await expect(within(canvasElement).getByLabelText("Full name")).toBeVisible();
  },
};

export const ConfirmingDelete: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Delete address of Ada Lovelace, 12 Analytical St" }));
    await expect(await within(document.body).findByRole("dialog", { name: "Delete this address?" })).toBeVisible();
  },
};

export const DeleteFailed: Story = {
  args: { actions: { ...actions, remove: () => Promise.resolve({ ok: false, status: 503, title: "Down", fieldErrors: {} }) } },
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Delete address of Ada Lovelace, 12 Analytical St" }));
    const dialog = await within(document.body).findByRole("dialog", { name: "Delete this address?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete address" }));
    await expect(await within(dialog).findByRole("alert")).toHaveTextContent("could not be deleted");
  },
};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
