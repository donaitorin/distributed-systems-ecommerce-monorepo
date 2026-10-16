import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import type { RegisterState } from "../../lib/auth-form";
import { RegisterForm } from "./register-form";

const answer = (state: RegisterState) => () => Promise.resolve(state);

const meta = {
  title: "Store/RegisterForm",
  component: RegisterForm,
  args: { action: answer({}), next: "/products" },
} satisfies Meta<typeof RegisterForm>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const EmailTaken: Story = {
  args: {
    action: answer({
      email: "ada@example.com",
      fieldErrors: { email: "An account with this email already exists. Sign in instead, or use another email." },
      emailTaken: true,
    }),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "Create account" }));
    await expect(await canvas.findByRole("link", { name: "Sign in with this email instead" })).toBeVisible();
  },
};

export const WeakPassword: Story = {
  args: {
    action: answer({
      email: "ada@example.com",
      fieldErrors: { password: "That password is too easy to guess. Choose something less common, such as a few unrelated words." },
    }),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "Create account" }));
    await expect(await canvas.findByLabelText("Password")).toHaveFocus();
  },
};

export const RateLimited: Story = {
  args: { action: answer({ error: "Too many sign up attempts. Try again in 30 seconds." }) },
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Create account" }));
    await expect(await within(canvasElement).findByRole("alert")).toBeVisible();
  },
};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
