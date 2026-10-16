import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import UsersPage from "../src/app/users/page";
import { NotificationsProvider } from "../src/components/notifications";
import { profile } from "./support/api";

const loadUserPage = jest.fn();
const getSession = jest.fn();

jest.mock("../src/server/accounts", () => ({ loadUserPage: (...args: unknown[]) => loadUserPage(...args) as unknown }));
jest.mock("../src/server/products", () => ({ isFailure: (value: { ok?: boolean }) => value.ok === false }));
jest.mock("../src/app/users/actions", () => ({ changeUserRoleAction: jest.fn() }));
jest.mock("@ecommerce/auth/next", () => ({ getSession: () => getSession() as unknown }));

globalThis.Request ??= class Request {} as unknown as typeof Request;

function inProviders(element: React.ReactElement) {
  return render(
    <NuqsTestingAdapter>
      <NotificationsProvider>{element}</NotificationsProvider>
    </NuqsTestingAdapter>,
  );
}

beforeEach(() => {
  loadUserPage.mockReset();
  getSession.mockReset();
  getSession.mockResolvedValue({ userId: "u1", role: "admin" });
});

describe("users page", () => {
  it("loads the page for the URL's filters and marks the signed in user", async () => {
    loadUserPage.mockResolvedValue({ items: [profile({ user_id: "u1" })], next_cursor: null });

    const { container } = inProviders(
      await UsersPage({ searchParams: Promise.resolve({ role: "admin", limit: ["50", "100"], email: undefined, cursor: "bad" }) }),
    );

    expect(loadUserPage).toHaveBeenCalledWith(expect.objectContaining({ role: "admin", limit: 50, email: null, cursor: "bad" }));
    expect(screen.getByRole("heading", { level: 1, name: "Users" })).toBeInTheDocument();
    expect(screen.getAllByText("(you)").length).toBeGreaterThan(0);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows a failed load and works without a session value", async () => {
    loadUserPage.mockResolvedValue({ ok: false, status: 503, title: "Down", fieldErrors: {} });
    getSession.mockResolvedValue(null);

    inProviders(await UsersPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getAllByRole("alert")[0]).toHaveTextContent("not available right now");
  });
});
