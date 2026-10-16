import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import type { CredentialsState } from "@ecommerce/web-core";
import { LoginForm } from "./login-form";

const answer = (state: CredentialsState) => () => Promise.resolve(state);

const meta = {
  title: "Store/LoginForm",
  component: LoginForm,
  args: { action: answer({}), next: "/products" },
} satisfies Meta<typeof LoginForm>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const FieldErrors: Story = {
  args: {
    action: answer({
      email: "ada",
      fieldErrors: { email: "Enter a valid email address", password: "Enter your password" },
    }),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "Sign in" }));
    await expect(await canvas.findByLabelText("Email")).toHaveFocus();
  },
};

export const WrongCredentials: Story = {
  args: { action: answer({ email: "ada@example.com", error: "The email or password is incorrect." }) },
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Sign in" }));
    await expect(await within(canvasElement).findByRole("alert")).toBeVisible();
  },
};

export const RateLimited: Story = {
  args: { action: answer({ error: "Too many sign in attempts. Try again in 42 seconds." }) },
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Sign in" }));
    await expect(await within(canvasElement).findByRole("alert")).toBeVisible();
  },
};

export const Submitting: Story = {
  args: { action: () => new Promise<CredentialsState>(() => undefined) },
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Sign in" }));
    await expect(await within(canvasElement).findByRole("button", { name: "Sign in" })).toBeDisabled();
  },
};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
