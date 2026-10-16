import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import LoginPage from "../src/app/login/page";
import RegisterPage from "../src/app/register/page";

const getSession = jest.fn();

jest.mock("@ecommerce/auth/next", () => ({
  getSession: () => getSession() as unknown,
}));

jest.mock("../src/app/login/actions", () => ({ signInAction: jest.fn() }));
jest.mock("../src/app/register/actions", () => ({ registerAction: jest.fn() }));
jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

const params = <T extends object>(value: T) => Promise.resolve(value);

beforeEach(() => {
  getSession.mockReset();
  getSession.mockResolvedValue(null);
});

describe("login page", () => {
  it("has one heading, no violations and a link to create an account", async () => {
    const { container } = render(await LoginPage({ searchParams: params({}) }));

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create an account" })).toHaveAttribute("href", "/register");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("carries a safe next page into the form and the sign up link", async () => {
    const { container } = render(await LoginPage({ searchParams: params({ next: "/account" }) }));

    expect(container.querySelector("input[name=next]")).toHaveValue("/account");
    expect(screen.getByRole("link", { name: "Create an account" })).toHaveAttribute("href", "/register?next=%2Faccount");
  });

  it.each(["https://evil.example", "//evil.example", "/\\evil.example", "/login"])("ignores the hostile next page %s", async (next) => {
    const { container } = render(await LoginPage({ searchParams: params({ next }) }));

    expect(container.querySelector("input[name=next]")).toHaveValue("/products");
  });

  it("explains an expired session", async () => {
    render(await LoginPage({ searchParams: params({ reason: "expired", next: "/account" }) }));

    expect(screen.getByRole("alert")).toHaveTextContent("session expired");
  });

  it("shows no notice for an unknown reason", async () => {
    render(await LoginPage({ searchParams: params({ reason: "other" }) }));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("sends a signed in customer on to the next page, but still shows the form after an expiry", async () => {
    getSession.mockResolvedValue({ userId: "u1", role: "customer" });

    await expect(LoginPage({ searchParams: params({ next: "/account" }) })).rejects.toThrow("NEXT_REDIRECT /account");
    await expect(LoginPage({ searchParams: params({}) })).rejects.toThrow("NEXT_REDIRECT /products");
    render(await LoginPage({ searchParams: params({ reason: "expired" }) }));
    expect(screen.getByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
  });
});

describe("register page", () => {
  it("has one heading, no violations and a link to sign in", async () => {
    const { container } = render(await RegisterPage({ searchParams: params({}) }));

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: "Create an account" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("keeps a safe next page and drops a hostile one", async () => {
    const safe = render(await RegisterPage({ searchParams: params({ next: "/account" }) }));
    expect(safe.container.querySelector("input[name=next]")).toHaveValue("/account");
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login?next=%2Faccount");
    safe.unmount();

    const hostile = render(await RegisterPage({ searchParams: params({ next: "https://evil.example" }) }));
    expect(hostile.container.querySelector("input[name=next]")).toHaveValue("/products");
  });

  it("sends a signed in customer on", async () => {
    getSession.mockResolvedValue({ userId: "u1", role: "customer" });

    await expect(RegisterPage({ searchParams: params({ next: "/account" }) })).rejects.toThrow("NEXT_REDIRECT /account");
  });
});
