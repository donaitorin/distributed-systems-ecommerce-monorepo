import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import type { Failure } from "@ecommerce/web-core";
import type { AddressSaved } from "../../server/addresses";
import { STORY_ADDRESS } from "../story-support";
import { AddressForm } from "./address-form";

const saved = (): Promise<AddressSaved | Failure> => Promise.resolve({ ok: true, address: STORY_ADDRESS });
const failed = (status: number | null, fieldErrors: Record<string, string> = {}) => (): Promise<Failure> =>
  Promise.resolve({ ok: false, status, title: "Problem", fieldErrors });

const meta = {
  title: "Store/AddressForm",
  component: AddressForm,
  args: { submit: saved, onSaved: fn() },
} satisfies Meta<typeof AddressForm>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const WithCancel: Story = { args: { onCancel: fn() } };

export const InvalidInput: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "Save address" }));
    await expect(await canvas.findByLabelText("Full name")).toBeInvalid();
  },
};

export const ServerFieldError: Story = {
  args: { submit: failed(422, { postal_code: "Use at most 20 characters" }) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(canvas.getByLabelText("Full name"), "Ada Lovelace");
    await userEvent.type(canvas.getByLabelText("Address line 1"), "12 Analytical St");
    await userEvent.type(canvas.getByLabelText("City"), "London");
    await userEvent.type(canvas.getByLabelText("Postal code"), "N1 9GU");
    await userEvent.type(canvas.getByLabelText("Country"), "GB");
    await userEvent.click(canvas.getByRole("button", { name: "Save address" }));
    await expect(await canvas.findByLabelText("Postal code")).toBeInvalid();
  },
};

export const LimitReached: Story = {
  args: { submit: failed(409) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(canvas.getByLabelText("Full name"), "Ada Lovelace");
    await userEvent.type(canvas.getByLabelText("Address line 1"), "12 Analytical St");
    await userEvent.type(canvas.getByLabelText("City"), "London");
    await userEvent.type(canvas.getByLabelText("Postal code"), "N1 9GU");
    await userEvent.type(canvas.getByLabelText("Country"), "GB");
    await userEvent.click(canvas.getByRole("button", { name: "Save address" }));
    await expect(await canvas.findByRole("alert")).toHaveTextContent("10 saved addresses");
  },
};

export const Saving: Story = {
  args: { submit: () => new Promise<AddressSaved | Failure>(() => undefined) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(canvas.getByLabelText("Full name"), "Ada Lovelace");
    await userEvent.type(canvas.getByLabelText("Address line 1"), "12 Analytical St");
    await userEvent.type(canvas.getByLabelText("City"), "London");
    await userEvent.type(canvas.getByLabelText("Postal code"), "N1 9GU");
    await userEvent.type(canvas.getByLabelText("Country"), "GB");
    await userEvent.click(canvas.getByRole("button", { name: "Save address" }));
    await expect(await canvas.findByRole("button", { name: "Save address" })).toBeDisabled();
  },
};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
