import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import OrdersPage from "../src/app/orders/page";
import { summary } from "./support/orders";

const requireSession = jest.fn();
const loadOrderPage = jest.fn();

jest.mock("@ecommerce/auth/next", () => ({ requireSession: (options: unknown) => requireSession(options) as unknown }));
jest.mock("../src/server/orders", () => ({ loadOrderPage: (cursor: string | null) => loadOrderPage(cursor) as unknown }));

beforeEach(() => {
  requireSession.mockReset();
  loadOrderPage.mockReset();
  requireSession.mockResolvedValue({ userId: "u1", role: "customer" });
  loadOrderPage.mockResolvedValue({ items: [summary()], next_cursor: "next" });
});

const params = (search: Record<string, string | string[] | undefined> = {}) => ({ searchParams: Promise.resolve(search) });

describe("orders page", () => {
  it("requires a session and shows the first page, newest first as the API returns it", async () => {
    const { container } = render(await OrdersPage(params()));

    expect(requireSession).toHaveBeenCalledWith({ loginPath: "/login" });
    expect(loadOrderPage).toHaveBeenCalledWith(null);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Next page" })).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("reads the cursor of the address", async () => {
    render(await OrdersPage(params({ cursor: "abc" })));

    expect(loadOrderPage).toHaveBeenCalledWith("abc");
    expect(screen.getByRole("link", { name: "First page" })).toBeInTheDocument();
  });

  it.each([[""], [["a", "b"]], ["x".repeat(513)]])("ignores a cursor that is not usable (%j)", async (cursor) => {
    render(await OrdersPage(params({ cursor })));

    expect(loadOrderPage).toHaveBeenCalledWith(null);
  });

  it("explains a cursor the API no longer accepts, with a way back to the first page", async () => {
    loadOrderPage.mockResolvedValue({ ok: false, kind: "invalid_cursor" });

    const { container } = render(await OrdersPage(params({ cursor: "old" })));

    expect(screen.getByRole("alert")).toHaveTextContent("no longer valid");
    expect(screen.getByRole("link", { name: "Back to the first page" })).toHaveAttribute("href", "/orders");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("explains a temporary failure and retries the same page", async () => {
    loadOrderPage.mockResolvedValue({ ok: false, kind: "unavailable" });

    const { container } = render(await OrdersPage(params({ cursor: "abc" })));

    expect(screen.getByRole("alert")).toHaveTextContent("could not be loaded");
    expect(screen.getByRole("link", { name: "Try again" })).toHaveAttribute("href", "/orders?cursor=abc");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("retries the first page when there was no cursor", async () => {
    loadOrderPage.mockResolvedValue({ ok: false, kind: "unavailable" });

    render(await OrdersPage(params()));

    expect(screen.getByRole("link", { name: "Try again" })).toHaveAttribute("href", "/orders");
  });
});
