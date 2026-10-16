import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import type { LoginState } from "../lib/login-form";
import { LoginForm } from "./login-form";

const respondWith = (state: LoginState) => () => Promise.resolve(state);

const meta = {
  title: "Backoffice/LoginForm",
  component: LoginForm,
  parameters: { layout: "padded" },
  args: { next: "/products", action: respondWith({}) },
} satisfies Meta<typeof LoginForm>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const MissingFields: Story = {
  args: {
    action: respondWith({
      email: "",
      fieldErrors: { email: "Enter your email address", password: "Enter your password" },
    }),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "Sign in" }));
    await expect(await canvas.findByText("Enter your email address")).toBeVisible();
    await expect(canvas.getByLabelText("Email")).toHaveFocus();
  },
};

export const WrongCredentials: Story = {
  args: { action: respondWith({ email: "admin@example.com", error: "The email or password is incorrect." }) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "Sign in" }));
    await expect(await canvas.findByRole("alert")).toHaveTextContent("incorrect");
  },
};

export const RateLimited: Story = {
  args: { action: respondWith({ email: "admin@example.com", error: "Too many sign in attempts. Try again in 42 seconds." }) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "Sign in" }));
    await expect(await canvas.findByRole("alert")).toHaveTextContent("42 seconds");
  },
};

export const Pending: Story = {
  args: { action: () => new Promise<LoginState>(() => undefined) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "Sign in" }));
    await expect(await canvas.findByRole("button", { name: "Sign in" })).toHaveAttribute("aria-busy", "true");
  },
};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
