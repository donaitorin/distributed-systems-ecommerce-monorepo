import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import DashboardPage from "../src/app/page";
import LoginPage from "../src/app/login/page";

const getSession = jest.fn();

jest.mock("@ecommerce/auth/next", () => ({
  getSession: () => getSession() as unknown,
  signIn: jest.fn(),
}));

jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

async function renderLogin(searchParams: { reason?: string; next?: string } = {}) {
  return render(await LoginPage({ searchParams: Promise.resolve(searchParams) }));
}

beforeEach(() => {
  getSession.mockReset();
  getSession.mockResolvedValue(null);
});

describe("dashboard page", () => {
  it("greets the signed in administrator and has no accessibility violations", async () => {
    getSession.mockResolvedValue({ userId: "u1", email: "admin@example.com", role: "admin" });

    const { container } = render(await DashboardPage());

    expect(screen.getByRole("heading", { level: 1, name: "Backoffice" })).toBeInTheDocument();
    expect(screen.getByText(/admin@example.com/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to products" })).toHaveAttribute("href", "/admin/products");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("falls back to the user id, then to a generic label", async () => {
    getSession.mockResolvedValue({ userId: "u1", role: "admin" });
    const { unmount } = render(await DashboardPage());
    expect(screen.getByText(/Signed in as u1/)).toBeInTheDocument();
    unmount();

    getSession.mockResolvedValue(null);
    render(await DashboardPage());
    expect(screen.getByText(/an administrator/)).toBeInTheDocument();
  });
});

describe("login page", () => {
  it("has one level 1 heading, the form and no alert by default", async () => {
    const { container } = await renderLogin();

    expect(screen.getByRole("heading", { level: 1, name: "Administrator sign in" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it.each([
    ["forbidden", "does not have access"],
    ["expired", "session expired"],
  ])("explains the %s redirect with an alert", async (reason, text) => {
    const { container } = await renderLogin({ reason });

    expect(screen.getByRole("alert")).toHaveTextContent(text);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("ignores unknown reasons", async () => {
    await renderLogin({ reason: "other" });

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("only carries a safe internal next path into the form", async () => {
    const { container, unmount } = await renderLogin({ next: "/products?q=a" });
    expect(container.querySelector("input[name='next']")).toHaveValue("/products?q=a");
    unmount();

    for (const hostile of ["https://evil.example", "//evil.example", "/admin//evil.example", "/\\evil.example"]) {
      const view = await renderLogin({ next: hostile });
      expect(view.container.querySelector("input[name='next']")).toHaveValue("/");
      view.unmount();
    }
  });

  it("sends an administrator who is already signed in to the destination", async () => {
    getSession.mockResolvedValue({ userId: "u1", role: "admin" });

    await expect(LoginPage({ searchParams: Promise.resolve({ next: "/admin/products" }) })).rejects.toThrow(
      "NEXT_REDIRECT /products",
    );
  });

  it("does not redirect when there is a reason, so a customer does not loop", async () => {
    getSession.mockResolvedValue({ userId: "u1", role: "admin" });

    await renderLogin({ reason: "forbidden" });

    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });

  it("shows the form to a customer who is signed in", async () => {
    getSession.mockResolvedValue({ userId: "u2", role: "customer" });

    await renderLogin();

    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });
});
