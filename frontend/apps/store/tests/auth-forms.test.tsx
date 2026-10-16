import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import type { CredentialsState } from "@ecommerce/web-core";
import { LoginForm } from "../src/components/auth/login-form";
import { RegisterForm } from "../src/components/auth/register-form";
import type { RegisterState } from "../src/lib/auth-form";

function loginAction(result: CredentialsState) {
  return jest.fn<Promise<CredentialsState>, [CredentialsState, FormData]>(() => Promise.resolve(result));
}

function registerAction(result: RegisterState) {
  return jest.fn<Promise<RegisterState>, [RegisterState, FormData]>(() => Promise.resolve(result));
}

describe("LoginForm", () => {
  it("has no accessibility violations, with labelled fields and the next page carried along", async () => {
    const { container } = render(<LoginForm action={loginAction({})} next="/account" />);

    expect(screen.getByLabelText("Email")).toHaveAttribute("autocomplete", "username");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
    expect(container.querySelector("input[name=next]")).toHaveValue("/account");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("submits the typed values and the next page", async () => {
    const action = loginAction({});
    render(<LoginForm action={action} next="/account" />);

    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "secret{Enter}");

    await waitFor(() => {
      expect(action).toHaveBeenCalled();
    });
    const data = action.mock.calls[0]?.[1];
    expect(Object.fromEntries(data?.entries() ?? [])).toEqual({ email: "ada@example.com", password: "secret", next: "/account" });
  });

  it("describes and focuses the first invalid field", async () => {
    const action = loginAction({ email: "x", fieldErrors: { email: "Enter a valid email address", password: "Enter your password" } });
    const { container } = render(<LoginForm action={action} next="/products" />);

    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(screen.getByLabelText("Email")).toHaveFocus();
    });
    expect(screen.getByLabelText("Email")).toBeInvalid();
    expect(screen.getByLabelText("Email")).toHaveAccessibleDescription("Enter a valid email address");
    expect(screen.getByLabelText("Password")).toHaveAccessibleDescription("Enter your password");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("focuses the password when only it is invalid, and the alert for a general error", async () => {
    const passwordOnly = render(<LoginForm action={loginAction({ fieldErrors: { password: "Enter your password" } })} next="/products" />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => {
      expect(screen.getByLabelText("Password")).toHaveFocus();
    });
    passwordOnly.unmount();

    render(<LoginForm action={loginAction({ error: "The email or password is incorrect." })} next="/products" />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    const alert = await screen.findByRole("alert");
    await waitFor(() => {
      expect(alert).toHaveFocus();
    });
    expect(alert).toHaveTextContent("incorrect");
  });
});

describe("RegisterForm", () => {
  it("has no accessibility violations and explains the password rule up front", async () => {
    const { container } = render(<RegisterForm action={registerAction({})} next="/products" />);

    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "new-password");
    expect(screen.getByLabelText("Password")).toHaveAccessibleDescription(/at least 10 characters/i);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("submits the values and the next page", async () => {
    const action = registerAction({});
    render(<RegisterForm action={action} next="/account" />);

    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "a-long-password");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => {
      expect(action).toHaveBeenCalled();
    });
    expect(Object.fromEntries(action.mock.calls[0]?.[1].entries() ?? [])).toEqual({
      email: "ada@example.com",
      password: "a-long-password",
      next: "/account",
    });
  });

  it("shows a taken email on the email field with a link to sign in that keeps the next page", async () => {
    const action = registerAction({
      email: "ada@example.com",
      fieldErrors: { email: "An account with this email already exists." },
      emailTaken: true,
    });
    const { container } = render(<RegisterForm action={action} next="/account" />);

    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => {
      expect(screen.getByLabelText("Email")).toHaveFocus();
    });
    expect(screen.getByLabelText("Email")).toHaveAccessibleDescription(/already exists/);
    expect(screen.getByRole("link", { name: "Sign in with this email instead" })).toHaveAttribute(
      "href",
      "/login?next=%2Faccount",
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows the password rule on the password field and moves focus there", async () => {
    const action = registerAction({ fieldErrors: { password: "Use at least 10 characters." } });
    render(<RegisterForm action={action} next="/products" />);

    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => {
      expect(screen.getByLabelText("Password")).toHaveFocus();
    });
    expect(screen.getByLabelText("Password")).toHaveAccessibleDescription(/Use at least 10 characters\./);
  });

  it("announces a general error as an alert and focuses it", async () => {
    render(<RegisterForm action={registerAction({ error: "Too many sign up attempts. Try again in 30 seconds." })} next="/products" />);

    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    const alert = await screen.findByRole("alert");
    await waitFor(() => {
      expect(alert).toHaveFocus();
    });
  });
});
