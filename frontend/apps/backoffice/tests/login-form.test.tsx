import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { LoginForm } from "../src/components/login-form";
import type { LoginState } from "../src/lib/login-form";

type LoginMock = jest.Mock<Promise<LoginState>, [LoginState, FormData]>;

function loginAction(result: LoginState = {}): LoginMock {
  return jest.fn<Promise<LoginState>, [LoginState, FormData]>().mockResolvedValue(result);
}

function renderForm(action: LoginMock, next = "/products") {
  return render(<LoginForm action={action} next={next} />);
}

describe("LoginForm", () => {
  it("has labelled fields, a hidden next value and no accessibility violations", async () => {
    const { container } = renderForm(loginAction());

    expect(screen.getByLabelText("Email")).toHaveAttribute("type", "email");
    expect(screen.getByLabelText("Email")).toHaveAttribute("autocomplete", "username");
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
    expect(container.querySelector("input[name='next']")).toHaveValue("/products");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("submits the entered credentials", async () => {
    const action = loginAction();
    renderForm(action);

    await userEvent.type(screen.getByLabelText("Email"), "admin@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "secret-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(action).toHaveBeenCalledTimes(1);
    });
    const data = action.mock.calls[0]?.[1];
    expect(data?.get("email")).toBe("admin@example.com");
    expect(data?.get("password")).toBe("secret-password");
    expect(data?.get("next")).toBe("/products");
  });

  it("moves focus to the first invalid field and links the message", async () => {
    const action = loginAction({
      email: "",
      fieldErrors: { email: "Enter your email address", password: "Enter your password" },
    });
    const { container } = renderForm(action);

    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(screen.getByLabelText("Email")).toHaveFocus();
    });
    expect(screen.getByLabelText("Email")).toBeInvalid();
    expect(screen.getByLabelText("Email")).toHaveAccessibleDescription("Enter your email address");
    expect(screen.getByLabelText("Password")).toBeInvalid();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("focuses the password when only the password is missing", async () => {
    const action = loginAction({ email: "a@b.c", fieldErrors: { password: "Enter your password" } });
    renderForm(action);

    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(screen.getByLabelText("Password")).toHaveFocus();
    });
    expect(screen.getByLabelText("Email")).toHaveValue("a@b.c");
  });

  it("announces a form error, focuses it and keeps the email but not the password", async () => {
    const action = loginAction({ email: "admin@example.com", error: "The email or password is incorrect." });
    const { container } = renderForm(action);

    await userEvent.type(screen.getByLabelText("Email"), "admin@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The email or password is incorrect.");
    await waitFor(() => {
      expect(alert).toHaveFocus();
    });
    expect(screen.getByLabelText("Email")).toHaveValue("admin@example.com");
    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows the busy state while the request is running", async () => {
    let finish: (state: LoginState) => void = () => undefined;
    const action = jest
      .fn<Promise<LoginState>, [LoginState, FormData]>()
      .mockReturnValue(new Promise<LoginState>((resolve) => (finish = resolve)));
    renderForm(action);

    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Sign in" })).toHaveAttribute("aria-busy", "true");
    });
    await act(async () => {
      finish({});
      await Promise.resolve();
    });
  });
});
