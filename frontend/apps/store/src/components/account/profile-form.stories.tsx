import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import type { Failure } from "@ecommerce/web-core";
import type { ProfileFormValues } from "../../lib/account-form";
import type { ProfileSaved } from "../../server/profile";
import { ProfileForm } from "./profile-form";

const PROFILE = {
  user_id: "0f6c1f0e-7a52-4f33-9c2a-5d9c3b1e7a10",
  email: "ada@example.com",
  role: "customer",
  name: "Ada Lovelace",
  phone: "+34600123456",
  created_at: "2026-10-14T10:00:00Z",
  updated_at: "2026-10-15T10:00:00Z",
};

const saved = (values: ProfileFormValues): Promise<ProfileSaved | Failure> =>
  Promise.resolve({ ok: true, profile: { ...PROFILE, name: values.name, phone: values.phone || null } });
const failed = (status: number | null, fieldErrors: Record<string, string> = {}) => (): Promise<Failure> =>
  Promise.resolve({ ok: false, status, title: "Problem", fieldErrors });

const meta = {
  title: "Store/ProfileForm",
  component: ProfileForm,
  args: { profile: { name: PROFILE.name, phone: PROFILE.phone }, submit: saved },
} satisfies Meta<typeof ProfileForm>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "Save profile" }));
    await expect(await canvas.findByText("Profile saved.")).toBeVisible();
  },
};

export const Empty: Story = { args: { profile: { name: null, phone: null } } };

export const InvalidInput: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.clear(canvas.getByLabelText("Name"));
    await userEvent.click(canvas.getByRole("button", { name: "Save profile" }));
    await expect(await canvas.findByLabelText("Name")).toBeInvalid();
  },
};

export const ServerFieldError: Story = {
  args: { submit: failed(422, { phone: "Start with + and the country code, then 8 to 15 digits in total." }) },
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Save profile" }));
    await expect(await within(canvasElement).findByLabelText("Phone")).toBeInvalid();
  },
};

export const Unavailable: Story = {
  args: { submit: failed(503) },
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Save profile" }));
    await expect(await within(canvasElement).findByRole("alert")).toBeVisible();
  },
};

export const Saving: Story = {
  args: { submit: () => new Promise<ProfileSaved | Failure>(() => undefined) },
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Save profile" }));
    await expect(await within(canvasElement).findByRole("button", { name: "Save profile" })).toBeDisabled();
  },
};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
