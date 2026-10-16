import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import DashboardPage from "../src/app/page";
import LoginPage from "../src/app/login/page";

const getSession = jest.fn();

jest.mock("@ecommerce/auth/next", () => ({
  getSession: () => getSession() as unknown,
}));

describe("dashboard page", () => {
  it("greets the signed in administrator and has no accessibility violations", async () => {
    getSession.mockResolvedValue({ userId: "u1", email: "admin@example.com", role: "admin" });

    const { container } = render(await DashboardPage());

    expect(screen.getByRole("heading", { level: 1, name: "Backoffice" })).toBeInTheDocument();
    expect(screen.getByText(/admin@example.com/)).toBeInTheDocument();
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
  it("has one level 1 heading and no alert by default", async () => {
    const { container } = render(await LoginPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByRole("heading", { level: 1, name: "Administrator sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("explains a forbidden redirect with an alert", async () => {
    const { container } = render(await LoginPage({ searchParams: Promise.resolve({ reason: "forbidden" }) }));

    expect(screen.getByRole("alert")).toHaveTextContent("does not have access");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("ignores unknown reasons", async () => {
    render(await LoginPage({ searchParams: Promise.resolve({ reason: "other" }) }));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
