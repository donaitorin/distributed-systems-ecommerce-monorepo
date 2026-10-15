import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import AccountPage from "../src/app/account/page";
import LoginPage from "../src/app/login/page";
import HomePage from "../src/app/page";

const requireSession = jest.fn();

jest.mock("@ecommerce/auth/next", () => ({
  requireSession: (options: unknown) => requireSession(options) as unknown,
}));

describe("home page", () => {
  it("has no accessibility violations", async () => {
    const { container } = render(<HomePage />);

    expect(await axe(container)).toHaveNoViolations();
  });

  it("has one level 1 heading and loading placeholders for the catalog", () => {
    render(<HomePage />);

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getAllByRole("status")).toHaveLength(4);
  });
});

describe("login page", () => {
  it("has no accessibility violations and one level 1 heading", async () => {
    const { container } = render(<LoginPage />);

    expect(screen.getByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("account page", () => {
  it("requires a session and greets the user by email", async () => {
    requireSession.mockResolvedValue({ userId: "u1", email: "ada@example.com", role: "customer" });

    const { container } = render(await AccountPage());

    expect(requireSession).toHaveBeenCalledWith({ loginPath: "/login" });
    expect(screen.getByText("Signed in as ada@example.com.")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("falls back to the user id when the token has no email", async () => {
    requireSession.mockResolvedValue({ userId: "u1", role: "customer" });

    render(await AccountPage());

    expect(screen.getByText("Signed in as u1.")).toBeInTheDocument();
  });
});
